"""Raw Elexon rows -> typed, validated Polars frames.

This is the schema contract for everything downstream. Rows that violate it
are not silently dropped: each problem becomes an ``Issue`` that surfaces in
the data-quality panel, so the user can see exactly what was excluded and why.

Canonical schemas (all timestamps tz-aware UTC):

    forecasts: publish_time, start_time, generation_mw
    actuals:   start_time, settlement_date, settlement_period, publish_time, generation_mw
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl

from windesk.ingest.elexon import RawRow

UTC_DT = pl.Datetime("us", "UTC")

FORECAST_SCHEMA = pl.Schema(
    {
        "publish_time": UTC_DT,
        "start_time": UTC_DT,
        "generation_mw": pl.Float64(),
    }
)
ACTUAL_SCHEMA = pl.Schema(
    {
        "start_time": UTC_DT,
        "settlement_date": pl.Date(),
        "settlement_period": pl.Int16(),
        "publish_time": UTC_DT,
        "generation_mw": pl.Float64(),
    }
)

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class Issue:
    dataset: str
    code: str
    severity: Severity
    count: int
    detail: str


def _parse_ts(col: str) -> pl.Expr:
    return pl.col(col).str.to_datetime(time_zone="UTC", time_unit="us")


def _empty(schema: pl.Schema) -> pl.DataFrame:
    return pl.DataFrame(schema=schema)


def normalize_forecasts(rows: list[RawRow]) -> tuple[pl.DataFrame, list[Issue]]:
    issues: list[Issue] = []
    if not rows:
        return _empty(FORECAST_SCHEMA), issues

    raw = pl.DataFrame(rows, infer_schema_length=None)
    df = raw.select(
        _parse_ts("publishTime").alias("publish_time"),
        _parse_ts("startTime").alias("start_time"),
        pl.col("generation").cast(pl.Float64).alias("generation_mw"),
    )

    nulls = df.filter(pl.any_horizontal(pl.all().is_null()))
    if nulls.height:
        issues.append(
            Issue("WINDFOR", "null_fields", "warning", nulls.height, "Rows with missing fields")
        )
        df = df.drop_nulls()

    negative = df.filter(pl.col("generation_mw") < 0)
    if negative.height:
        issues.append(
            Issue(
                "WINDFOR",
                "negative_generation",
                "warning",
                negative.height,
                "Negative forecast values (excluded)",
            )
        )
        df = df.filter(pl.col("generation_mw") >= 0)

    misaligned = df.filter(pl.col("start_time").dt.minute() != 0)
    if misaligned.height:
        issues.append(
            Issue(
                "WINDFOR",
                "misaligned_start",
                "warning",
                misaligned.height,
                "Forecast points not on the hour (excluded; WINDFOR is hourly)",
            )
        )
        df = df.filter(pl.col("start_time").dt.minute() == 0)

    before = df.height
    df = df.unique(subset=["publish_time", "start_time"], keep="last", maintain_order=True)
    if dupes := before - df.height:
        issues.append(
            Issue(
                "WINDFOR",
                "duplicate_points",
                "info",
                dupes,
                "Duplicate (publish_time, start_time) pairs (last kept)",
            )
        )

    return df.sort("publish_time", "start_time").cast(FORECAST_SCHEMA), issues


def normalize_actuals(rows: list[RawRow]) -> tuple[pl.DataFrame, list[Issue]]:
    issues: list[Issue] = []
    if not rows:
        return _empty(ACTUAL_SCHEMA), issues

    raw = pl.DataFrame(rows, infer_schema_length=None)
    wrong_fuel = raw.filter(pl.col("fuelType") != "WIND")
    if wrong_fuel.height:
        issues.append(
            Issue(
                "FUELHH",
                "non_wind_rows",
                "error",
                wrong_fuel.height,
                "Non-WIND rows returned despite fuelType filter (excluded)",
            )
        )
        raw = raw.filter(pl.col("fuelType") == "WIND")

    df = raw.select(
        _parse_ts("startTime").alias("start_time"),
        pl.col("settlementDate").str.to_date().alias("settlement_date"),
        pl.col("settlementPeriod").cast(pl.Int16).alias("settlement_period"),
        _parse_ts("publishTime").alias("publish_time"),
        pl.col("generation").cast(pl.Float64).alias("generation_mw"),
    )

    nulls = df.filter(pl.any_horizontal(pl.all().is_null()))
    if nulls.height:
        issues.append(
            Issue("FUELHH", "null_fields", "warning", nulls.height, "Rows with missing fields")
        )
        df = df.drop_nulls()

    negative = df.filter(pl.col("generation_mw") < 0)
    if negative.height:
        issues.append(
            Issue(
                "FUELHH",
                "negative_generation",
                "warning",
                negative.height,
                "Negative outturn values (excluded)",
            )
        )
        df = df.filter(pl.col("generation_mw") >= 0)

    misaligned = df.filter(~pl.col("start_time").dt.minute().is_in([0, 30]))
    if misaligned.height:
        issues.append(
            Issue(
                "FUELHH",
                "misaligned_start",
                "warning",
                misaligned.height,
                "Periods not starting on :00 or :30 (excluded)",
            )
        )
        df = df.filter(pl.col("start_time").dt.minute().is_in([0, 30]))

    # Elexon occasionally republishes a period. The latest value is authoritative, but the
    # period first became *available* at its earliest publication, which is what the
    # no-look-ahead rules must use.
    before = df.height
    df = (
        df.sort("publish_time")
        .group_by("start_time", maintain_order=True)
        .agg(
            pl.col("settlement_date").last(),
            pl.col("settlement_period").last(),
            pl.col("publish_time").first(),
            pl.col("generation_mw").last(),
        )
    )
    if dupes := before - df.height:
        issues.append(
            Issue(
                "FUELHH",
                "republished_periods",
                "info",
                dupes,
                "Periods published more than once (latest kept)",
            )
        )

    return df.sort("start_time").cast(ACTUAL_SCHEMA), issues
