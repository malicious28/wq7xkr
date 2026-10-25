"""Point-in-time ("as-of") forecast selection. The no-look-ahead core.

Every view in the product answers one question: *for target time T, what
did the forecast say if you could only see runs published by cutoff C?*
The rule, applied per target:

    choose the run with the greatest publish_time <= C that contains T.

Two ways of choosing C cover every use:

* fixed horizon H: ``C = T - H`` ("the forecast made at least H hours ahead")
* fixed decision: ``C = gate closure - margin`` for a whole delivery day

Both are built on :func:`select_asof`, the single implementation that the
property-based tests pin down. Because C <= T whenever H >= 0 or the gate
precedes delivery, a selected point is never one whose target had already
passed when it was published.
"""

from __future__ import annotations

import polars as pl

ASOF_COLUMNS = ("start_time", "cutoff", "publish_time", "forecast_mw", "lead_h")


def select_asof(forecasts: pl.DataFrame, targets: pl.DataFrame) -> pl.DataFrame:
    """Pick, for each ``(start_time, cutoff)`` target, the latest run published by cutoff.

    ``forecasts``: publish_time, start_time, generation_mw
    ``targets``:   start_time, cutoff (both UTC)

    Returns one row per target with ``publish_time``, ``forecast_mw`` and
    ``lead_h`` (hours from publication to target), null when no run
    published by the cutoff covers the target. Input order is preserved.
    """
    if targets.is_empty():
        return targets.with_columns(
            pl.lit(None, forecasts.schema["publish_time"]).alias("publish_time"),
            pl.lit(None, pl.Float64).alias("forecast_mw"),
            pl.lit(None, pl.Float64).alias("lead_h"),
        ).select(ASOF_COLUMNS)

    candidates = forecasts.select(
        pl.col("start_time"),
        pl.col("publish_time"),
        pl.col("generation_mw").alias("forecast_mw"),
    ).sort("start_time", "publish_time")
    left = (
        targets.select("start_time", "cutoff").with_row_index("_row").sort("start_time", "cutoff")
    )
    joined = left.join_asof(
        candidates,
        left_on="cutoff",
        right_on="publish_time",
        by="start_time",
        strategy="backward",
        check_sortedness=False,  # sorted above by (by-key, on-key)
        coalesce=False,
    )
    return (
        joined.sort("_row")
        .with_columns(
            ((pl.col("start_time") - pl.col("publish_time")).dt.total_seconds() / 3600.0).alias(
                "lead_h"
            )
        )
        .select(ASOF_COLUMNS)
    )
