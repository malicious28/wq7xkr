"""Data-quality checks: can the numbers on screen be trusted?

Checks are computed from the normalised data, not assumed:

* forecast runs per day against the observed publication schedule, with
  late and missing runs (Elexon's glossary still says 4 runs a day; the
  data shows 8)
* points per run (a full WINDFOR run has 73 hourly points)
* settlement periods per day against the clock-aware expectation (46/48/50)
* outturn publication lag, which bounds what a bias correction can use
* implausible values
"""

from __future__ import annotations

from datetime import date, time, timedelta

import polars as pl

from windesk.domain.clock import periods_in_day

# Observed WINDFOR schedule (UTC). A run is matched to the latest slot at or
# before its publish time; arriving more than LATE_AFTER after it is late.
RUN_SLOTS_UTC = (
    time(2, 30),
    time(4, 30),
    time(7, 30),
    time(9, 30),
    time(11, 30),
    time(15, 30),
    time(18, 30),
    time(22, 30),
)
LATE_AFTER = timedelta(minutes=10)
EXPECTED_POINTS = 73
PLAUSIBLE_MAX_MW = 30_000.0  # well above GB metered wind capacity


def _slot_minutes() -> list[int]:
    return [t.hour * 60 + t.minute for t in RUN_SLOTS_UTC]


def run_schedule(forecasts: pl.DataFrame) -> pl.DataFrame:
    """One row per run with its matched slot and delay in minutes."""
    slots = pl.Series("slot_min", _slot_minutes(), dtype=pl.Int32)
    runs = (
        forecasts.group_by("publish_time")
        .agg(pl.len().alias("points"))
        .with_columns(
            (
                pl.col("publish_time").dt.hour().cast(pl.Int32) * 60
                + pl.col("publish_time").dt.minute().cast(pl.Int32)
            ).alias("pub_min"),
            pl.col("publish_time").dt.date().alias("publish_date"),
        )
        .sort("pub_min")
    )
    matched = runs.join_asof(
        pl.DataFrame({"slot_min": slots}).sort("slot_min"),
        left_on="pub_min",
        right_on="slot_min",
        strategy="backward",
    ).with_columns(
        # Before the first slot of the day: the run belongs to yesterday's last slot.
        pl.when(pl.col("slot_min").is_null())
        .then(pl.col("pub_min") - _slot_minutes()[-1] + 24 * 60)
        .otherwise(pl.col("pub_min") - pl.col("slot_min"))
        .alias("delay_min"),
        pl.when(pl.col("slot_min").is_null())
        .then(pl.col("publish_date") - pl.duration(days=1))
        .otherwise(pl.col("publish_date"))
        .alias("publish_date"),
        pl.col("slot_min").fill_null(_slot_minutes()[-1]),
    )
    return matched.with_columns(
        (pl.col("delay_min") > LATE_AFTER.total_seconds() / 60).alias("late"),
        (pl.col("points") < EXPECTED_POINTS).alias("short"),
    ).sort("publish_time")


def missing_runs(schedule: pl.DataFrame, first: date, last: date) -> list[dict[str, object]]:
    """Scheduled (date, slot) pairs in ``[first, last]`` with no run."""
    seen = set(zip(schedule["publish_date"].to_list(), schedule["slot_min"].to_list(), strict=True))
    out: list[dict[str, object]] = []
    d = first
    while d <= last:
        for t, m in zip(RUN_SLOTS_UTC, _slot_minutes(), strict=True):
            if (d, m) not in seen:
                out.append({"date": d, "slot_utc": t.strftime("%H:%M")})
        d += timedelta(days=1)
    return out


def period_completeness(actuals: pl.DataFrame, first: date, last: date) -> pl.DataFrame:
    """Observed vs expected settlement periods per day (clock-change aware)."""
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    expected = pl.DataFrame(
        {
            "settlement_date": days,
            "expected": [periods_in_day(d) for d in days],
        },
        schema={"settlement_date": pl.Date, "expected": pl.Int32},
    )
    observed = actuals.group_by("settlement_date").agg(pl.len().cast(pl.Int32).alias("observed"))
    return (
        expected.join(observed, on="settlement_date", how="left")
        .with_columns(pl.col("observed").fill_null(0))
        .with_columns((pl.col("observed") == pl.col("expected")).alias("complete"))
        .sort("settlement_date")
    )


def publication_lag(actuals: pl.DataFrame) -> dict[str, float | None]:
    lag = (actuals["publish_time"] - actuals["start_time"]).dt.total_seconds() / 60
    if lag.is_empty():
        return {"p50_min": None, "p95_min": None, "max_min": None}
    return {
        "p50_min": lag.quantile(0.5, "linear"),
        "p95_min": lag.quantile(0.95, "linear"),
        "max_min": float(lag.max()),  # type: ignore[arg-type]
    }


def implausible(frame: pl.DataFrame, col: str = "generation_mw") -> int:
    return frame.filter(pl.col(col) > PLAUSIBLE_MAX_MW).height
