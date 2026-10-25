"""Forecast revisions: every run that covered a delivery day, oldest first.

Shows how the forecast for one day moved as delivery approached, and which
runs existed before the gate. Only runs published before the day ended are
included, and points for hours that had already started when a run was
published are dropped, consistent with the as-of rule (ADR 0001).
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from windesk.domain.clock import ensure_utc


def revisions(forecasts: pl.DataFrame, day_start: datetime, day_end: datetime) -> pl.DataFrame:
    """Columns: publish_time, start_time, forecast_mw for targets in ``[day_start, day_end)``."""
    day_start, day_end = ensure_utc(day_start), ensure_utc(day_end)
    return (
        forecasts.filter(
            pl.col("start_time").is_between(day_start, day_end, closed="left")
            & (pl.col("start_time") >= pl.col("publish_time"))
        )
        .select("publish_time", "start_time", pl.col("generation_mw").alias("forecast_mw"))
        .sort("publish_time", "start_time")
    )
