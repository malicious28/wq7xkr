"""Ramp-event verification.

A ramp is a change of at least ``threshold_mw`` over ``window_h`` hours,
measured on an hourly series: ``delta(t) = x(t + window) - x(t)``. Ramps
matter to a buyer more than average error does: a missed down-ramp is the
moment the desk is suddenly short.

Each hour where both series are defined is classified with a standard 2x2
contingency table. A forecast ramp "hits" if a forecast ramp of the same
sign starts within ``tolerance_h`` hours of the actual one, a common
allowance for small timing errors. Scores: POD (probability of detection),
FAR (false alarm ratio) and CSI (critical success index).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

import polars as pl


@dataclass(frozen=True, slots=True)
class RampConfig:
    threshold_mw: float = 2000.0
    window_h: int = 3
    tolerance_h: int = 1


def _ramp_sign(col: str, cfg: RampConfig) -> pl.Expr:
    delta = pl.col(col).shift(-cfg.window_h) - pl.col(col)
    return (
        pl.when(delta >= cfg.threshold_mw)
        .then(1)
        .when(delta <= -cfg.threshold_mw)
        .then(-1)
        .when(delta.is_not_null())
        .then(0)
        .otherwise(None)
        .cast(pl.Int8)
    )


def _near(sign_col: str, sign: int, tol: int) -> pl.Expr:
    """True if ``sign_col`` equals ``sign`` anywhere within +/- ``tol`` rows."""
    hit = (pl.col(sign_col) == sign).cast(pl.Int8).fill_null(0)
    return hit.rolling_max(window_size=2 * tol + 1, center=True, min_samples=1) == 1


def classify(series: pl.DataFrame, cfg: RampConfig) -> pl.DataFrame:
    """``series``: contiguous hourly rows with start_time, forecast_mw, actual_mw.

    Gaps break the hourly assumption, so the input is re-indexed onto a full
    hourly grid first; deltas spanning a gap come out null and are skipped.
    """
    if series.is_empty():
        return series.with_columns(
            pl.lit(None, pl.Int8).alias("actual_ramp"),
            pl.lit(None, pl.Int8).alias("forecast_ramp"),
            pl.lit(None, pl.String).alias("outcome"),
        )
    grid = pl.datetime_range(
        cast("datetime", series["start_time"].min()),
        cast("datetime", series["start_time"].max()),
        "1h",
        eager=True,
        time_unit="us",
        time_zone="UTC",
    ).alias("start_time")
    # shift() below compares neighbouring rows, so the hourly order must be kept.
    full = pl.DataFrame({"start_time": grid}).join(
        series, on="start_time", how="left", maintain_order="left"
    )
    full = full.with_columns(
        _ramp_sign("actual_mw", cfg).alias("actual_ramp"),
        _ramp_sign("forecast_mw", cfg).alias("forecast_ramp"),
    )
    tol = cfg.tolerance_h
    a, f = pl.col("actual_ramp"), pl.col("forecast_ramp")
    f_near_up, f_near_dn = _near("forecast_ramp", 1, tol), _near("forecast_ramp", -1, tol)
    a_near_up, a_near_dn = _near("actual_ramp", 1, tol), _near("actual_ramp", -1, tol)
    outcome = (
        pl.when(a.is_null() | f.is_null())
        .then(None)
        .when((a == 1) & f_near_up)
        .then(pl.lit("hit"))
        .when((a == -1) & f_near_dn)
        .then(pl.lit("hit"))
        .when(a != 0)
        .then(pl.lit("miss"))
        .when((f == 1) & ~a_near_up)
        .then(pl.lit("false_alarm"))
        .when((f == -1) & ~a_near_dn)
        .then(pl.lit("false_alarm"))
        .otherwise(pl.lit("correct_negative"))
    )
    return full.with_columns(outcome.alias("outcome"))


@dataclass(frozen=True, slots=True)
class RampScore:
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int
    pod: float | None
    far: float | None
    csi: float | None


def scores(classified: pl.DataFrame) -> RampScore:
    counts = dict(classified.drop_nulls("outcome").group_by("outcome").len().iter_rows())
    hits = int(counts.get("hit", 0))
    misses = int(counts.get("miss", 0))
    false_alarms = int(counts.get("false_alarm", 0))
    correct_neg = int(counts.get("correct_negative", 0))

    def ratio(num: int, den: int) -> float | None:
        return num / den if den else None

    return RampScore(
        hits=hits,
        misses=misses,
        false_alarms=false_alarms,
        correct_negatives=correct_neg,
        pod=ratio(hits, hits + misses),
        far=ratio(false_alarms, hits + false_alarms),
        csi=ratio(hits, hits + misses + false_alarms),
    )


def events(classified: pl.DataFrame, cfg: RampConfig) -> pl.DataFrame:
    """Actual ramp starts (first hour of each run of same-sign ramp hours)."""
    rows = classified.filter(pl.col("actual_ramp").is_in([-1, 1]))
    if rows.is_empty():
        return rows.select("start_time", "actual_ramp", "outcome").with_columns(
            pl.lit(None, pl.Float64).alias("delta_mw")
        )
    starts = classified.with_columns(
        (pl.col("actual_mw").shift(-cfg.window_h) - pl.col("actual_mw")).alias("delta_mw"),
        (pl.col("actual_ramp") != pl.col("actual_ramp").shift(1)).fill_null(True).alias("_new"),
    ).filter(pl.col("actual_ramp").is_in([-1, 1]) & pl.col("_new"))
    return starts.select("start_time", "actual_ramp", "delta_mw", "outcome")
