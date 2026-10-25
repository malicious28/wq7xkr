"""Out-of-sample models. The key property: a day's outputs never depend on its
own outturn or anything published after its cutoff."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

from tests.conftest import actuals_frame, forecasts_frame, utc
from windesk.domain import models
from windesk.domain.matching import MatchingRule, hourly_actuals
from windesk.domain.pairs import date_range, decision_pairs

GATE = time(9, 50)
FIRST, LAST = date(2026, 1, 1), date(2026, 1, 20)


def _world(bias: float = 0.0, scale: float = 1.0) -> tuple[pl.DataFrame, pl.DataFrame]:
    """A run published at 09:30 every day covering the next day, and matching actuals.

    Actual is a smooth daily cycle; forecast = scale * actual + bias.
    """
    start = utc(2025, 12, 31)
    hours = 24 * 22
    actual_hourly = [5000.0 + 2000.0 * ((h % 24) / 23) for h in range(hours)]
    half_hourly = [v for v in actual_hourly for _ in range(2)]
    actuals = actuals_frame(start, half_hourly)
    rows: list[tuple[datetime, datetime, float]] = []
    for d in range(21):
        pub = start + timedelta(days=d, hours=9, minutes=30)
        day_start = start + timedelta(days=d + 1)
        rows.extend(
            (pub, day_start + timedelta(hours=h), scale * actual_hourly[(d + 1) * 24 + h] + bias)
            for h in range(24)
        )
    return forecasts_frame(rows), actuals


def _fit(
    forecasts: pl.DataFrame,
    actuals: pl.DataFrame,
    days: list[date],
    cfg: models.FitConfig | None = None,
) -> pl.DataFrame:
    hourly = hourly_actuals(actuals, MatchingRule.HOUR_MEAN)
    pairs = decision_pairs(forecasts, hourly, date_range(FIRST, LAST), GATE)
    return models.fit_and_apply(pairs, hourly, days, cfg or models.FitConfig())


def test_constant_bias_is_removed_exactly_by_debiased_model() -> None:
    f, a = _world(bias=1500.0)
    out = _fit(f, a, [date(2026, 1, 15)])
    err = (out["debiased"] - out["actual_mw"]).abs().max()
    assert err == pytest.approx(0.0, abs=1e-6)
    assert (out["raw"] - out["actual_mw"]).mean() == pytest.approx(1500.0)


def test_proportional_bias_is_removed_by_ratio_model() -> None:
    f, a = _world(scale=1.15)
    out = _fit(f, a, [date(2026, 1, 15)])
    assert (out["ratio"] - out["actual_mw"]).abs().max() == pytest.approx(0.0, abs=1e-6)


def test_insufficient_history_yields_no_band_or_correction() -> None:
    f, a = _world(bias=100.0)
    out = _fit(f, a, [date(2026, 1, 3)])
    assert out["history_days"][0] < models.FitConfig().min_history_days
    assert out["debiased"].null_count() == out.height
    assert out["band_low"].null_count() == out.height
    assert out["raw"].null_count() == 0


def test_outputs_do_not_change_when_same_day_or_future_outturn_changes() -> None:
    """Metamorphic no-look-ahead test: corrupt every actual from the decision
    day onwards; the day's forecasts, corrections and band must be identical."""
    f, a = _world(bias=800.0)
    day = date(2026, 1, 15)
    baseline = _fit(f, a, [day])
    cut = utc(2026, 1, 14, 9, 50)
    corrupted = a.with_columns(
        pl.when(pl.col("publish_time") > cut)
        .then(pl.col("generation_mw") * 3 + 7777)
        .otherwise(pl.col("generation_mw"))
    )
    again = _fit(f, corrupted, [day])
    cols = ["raw", "debiased", "ratio", "persistence", "band_low", "band_high"]
    assert baseline.select(cols).equals(again.select(cols))


def test_persistence_is_last_outturn_known_at_cutoff() -> None:
    f, a = _world()
    out = _fit(f, a, [date(2026, 1, 15)])
    hourly = hourly_actuals(a, MatchingRule.HOUR_MEAN)
    known = hourly.filter(pl.col("available_at") <= utc(2026, 1, 14, 9, 50))
    assert out["persistence"][0] == known.sort("start_time")["actual_mw"][-1]


def test_model_scores_compare_on_common_rows_with_skill() -> None:
    f, a = _world(bias=1000.0)
    out = _fit(f, a, date_range(date(2026, 1, 10), date(2026, 1, 15)))
    scores = {r["model"]: r for r in models.model_scores(out).iter_rows(named=True)}
    assert scores["raw"]["mae_mw"] == pytest.approx(1000.0)
    assert scores["debiased"]["skill_vs_raw"] == pytest.approx(1.0)
    assert len({r["n"] for r in scores.values()}) == 1


def test_band_coverage_reports_share_inside_band() -> None:
    df = pl.DataFrame(
        {
            "actual_mw": [5.0, 15.0, 25.0, None],
            "band_low": [0.0, 0.0, 0.0, 0.0],
            "band_high": [10.0, 20.0, 20.0, 1.0],
        }
    )
    cov = models.band_coverage(df)
    assert cov["n"] == 3
    assert cov["coverage"] == pytest.approx(2 / 3)
    assert cov["above"] == pytest.approx(1 / 3)
    assert models.band_coverage(df.head(0))["coverage"] is None


def test_fit_and_apply_with_no_matching_days_returns_empty() -> None:
    f, a = _world()
    assert _fit(f, a, [date(2027, 1, 1)]).is_empty()
