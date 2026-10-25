from __future__ import annotations

import math

import polars as pl
import pytest

from tests.conftest import actuals_frame, utc
from windesk.domain import metrics
from windesk.domain.matching import MatchingRule, hourly_actuals


def test_hour_mean_averages_both_halves_and_takes_later_publication() -> None:
    a = actuals_frame(utc(2026, 1, 15, 0), [100.0, 300.0, 500.0, 700.0])
    out = hourly_actuals(a, MatchingRule.HOUR_MEAN)
    assert out["actual_mw"].to_list() == [200.0, 600.0]
    # available when the :30 period was published (00:30 + 30 min lag)
    assert out["available_at"][0] == utc(2026, 1, 15, 1, 0)


def test_hour_mean_drops_incomplete_hours() -> None:
    a = actuals_frame(utc(2026, 1, 15, 0), [100.0, 300.0, 500.0])
    out = hourly_actuals(a, MatchingRule.HOUR_MEAN)
    assert out.height == 1


def test_on_the_hour_uses_only_hh00_periods() -> None:
    a = actuals_frame(utc(2026, 1, 15, 0), [100.0, 300.0, 500.0, 700.0])
    out = hourly_actuals(a, MatchingRule.ON_THE_HOUR)
    assert out["actual_mw"].to_list() == [100.0, 500.0]


def _pairs(forecast: list[float | None], actual: list[float | None]) -> pl.DataFrame:
    return pl.DataFrame(
        {"forecast_mw": forecast, "actual_mw": actual},
        schema={"forecast_mw": pl.Float64, "actual_mw": pl.Float64},
    )


def test_summary_matches_hand_computed_values() -> None:
    s = metrics.summarize(_pairs([110, 90, 130], [100, 100, 100]), capacity_mw=1000)
    # errors: +10, -10, +30
    assert s.n == 3
    assert s.bias_mw == pytest.approx(10)
    assert s.mae_mw == pytest.approx(50 / 3)
    assert s.rmse_mw == pytest.approx(math.sqrt((100 + 100 + 900) / 3))
    assert s.wape == pytest.approx(50 / 300)
    assert s.nmae == pytest.approx(50 / 3 / 1000)
    assert s.err_p50_mw == pytest.approx(10)


def test_summary_ignores_incomplete_pairs() -> None:
    s = metrics.summarize(_pairs([110, None, 130], [100, 100, None]), capacity_mw=1000)
    assert s.n == 1
    assert s.bias_mw == pytest.approx(10)


def test_summary_of_nothing_is_empty_not_an_error() -> None:
    s = metrics.summarize(_pairs([None], [1.0]), capacity_mw=1000)
    assert s.n == 0
    assert s.mae_mw is None


def test_grouped_breaks_down_by_key() -> None:
    p = _pairs([110, 90, 130, 70], [100, 100, 100, 100]).with_columns(
        pl.Series("g", ["a", "a", "b", "b"])
    )
    g = metrics.grouped(p, "g", capacity_mw=1000)
    assert g["g"].to_list() == ["a", "b"]
    assert g["bias_mw"].to_list() == pytest.approx([0, 0])
    assert g["mae_mw"].to_list() == pytest.approx([10, 30])


def test_capacity_proxy_is_max_actual_and_rejects_empty() -> None:
    a = actuals_frame(utc(2026, 1, 1), [5.0, 9.0, 7.0])
    assert metrics.capacity_proxy(a) == 9.0
    with pytest.raises(ValueError, match="capacity proxy"):
        metrics.capacity_proxy(a.head(0))


def test_wind_level_buckets_are_left_closed() -> None:
    df = pl.DataFrame({"actual_mw": [0.0, 2999.0, 3000.0, 15000.0, 20000.0]})
    labels = df.select(metrics.wind_level()).to_series().cast(pl.String).to_list()
    assert labels == ["0-3 GW", "0-3 GW", "3-6 GW", "15+ GW", "15+ GW"]


def test_histogram_bins_align_to_width() -> None:
    h = metrics.histogram(pl.Series([-1.0, 10.0, 499.0, 500.0, None]), bin_mw=500)
    assert h.rows() == [(-500.0, 1), (0.0, 2), (500.0, 1)]
    assert metrics.histogram(pl.Series([], dtype=pl.Float64)).is_empty()
