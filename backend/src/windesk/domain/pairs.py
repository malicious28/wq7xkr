"""Forecast/actual pairs: the unit every metric is computed on.

Two constructions, matching the two questions a buyer asks:

* :func:`horizon_pairs` - "how good is the forecast made H hours ahead?"
* :func:`decision_pairs` - "how good was the forecast I could see at my
  gate closure, for each delivery day?" (lead time varies across the day)

Targets come from a complete hourly grid, not from the actuals, so missing
outturn shows up as nulls instead of silently shrinking the sample.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta

import polars as pl

from windesk.domain.asof import select_asof
from windesk.domain.clock import UK, ensure_utc, local_gate_to_utc, settlement_day_bounds

PAIR_COLUMNS = (
    "delivery_date",
    "start_time",
    "cutoff",
    "publish_time",
    "lead_h",
    "forecast_mw",
    "actual_mw",
    "available_at",
)


def hourly_grid(start: datetime, end: datetime) -> pl.Series:
    """Hour starts in ``[start, end)``, UTC."""
    start, end = ensure_utc(start), ensure_utc(end)
    if end <= start:
        return pl.Series("start_time", [], dtype=pl.Datetime("us", "UTC"))
    return pl.datetime_range(
        start, end, "1h", closed="left", eager=True, time_unit="us", time_zone="UTC"
    ).alias("start_time")


def _attach(selected: pl.DataFrame, hourly_actuals: pl.DataFrame) -> pl.DataFrame:
    # Row order carries meaning (charts, tables, CSV); Polars only keeps it when asked.
    out = selected.join(
        hourly_actuals, on="start_time", how="left", maintain_order="left"
    ).with_columns(
        pl.col("start_time").dt.convert_time_zone(UK.key).dt.date().alias("delivery_date")
    )
    return out.select(PAIR_COLUMNS)


def horizon_pairs_many(
    forecasts: pl.DataFrame,
    hourly_actuals: pl.DataFrame,
    start: datetime,
    end: datetime,
    horizons: Sequence[timedelta],
) -> pl.DataFrame:
    """Pairs for several fixed horizons from one as-of join, tagged ``horizon_h``.

    One join over (target x horizon) instead of one join per horizon: the
    accuracy curve needs 49 horizons, so this is the hot path.
    """
    if any(h < timedelta(0) for h in horizons):
        msg = "horizon must be non-negative"
        raise ValueError(msg)
    grid = pl.DataFrame({"start_time": hourly_grid(start, end)})
    offsets = pl.DataFrame({"_offset": list(horizons)}, schema={"_offset": pl.Duration("us")})
    targets = (
        offsets.join(grid, how="cross", maintain_order="left_right")
        .with_columns((pl.col("start_time") - pl.col("_offset")).alias("cutoff"))
        .select("start_time", "cutoff")
    )
    return _attach(select_asof(forecasts, targets), hourly_actuals).with_columns(
        ((pl.col("start_time") - pl.col("cutoff")).dt.total_seconds() / 3600).alias("horizon_h")
    )


def horizon_pairs(
    forecasts: pl.DataFrame,
    hourly_actuals: pl.DataFrame,
    start: datetime,
    end: datetime,
    horizon: timedelta,
) -> pl.DataFrame:
    return horizon_pairs_many(forecasts, hourly_actuals, start, end, [horizon]).drop("horizon_h")


def hindsight_pairs(
    forecasts: pl.DataFrame, hourly_actuals: pl.DataFrame, start: datetime, end: datetime
) -> pl.DataFrame:
    """The *latest-ever* run for each hour, including runs published after it began.

    This is what Elexon's ``/forecast/generation/wind/latest`` serves. It is never
    used for decisions; it is reported only to show how much hindsight flatters
    a forecast that was not actually available in time.
    """
    grid = hourly_grid(start, end)
    late = pl.lit(ensure_utc(end) + timedelta(days=7)).dt.cast_time_unit("us")
    targets = pl.DataFrame({"start_time": grid}).with_columns(late.alias("cutoff"))
    return _attach(select_asof(forecasts, targets), hourly_actuals)


def decision_targets(
    delivery_days: Sequence[date], gate_local: time, margin: timedelta
) -> pl.DataFrame:
    """Hourly targets for each delivery day, all sharing that day's cutoff."""
    frames = []
    for d in delivery_days:
        day_start, day_end = settlement_day_bounds(d)
        cutoff = local_gate_to_utc(d, gate_local) - margin
        frames.append(
            pl.DataFrame({"start_time": hourly_grid(day_start, day_end)}).with_columns(
                pl.lit(cutoff.astimezone(UTC)).dt.cast_time_unit("us").alias("cutoff")
            )
        )
    if not frames:
        return pl.DataFrame(
            schema={"start_time": pl.Datetime("us", "UTC"), "cutoff": pl.Datetime("us", "UTC")}
        )
    return pl.concat(frames)


def decision_pairs(
    forecasts: pl.DataFrame,
    hourly_actuals: pl.DataFrame,
    delivery_days: Sequence[date],
    gate_local: time,
    margin: timedelta = timedelta(0),
) -> pl.DataFrame:
    targets = decision_targets(delivery_days, gate_local, margin)
    return _attach(select_asof(forecasts, targets), hourly_actuals)


def date_range(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]
