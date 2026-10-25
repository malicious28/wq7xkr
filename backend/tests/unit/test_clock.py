from __future__ import annotations

from datetime import date, datetime, time

import pytest

from tests.conftest import utc
from windesk.domain import clock


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 1, 15), 48),
        (date(2026, 3, 29), 46),  # spring forward: 23 h day
        (date(2025, 10, 26), 50),  # fall back: 25 h day
        (date(2026, 10, 25), 50),
        (date(2026, 3, 30), 48),
    ],
)
def test_periods_in_day_follows_clock_changes(day: date, expected: int) -> None:
    assert clock.periods_in_day(day) == expected


def test_settlement_day_bounds_in_summer_start_at_23_utc() -> None:
    start, end = clock.settlement_day_bounds(date(2026, 7, 1))
    assert start == utc(2026, 6, 30, 23, 0)
    assert end == utc(2026, 7, 1, 23, 0)


def test_gate_time_converts_through_local_calendar() -> None:
    winter = clock.local_gate_to_utc(date(2026, 1, 15), time(9, 50))
    summer = clock.local_gate_to_utc(date(2026, 7, 15), time(9, 50))
    assert winter == utc(2026, 1, 14, 9, 50)
    assert summer == utc(2026, 7, 14, 8, 50)


def test_gate_time_for_day_after_clock_change_uses_the_gate_days_offset() -> None:
    # Delivery 30 Mar; gate on 29 Mar is already BST.
    assert clock.local_gate_to_utc(date(2026, 3, 30), time(9, 50)) == utc(2026, 3, 29, 8, 50)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        clock.ensure_utc(datetime(2026, 1, 1))


def test_autumn_settlement_day_is_25_hours_from_bst_midnight() -> None:
    start, end = clock.settlement_day_bounds(date(2026, 10, 25))
    assert start == utc(2026, 10, 24, 23, 0)  # 00:00 BST
    assert end == utc(2026, 10, 26, 0, 0)  # 00:00 GMT
    assert (end - start).total_seconds() == 25 * 3600
