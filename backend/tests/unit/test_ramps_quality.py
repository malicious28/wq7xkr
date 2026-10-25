from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

import polars as pl
import pytest

from tests.conftest import actuals_frame, forecasts_frame, utc
from windesk.domain import quality, ramps

CFG = ramps.RampConfig(threshold_mw=2000, window_h=3, tolerance_h=1)


def _series(actual: Sequence[float], forecast: Sequence[float]) -> pl.DataFrame:
    start = utc(2026, 1, 10)
    return pl.DataFrame(
        {
            "start_time": [start + timedelta(hours=i) for i in range(len(actual))],
            "forecast_mw": forecast,
            "actual_mw": actual,
        }
    ).cast({"start_time": pl.Datetime("us", "UTC")})


FLAT = [5000.0] * 10
UP_AT_2 = [5000, 5000, 5000, 6000, 7000, 8000, 8000, 8000, 8000, 8000]  # +3000 over 2->5


def test_ramp_forecast_on_time_is_a_hit() -> None:
    out = ramps.scores(ramps.classify(_series(UP_AT_2, UP_AT_2), CFG))
    assert out.misses == 0
    assert out.false_alarms == 0
    assert out.hits > 0
    assert out.pod == 1.0


def test_ramp_forecast_one_hour_late_is_still_a_hit_within_tolerance() -> None:
    late = [5000.0, *UP_AT_2[:-1]]
    out = ramps.scores(ramps.classify(_series(UP_AT_2, late), CFG))
    assert out.misses == 0
    assert out.hits > 0


def test_unforecast_ramp_is_a_miss_and_phantom_ramp_a_false_alarm() -> None:
    miss = ramps.scores(ramps.classify(_series(UP_AT_2, FLAT), CFG))
    assert miss.hits == 0
    assert miss.misses > 0
    assert miss.pod == 0.0
    fa = ramps.scores(ramps.classify(_series(FLAT, UP_AT_2), CFG))
    assert fa.false_alarms > 0
    assert fa.far == 1.0
    assert fa.pod is None


def test_opposite_direction_is_not_a_hit() -> None:
    down = [8000, 8000, 8000, 7000, 6000, 5000, 5000, 5000, 5000, 5000]
    out = ramps.scores(ramps.classify(_series(UP_AT_2, [float(x) for x in down]), CFG))
    assert out.hits == 0


def test_gaps_are_reindexed_and_not_bridged() -> None:
    s = _series(UP_AT_2, UP_AT_2)
    gappy = s.filter(pl.col("start_time") != utc(2026, 1, 10, 5))
    classified = ramps.classify(gappy, CFG)
    assert classified.height == s.height  # gap re-inserted as a null row
    assert classified.filter(pl.col("start_time") == utc(2026, 1, 10, 2))["outcome"][0] is None


def test_events_lists_each_ramp_start_once() -> None:
    ev = ramps.events(ramps.classify(_series(UP_AT_2, UP_AT_2), CFG), CFG)
    assert ev.height == 1
    assert ev["actual_ramp"][0] == 1
    assert ev["delta_mw"][0] >= 2000


def test_empty_series() -> None:
    empty = _series([], [])
    assert ramps.classify(empty, CFG).is_empty()
    assert ramps.events(ramps.classify(empty, CFG), CFG).is_empty()


# --- quality -------------------------------------------------------------------------------


def _run(pub: datetime) -> list[tuple[datetime, datetime, float]]:
    return [(pub, utc(2026, 1, 16) + timedelta(hours=h), 1000.0) for h in range(73)]


def test_run_schedule_flags_late_and_short_runs() -> None:
    f = forecasts_frame(
        [
            *_run(utc(2026, 1, 15, 9, 30)),
            *_run(utc(2026, 1, 15, 12, 25)),  # 11:30 slot, 55 min late
            *_run(utc(2026, 1, 15, 15, 30))[:10],  # short run
        ]
    )
    s = quality.run_schedule(f)
    assert s["late"].to_list() == [False, True, False]
    assert s["delay_min"].to_list() == [0, 55, 0]
    assert s["short"].to_list() == [False, False, True]


def test_run_before_first_slot_belongs_to_previous_days_last_slot() -> None:
    f = forecasts_frame(_run(utc(2026, 1, 16, 0, 10)))
    row = quality.run_schedule(f).row(0, named=True)
    assert row["slot_min"] == 22 * 60 + 30
    assert row["delay_min"] == 100
    assert row["publish_date"] == date(2026, 1, 15)


def test_missing_runs_lists_unfilled_slots() -> None:
    f = forecasts_frame(_run(utc(2026, 1, 15, 2, 30)))
    missing = quality.missing_runs(quality.run_schedule(f), date(2026, 1, 15), date(2026, 1, 15))
    assert len(missing) == 7
    assert {"date": date(2026, 1, 15), "slot_utc": "04:30"} in missing


def test_period_completeness_is_clock_change_aware() -> None:
    a = actuals_frame(utc(2026, 3, 29, 0), [1.0] * 46)
    c = quality.period_completeness(a, date(2026, 3, 29), date(2026, 3, 30))
    assert c["expected"].to_list() == [46, 48]
    assert c["complete"].to_list() == [True, False]


def test_publication_lag_and_implausible_values() -> None:
    a = actuals_frame(utc(2026, 1, 1), [1.0, 40_000.0], lag=timedelta(minutes=45))
    lag = quality.publication_lag(a)
    assert lag["p50_min"] == pytest.approx(45)
    assert quality.implausible(a) == 1
    assert quality.publication_lag(a.head(0))["p50_min"] is None
