from __future__ import annotations

from datetime import timedelta

from tests.conftest import forecasts_frame, utc
from windesk.domain.revisions import revisions

DAY_START, DAY_END = utc(2026, 1, 15), utc(2026, 1, 16)


def test_keeps_only_target_day_and_drops_already_started_hours() -> None:
    f = forecasts_frame(
        [
            (utc(2026, 1, 14, 9, 30), DAY_START, 100.0),
            (utc(2026, 1, 14, 9, 30), DAY_START - timedelta(hours=1), 1.0),  # previous day
            (utc(2026, 1, 15, 9, 30), DAY_START + timedelta(hours=8), 200.0),  # already started
            (utc(2026, 1, 15, 9, 30), DAY_START + timedelta(hours=12), 300.0),
            (utc(2026, 1, 15, 9, 30), DAY_END, 2.0),  # next day
        ]
    )
    out = revisions(f, DAY_START, DAY_END)
    assert out["forecast_mw"].to_list() == [100.0, 300.0]
    assert out.columns == ["publish_time", "start_time", "forecast_mw"]


def test_runs_are_ordered_oldest_first() -> None:
    f = forecasts_frame(
        [
            (utc(2026, 1, 14, 22, 30), DAY_START + timedelta(hours=5), 2.0),
            (utc(2026, 1, 13, 2, 30), DAY_START + timedelta(hours=5), 1.0),
        ]
    )
    assert revisions(f, DAY_START, DAY_END)["forecast_mw"].to_list() == [1.0, 2.0]
