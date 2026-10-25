from __future__ import annotations

from datetime import timedelta

import polars as pl
import pytest

from tests.conftest import forecasts_frame, utc
from windesk.domain import asof
from windesk.domain.pairs import horizon_pairs

T = utc(2026, 1, 15, 12)  # a target hour
NO_ACTUALS = pl.DataFrame(
    schema={
        "start_time": pl.Datetime("us", "UTC"),
        "actual_mw": pl.Float64,
        "available_at": pl.Datetime("us", "UTC"),
    }
)

# Three runs that all cover T, plus a later run that does *not* cover T.
FORECASTS = forecasts_frame(
    [
        (utc(2026, 1, 14, 9, 30), T, 1000.0),
        (utc(2026, 1, 14, 22, 30), T, 2000.0),
        (utc(2026, 1, 15, 9, 30), T, 3000.0),
        (utc(2026, 1, 15, 10, 30), T + timedelta(hours=1), 9999.0),
    ]
)


def _select(cutoff_time: object) -> dict[str, object]:
    targets = pl.DataFrame({"start_time": [T], "cutoff": [cutoff_time]}).cast(
        {"start_time": pl.Datetime("us", "UTC"), "cutoff": pl.Datetime("us", "UTC")}
    )
    return asof.select_asof(FORECASTS, targets).row(0, named=True)


def test_picks_latest_run_published_by_cutoff() -> None:
    row = _select(utc(2026, 1, 15, 0, 0))
    assert row["forecast_mw"] == 2000.0
    assert row["publish_time"] == utc(2026, 1, 14, 22, 30)
    assert row["lead_h"] == pytest.approx(13.5)


def test_run_published_exactly_at_cutoff_is_available() -> None:
    assert _select(utc(2026, 1, 15, 9, 30))["forecast_mw"] == 3000.0


def test_run_published_one_microsecond_after_cutoff_is_not() -> None:
    cutoff = utc(2026, 1, 15, 9, 30) - timedelta(microseconds=1)
    assert _select(cutoff)["forecast_mw"] == 2000.0


def test_newer_run_that_does_not_cover_target_is_skipped() -> None:
    # The 10:30 run is newest at 11:00 but has no point for T.
    assert _select(utc(2026, 1, 15, 11))["forecast_mw"] == 3000.0


def test_no_run_before_cutoff_gives_null() -> None:
    row = _select(utc(2026, 1, 1))
    assert row["forecast_mw"] is None
    assert row["publish_time"] is None


def test_horizon_pairs_use_target_minus_horizon_as_cutoff() -> None:
    out = horizon_pairs(FORECASTS, NO_ACTUALS, T, T + timedelta(hours=1), timedelta(hours=12))
    # cutoff = 00:00 on the 15th -> the 22:30 run
    assert out["forecast_mw"][0] == 2000.0
    assert out["cutoff"][0] == utc(2026, 1, 15, 0)


def test_negative_horizon_is_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        horizon_pairs(FORECASTS, NO_ACTUALS, T, T + timedelta(hours=1), timedelta(hours=-1))


def test_input_order_is_preserved() -> None:
    times = [T + timedelta(hours=1), T]
    targets = pl.DataFrame({"start_time": times, "cutoff": [utc(2026, 1, 15, 11)] * 2}).cast(
        {"start_time": pl.Datetime("us", "UTC"), "cutoff": pl.Datetime("us", "UTC")}
    )
    out = asof.select_asof(FORECASTS, targets)
    assert out["start_time"].to_list() == times
    assert out["forecast_mw"].to_list() == [9999.0, 3000.0]


def test_empty_targets_return_empty_frame_with_schema() -> None:
    empty = pl.DataFrame(
        schema={"start_time": pl.Datetime("us", "UTC"), "cutoff": pl.Datetime("us", "UTC")}
    )
    out = asof.select_asof(FORECASTS, empty)
    assert out.is_empty()
    assert out.columns == list(asof.ASOF_COLUMNS)
