"""Out-of-sample error bands, bias correction and baselines.

Everything here is fitted *per delivery day* on history that was genuinely
available at that day's cutoff:

    history = decision pairs for earlier delivery days, within the trailing
              window, whose hourly actual was published by the cutoff.

That makes every reported coverage figure and skill score honest: no day is
ever corrected or banded using its own (or any later) outturn.

Errors are pooled by 6-hour block of the delivery day. The bias is strongly
diurnal (larger overnight), and a 6-hour block over 28 days still gives
~168 samples per quantile, against ~28 for a per-hour fit.

Models produced for every target:

* ``raw``          - WINDFOR as published
* ``debiased``     - raw minus the trailing median error of its block
* ``ratio``        - raw divided by the trailing forecast/actual energy ratio
* ``persistence``  - the latest hourly outturn known at the cutoff, held flat
* ``band_low/high``- raw minus the trailing P90/P10 error: an 80% interval
                     for the actual, centred on the debiased forecast
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

BLOCK_HOURS = 6
MODEL_NAMES = ("raw", "debiased", "ratio", "persistence")


@dataclass(frozen=True, slots=True)
class FitConfig:
    trailing_days: int = 28
    min_history_days: int = 7
    band_low_q: float = 0.1
    band_high_q: float = 0.9


def block_of(col: str = "start_time") -> pl.Expr:
    """6-hour block (0-3) of the target's UK local hour."""
    return (pl.col(col).dt.convert_time_zone("Europe/London").dt.hour() // BLOCK_HOURS).alias(
        "block"
    )


def _fit_day(history: pl.DataFrame, cfg: FitConfig) -> tuple[pl.DataFrame, float | None, int]:
    """Block-level error quantiles and the overall energy ratio from history."""
    hist = history.drop_nulls(["forecast_mw", "actual_mw"]).with_columns(
        (pl.col("forecast_mw") - pl.col("actual_mw")).alias("error_mw"), block_of()
    )
    days = hist["delivery_date"].n_unique()
    if days < cfg.min_history_days:
        return pl.DataFrame(schema={"block": pl.Int8}), None, days
    blocks = hist.group_by("block").agg(
        pl.col("error_mw").quantile(0.5, "linear").alias("err_q50"),
        pl.col("error_mw").quantile(cfg.band_low_q, "linear").alias("err_qlo"),
        pl.col("error_mw").quantile(cfg.band_high_q, "linear").alias("err_qhi"),
    )
    actual_sum = hist["actual_mw"].sum()
    ratio = float(hist["forecast_mw"].sum()) / float(actual_sum) if actual_sum > 0 else None
    return blocks, ratio, days


def _persistence(hourly_actuals: pl.DataFrame, cutoff: object) -> float | None:
    known = hourly_actuals.filter(pl.col("available_at") <= cutoff)
    if known.is_empty():
        return None
    value = known.sort("start_time")["actual_mw"][-1]
    return float(value) if value is not None else None


def fit_and_apply(
    pairs: pl.DataFrame,
    hourly_actuals: pl.DataFrame,
    days: list[date],
    cfg: FitConfig,
) -> pl.DataFrame:
    """Apply every model to the pairs of ``days`` using strictly prior history.

    ``pairs`` must contain decision pairs for the target days *and* enough
    earlier days to cover the trailing window.
    """
    out: list[pl.DataFrame] = []
    for d in days:
        today = pairs.filter(pl.col("delivery_date") == d)
        if today.is_empty():
            continue
        cutoff = today["cutoff"][0]
        history = pairs.filter(
            (pl.col("delivery_date") < d)
            & (pl.col("delivery_date") >= d - timedelta(days=cfg.trailing_days))
            & (pl.col("available_at") <= cutoff)
        )
        blocks, ratio, n_days = _fit_day(history, cfg)
        persistence = _persistence(hourly_actuals, cutoff)
        enriched = today.with_columns(block_of())
        if blocks.is_empty():
            enriched = enriched.with_columns(
                pl.lit(None, pl.Float64).alias(c) for c in ("err_q50", "err_qlo", "err_qhi")
            )
        else:
            enriched = enriched.join(blocks, on="block", how="left", maintain_order="left")
        f = pl.col("forecast_mw")
        out.append(
            enriched.with_columns(
                f.alias("raw"),
                (f - pl.col("err_q50")).alias("debiased"),
                (f / ratio if ratio else pl.lit(None, pl.Float64)).alias("ratio"),
                pl.lit(persistence, pl.Float64).alias("persistence"),
                (f - pl.col("err_qhi")).clip(lower_bound=0).alias("band_low"),
                (f - pl.col("err_qlo")).clip(lower_bound=0).alias("band_high"),
                pl.lit(n_days, pl.Int32).alias("history_days"),
            ).drop("block")
        )
    if not out:
        return pairs.head(0)
    return pl.concat(out, how="diagonal_relaxed")


def model_scores(fitted: pl.DataFrame) -> pl.DataFrame:
    """MAE/RMSE/bias per model on the rows where *all* models are defined.

    Scoring on a common sample keeps the comparison fair: a model is never
    flattered by being evaluated on easier hours.
    """
    common = fitted.drop_nulls(["actual_mw", *MODEL_NAMES])
    rows = []
    for m in MODEL_NAMES:
        err = common[m] - common["actual_mw"]
        rows.append(
            {
                "model": m,
                "n": common.height,
                "bias_mw": err.mean(),
                "mae_mw": err.abs().mean(),
                "rmse_mw": (err**2).mean() ** 0.5 if common.height else None,  # type: ignore[operator]
            }
        )
    scores = pl.DataFrame(
        rows,
        schema={
            "model": pl.String,
            "n": pl.Int64,
            "bias_mw": pl.Float64,
            "mae_mw": pl.Float64,
            "rmse_mw": pl.Float64,
        },
    )
    raw_mae = scores.filter(pl.col("model") == "raw")["mae_mw"][0]
    pers_mae = scores.filter(pl.col("model") == "persistence")["mae_mw"][0]
    return scores.with_columns(
        (1 - pl.col("mae_mw") / raw_mae).alias("skill_vs_raw"),
        (1 - pl.col("mae_mw") / pers_mae).alias("skill_vs_persistence"),
    )


def band_coverage(fitted: pl.DataFrame) -> dict[str, float | int | None]:
    banded = fitted.drop_nulls(["actual_mw", "band_low", "band_high"])
    if banded.is_empty():
        return {"n": 0, "coverage": None, "mean_width_mw": None, "below": None, "above": None}
    a = pl.col("actual_mw")
    stats = banded.select(
        pl.len().alias("n"),
        a.is_between(pl.col("band_low"), pl.col("band_high")).mean().alias("coverage"),
        (pl.col("band_high") - pl.col("band_low")).mean().alias("mean_width_mw"),
        (a < pl.col("band_low")).mean().alias("below"),
        (a > pl.col("band_high")).mean().alias("above"),
    ).row(0, named=True)
    return dict(stats)
