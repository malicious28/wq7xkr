"""Forecast error metrics (after Madsen, Pinson, Kariniotakis et al., 2005).

Sign convention everywhere: ``error = forecast - actual`` (MW). Positive
means the forecast was too high, i.e. *less* wind turned up than expected
and the buyer would have been short.

Deliberately absent: MAPE. It divides by actual output and explodes in calm
hours. WAPE (sum |error| / sum actual) is reported for a percentage view.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True, slots=True)
class Summary:
    n: int
    bias_mw: float | None
    mae_mw: float | None
    rmse_mw: float | None
    wape: float | None
    nmae: float | None
    err_p10_mw: float | None
    err_p50_mw: float | None
    err_p90_mw: float | None
    abs_err_p90_mw: float | None
    mean_actual_mw: float | None
    mean_forecast_mw: float | None


def with_error(pairs: pl.DataFrame) -> pl.DataFrame:
    return pairs.with_columns((pl.col("forecast_mw") - pl.col("actual_mw")).alias("error_mw"))


def summary_exprs(capacity_mw: float) -> list[pl.Expr]:
    """Aggregation expressions shared by every grouped breakdown."""
    err = pl.col("error_mw")
    return [
        pl.len().alias("n"),
        err.mean().alias("bias_mw"),
        err.abs().mean().alias("mae_mw"),
        (err**2).mean().sqrt().alias("rmse_mw"),
        (err.abs().sum() / pl.col("actual_mw").sum()).alias("wape"),
        (err.abs().mean() / capacity_mw).alias("nmae"),
        err.quantile(0.1, "linear").alias("err_p10_mw"),
        err.quantile(0.5, "linear").alias("err_p50_mw"),
        err.quantile(0.9, "linear").alias("err_p90_mw"),
        err.abs().quantile(0.9, "linear").alias("abs_err_p90_mw"),
        pl.col("actual_mw").mean().alias("mean_actual_mw"),
        pl.col("forecast_mw").mean().alias("mean_forecast_mw"),
    ]


def summarize(pairs: pl.DataFrame, capacity_mw: float) -> Summary:
    """Headline statistics over complete pairs (rows with nulls are ignored)."""
    clean = with_error(pairs.drop_nulls(["forecast_mw", "actual_mw"]))
    if clean.is_empty():
        return Summary(0, *([None] * 11))
    row = clean.select(summary_exprs(capacity_mw)).row(0, named=True)
    return Summary(**row)


def grouped(pairs: pl.DataFrame, by: str | pl.Expr, capacity_mw: float) -> pl.DataFrame:
    """The same statistics broken down by a key, sorted by that key."""
    clean = with_error(pairs.drop_nulls(["forecast_mw", "actual_mw"]))
    key = by if isinstance(by, pl.Expr) else pl.col(by)
    return clean.group_by(key).agg(summary_exprs(capacity_mw)).sort(key.meta.output_name())


def capacity_proxy(actuals: pl.DataFrame) -> float:
    """Normaliser for nMAE.

    Installed capacity behind FUELHH is not published in the dataset, so the
    maximum observed half-hourly outturn stands in. The UI labels it as a
    proxy; it understates true capacity, so nMAE is conservative (too high).
    """
    peak = actuals["generation_mw"].max()
    if not isinstance(peak, int | float) or peak <= 0:
        msg = "Cannot derive a capacity proxy from empty or non-positive actuals"
        raise ValueError(msg)
    return float(peak)


WIND_LEVEL_EDGES_MW = (3000, 6000, 9000, 12000, 15000)


WIND_LEVEL_LABELS = ("0-3 GW", "3-6 GW", "6-9 GW", "9-12 GW", "12-15 GW", "15+ GW")


def wind_level(col: str = "actual_mw") -> pl.Expr:
    """Left-closed bucket label such as '6-9 GW', as an ordered Enum.

    The bucket index is the number of edges at or below the value. Written
    out explicitly rather than with ``cut`` (deprecated in Polars 2) or
    ``bin_intervals`` (experimental), so edges cannot drift with an upgrade.
    """
    value = pl.col(col)
    index = pl.sum_horizontal(*((value >= edge).cast(pl.Int8) for edge in WIND_LEVEL_EDGES_MW))
    labels = dict(enumerate(WIND_LEVEL_LABELS))
    return (
        pl.when(value.is_null())
        .then(None)
        .otherwise(index)
        .replace_strict(labels, return_dtype=pl.Enum(WIND_LEVEL_LABELS))
    )


def histogram(values: pl.Series, bin_mw: int = 500) -> pl.DataFrame:
    """Fixed-width histogram, bins aligned to multiples of ``bin_mw``."""
    clean = values.drop_nulls()
    if clean.is_empty():
        return pl.DataFrame(schema={"bin_start_mw": pl.Float64, "count": pl.UInt32})
    return (
        pl.DataFrame({"v": clean})
        .with_columns(((pl.col("v") / bin_mw).floor() * bin_mw).alias("bin_start_mw"))
        .group_by("bin_start_mw")
        .agg(pl.len().cast(pl.UInt32).alias("count"))
        .sort("bin_start_mw")
    )
