"""Matching hourly forecasts to half-hourly outturn.

WINDFOR is hourly; FUELHH is half-hourly mean power. Two rules are offered
and the active one is always shown in the UI:

* ``hour_mean`` (default): the forecast hour starting at HH:00 is compared
  with the mean of the HH:00 and HH:30 periods. This is energy-consistent:
  both sides describe the same hour's MWh. Hours with only one half are
  dropped rather than half-measured.
* ``on_the_hour``: compare with the HH:00 period only, for users who read
  WINDFOR values as point estimates at the top of the hour.

``available_at`` is when the *whole* hourly actual became known (the later
of its periods' first publications). No-look-ahead rules filter on it.
"""

from __future__ import annotations

from enum import StrEnum

import polars as pl


class MatchingRule(StrEnum):
    HOUR_MEAN = "hour_mean"
    ON_THE_HOUR = "on_the_hour"


def hourly_actuals(actuals: pl.DataFrame, rule: MatchingRule) -> pl.DataFrame:
    """Columns: start_time (hour start, UTC), actual_mw, available_at."""
    if rule is MatchingRule.ON_THE_HOUR:
        return actuals.filter(pl.col("start_time").dt.minute() == 0).select(
            "start_time",
            pl.col("generation_mw").alias("actual_mw"),
            pl.col("publish_time").alias("available_at"),
        )

    return (
        actuals.with_columns(pl.col("start_time").dt.truncate("1h").alias("hour"))
        .group_by("hour")
        .agg(
            pl.col("generation_mw").mean().alias("actual_mw"),
            pl.col("publish_time").max().alias("available_at"),
            pl.len().alias("_n"),
        )
        .filter(pl.col("_n") == 2)
        .select(pl.col("hour").alias("start_time"), "actual_mw", "available_at")
        .sort("start_time")
    )
