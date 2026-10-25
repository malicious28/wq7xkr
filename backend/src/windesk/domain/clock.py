"""GB market time: settlement days, settlement periods and gate times.

Rules this module enforces:

* All instants are tz-aware UTC. Local (Europe/London) time is only an input
  format for *calendar* concepts: settlement days and exchange gate times.
* A settlement day runs 00:00-24:00 local time, so it is 23 h (46 periods)
  on the spring clock change, 25 h (50 periods) in autumn, otherwise 48.
* January is GMT (UTC == local), which hides time-zone bugs. The tests
  exercise the clock-change days explicitly for that reason.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
PERIOD = timedelta(minutes=30)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        msg = f"Naive datetime {dt.isoformat()} is ambiguous; pass a tz-aware value"
        raise ValueError(msg)
    return dt.astimezone(UTC)


def local_midnight_utc(d: date) -> datetime:
    """The UTC instant at which local calendar day ``d`` begins."""
    return datetime.combine(d, time(0), tzinfo=UK).astimezone(UTC)


def settlement_day_bounds(d: date) -> tuple[datetime, datetime]:
    """Half-open UTC interval ``[start, end)`` covered by settlement day ``d``."""
    return local_midnight_utc(d), local_midnight_utc(d + timedelta(days=1))


def periods_in_day(d: date) -> int:
    start, end = settlement_day_bounds(d)
    return int((end - start) / PERIOD)


def local_gate_to_utc(delivery_day: date, gate_local: time, days_before: int = 1) -> datetime:
    """UTC instant of a local gate time ``days_before`` days before delivery.

    Gate times are quoted in UK local time by the exchanges, so the
    conversion must go through the local calendar, not a fixed offset.
    """
    local_day = delivery_day - timedelta(days=days_before)
    return datetime.combine(local_day, gate_local, tzinfo=UK).astimezone(UTC)
