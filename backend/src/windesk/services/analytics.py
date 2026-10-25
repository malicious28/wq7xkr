"""Application service: composes the domain functions into API answers.

The service owns no maths of its own; it chooses targets, calls the pure
domain functions and shapes their output into DTOs. The underlying data is
immutable for the life of the process (one ``data_version``), so results are
memoised by their full parameter tuple.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from threading import Lock
from typing import Any, cast

import polars as pl

from windesk.api import schemas as s
from windesk.config import Settings
from windesk.domain import metrics, models, quality, ramps
from windesk.domain.auctions import AUCTIONS, AuctionId
from windesk.domain.clock import UK, local_gate_to_utc, settlement_day_bounds
from windesk.domain.matching import MatchingRule, hourly_actuals
from windesk.domain.pairs import (
    date_range,
    decision_pairs,
    hindsight_pairs,
    horizon_pairs,
    horizon_pairs_many,
)
from windesk.domain.ramps import RampConfig
from windesk.domain.revisions import revisions as day_revisions
from windesk.store.repository import WarehouseData

MAX_HORIZON_H = 48
MEMO_MAX_ENTRIES = 512
HEATMAP_HORIZONS = (0, 6, 12, 18, 24, 30, 36, 42, 48)


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


class Analytics:
    def __init__(self, data: WarehouseData, settings: Settings) -> None:
        self.data = data
        self.settings = settings
        self.capacity_mw = metrics.capacity_proxy(data.actuals)
        self._memo: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = Lock()
        self._schedule = quality.run_schedule(data.forecasts)

    # --- plumbing -----------------------------------------------------------------------

    def _cached[R](self, key: Hashable, fn: Callable[[], R]) -> R:
        # Keys come from query parameters, so the memo is a bounded LRU: a client
        # sweeping dates or gate times cannot grow memory without limit.
        with self._lock:
            if key in self._memo:
                self._memo.move_to_end(key)
                return cast("R", self._memo[key])
        value = fn()  # outside the lock: a rare duplicate compute beats serialising requests
        with self._lock:
            self._memo[key] = value
            self._memo.move_to_end(key)
            while len(self._memo) > MEMO_MAX_ENTRIES:
                self._memo.popitem(last=False)
        return value

    def hourly(self, rule: MatchingRule) -> pl.DataFrame:
        return self._cached(("hourly", rule), lambda: hourly_actuals(self.data.actuals, rule))

    @staticmethod
    def _bounds(first: date, last: date) -> tuple[datetime, datetime]:
        return settlement_day_bounds(first)[0], settlement_day_bounds(last)[1]

    def scopes(self) -> list[s.ScopePreset]:
        st = self.settings
        return [
            s.ScopePreset(
                id="decisions_jan_2026",
                label="Decisions made in January 2026",
                description="Gate closures on 1-31 Jan 2026, i.e. delivery days 2 Jan - 1 Feb.",
                delivery_first=st.decision_start + timedelta(days=1),
                delivery_last=st.decision_end + timedelta(days=1),
            ),
            s.ScopePreset(
                id="delivery_jan_2026",
                label="Delivery in January 2026",
                description="Delivery days 1-31 Jan 2026 (decisions 31 Dec - 30 Jan).",
                delivery_first=st.decision_start,
                delivery_last=st.decision_end,
            ),
        ]

    def prewarm(self) -> None:
        """Compute the default views once, so the first visitor never waits on a cold path."""
        default = self.scopes()[0]
        first, last, rule = default.delivery_first, default.delivery_last, MatchingRule.HOUR_MEAN
        self.accuracy(first, last, 24, rule)
        self.models(first, last, AuctionId.N2EX_DA, rule)
        self.quality(first, last)
        self.decision(
            date(2026, 1, 15), AUCTIONS[AuctionId.N2EX_DA].gate_local, AuctionId.N2EX_DA, 0, rule
        )

    # --- meta ---------------------------------------------------------------------------

    def meta(self) -> s.MetaOut:
        f, a, m = self.data.forecasts, self.data.actuals, self.data.meta
        return s.MetaOut(
            data_version=self.data.data_version,
            fetched_at=m.get("fetched_at", ""),
            built_at=m.get("built_at", ""),
            source=self.settings.elexon_base_url,
            forecast_runs=f["publish_time"].n_unique(),
            forecast_rows=f.height,
            actual_rows=a.height,
            forecast_publish_first=f["publish_time"].min(),
            forecast_publish_last=f["publish_time"].max(),
            actual_first=a["start_time"].min(),
            actual_last=a["start_time"].max(),
            capacity_proxy_mw=self.capacity_mw,
            auctions=[
                s.AuctionOut(
                    id=x.id,
                    name=x.name,
                    venue=x.venue,
                    product=x.product,
                    gate_local=x.gate_local.strftime("%H:%M"),
                    source=x.source,
                    source_quality=x.source_quality,
                )
                for x in AUCTIONS.values()
            ],
            scopes=self.scopes(),
            default_scope="decisions_jan_2026",
            matching_rules=list(MatchingRule),
            trailing_days=self.settings.trailing_days,
            max_horizon_h=MAX_HORIZON_H,
        )

    # --- decision view ------------------------------------------------------------------

    def _run_info(self, row: dict[str, Any], cutoff: datetime) -> s.RunInfo:
        return s.RunInfo(
            publish_time=row["publish_time"],
            points=row["points"],
            available=row["publish_time"] <= cutoff,
            late=row["late"],
            delay_min=float(row["delay_min"]),
        )

    def decision(
        self,
        delivery_date: date,
        gate_local: time,
        auction: AuctionId | None,
        margin_min: int,
        rule: MatchingRule,
    ) -> s.DecisionOut:
        key = ("decision", delivery_date, gate_local, auction, margin_min, rule)
        return self._cached(
            key, lambda: self._decision(delivery_date, gate_local, auction, margin_min, rule)
        )

    def _decision(
        self,
        delivery_date: date,
        gate_local: time,
        auction: AuctionId | None,
        margin_min: int,
        rule: MatchingRule,
    ) -> s.DecisionOut:
        margin = timedelta(minutes=margin_min)
        cutoff = local_gate_to_utc(delivery_date, gate_local) - margin
        hourly = self.hourly(rule)
        cfg = models.FitConfig(trailing_days=self.settings.trailing_days)

        history_first = delivery_date - timedelta(days=cfg.trailing_days)
        pairs = decision_pairs(
            self.data.forecasts,
            hourly,
            date_range(history_first, delivery_date),
            gate_local,
            margin,
        )
        fitted = models.fit_and_apply(pairs, hourly, [delivery_date], cfg)

        # Runs relevant to this decision: from 24 h before the cutoff to the end of delivery.
        _, day_end = settlement_day_bounds(delivery_date)
        sched = self._schedule.filter(
            pl.col("publish_time").is_between(cutoff - timedelta(hours=24), day_end)
        )
        window = [self._run_info(r, cutoff) for r in sched.iter_rows(named=True)]
        available = [r for r in window if r.available]
        chosen = available[-1] if available else None

        warnings: list[str] = []
        age_min: float | None = None
        if chosen is None:
            warnings.append("No forecast run was published before the decision cutoff.")
        else:
            age_min = (cutoff - chosen.publish_time).total_seconds() / 60
            if age_min > 6 * 60:
                warnings.append(f"Latest available run is {age_min / 60:.1f} h old at the cutoff.")
            if chosen.late:
                warnings.append(f"The selected run arrived {chosen.delay_min:.0f} min late.")
        late_missed = [
            r
            for r in window
            if not r.available
            and r.late
            and r.publish_time - timedelta(minutes=r.delay_min) <= cutoff
        ]
        warnings.extend(
            f"The run scheduled before the cutoff arrived late at "
            f"{r.publish_time.astimezone(UK):%H:%M} UK and was not usable."
            for r in late_missed
        )

        points: list[s.DecisionPoint] = []
        history_days: int | None = None
        if not fitted.is_empty():
            history_days = int(fitted["history_days"][0])
            if history_days < cfg.min_history_days:
                warnings.append(
                    f"Only {history_days} days of history before this cutoff; "
                    "error band and bias correction are unavailable."
                )
            for r in fitted.iter_rows(named=True):
                known = r["available_at"] is not None and r["available_at"] <= cutoff
                points.append(
                    s.DecisionPoint(
                        start_time=r["start_time"],
                        lead_h=_f(r["lead_h"]),
                        forecast_mw=_f(r["raw"]),
                        debiased_mw=_f(r["debiased"]),
                        ratio_mw=_f(r["ratio"]),
                        band_low_mw=_f(r["band_low"]),
                        band_high_mw=_f(r["band_high"]),
                        actual_mw=_f(r["actual_mw"]),
                        actual_known_at_cutoff=known,
                    )
                )

        day_start, _ = settlement_day_bounds(delivery_date)
        hh = self.data.actuals.filter(
            pl.col("start_time").is_between(day_start, day_end, closed="left")
        )
        day_pairs = fitted.select("forecast_mw", "actual_mw") if not fitted.is_empty() else None
        summary = None
        if day_pairs is not None and day_pairs.drop_nulls().height:
            summary = s.Summary(**asdict(metrics.summarize(day_pairs, self.capacity_mw)))

        def energy(col: str) -> float | None:
            if fitted.is_empty() or fitted[col].null_count() == fitted.height:
                return None
            return float(fitted[col].sum())  # hourly MW values sum to MWh

        return s.DecisionOut(
            delivery_date=delivery_date,
            auction=auction,
            gate_local=gate_local.strftime("%H:%M"),
            cutoff=cutoff,
            margin_min=margin_min,
            run=chosen,
            run_age_min=age_min,
            runs_in_window=window,
            newer_runs_after_cutoff=sum(1 for r in window if not r.available),
            warnings=warnings,
            history_days=history_days,
            points=points,
            actuals_half_hourly=[
                s.HalfHourActual(
                    start_time=r["start_time"],
                    settlement_period=r["settlement_period"],
                    actual_mw=r["generation_mw"],
                )
                for r in hh.iter_rows(named=True)
            ],
            energy_forecast_mwh=energy("raw"),
            energy_conservative_mwh=energy("band_low"),
            energy_actual_mwh=energy("actual_mw"),
            day_summary=summary,
        )

    # --- revisions ----------------------------------------------------------------------

    def revisions(
        self, delivery_date: date, gate_local: time, margin_min: int, rule: MatchingRule
    ) -> s.RevisionsOut:
        key = ("revisions", delivery_date, gate_local, margin_min, rule)
        return self._cached(
            key, lambda: self._revisions(delivery_date, gate_local, margin_min, rule)
        )

    def _revisions(
        self, delivery_date: date, gate_local: time, margin_min: int, rule: MatchingRule
    ) -> s.RevisionsOut:
        cutoff = local_gate_to_utc(delivery_date, gate_local) - timedelta(minutes=margin_min)
        day_start, day_end = settlement_day_bounds(delivery_date)
        frame = day_revisions(self.data.forecasts, day_start, day_end)
        runs = [
            s.RevisionRun(
                publish_time=publish,
                available=publish <= cutoff,
                points=[
                    s.RevisionPoint(start_time=t, forecast_mw=v)
                    for t, v in group.select("start_time", "forecast_mw").iter_rows()
                ],
            )
            for (publish,), group in frame.group_by("publish_time", maintain_order=True)
        ]
        available = [r.publish_time for r in runs if r.available]
        hourly = self.hourly(rule).filter(
            pl.col("start_time").is_between(day_start, day_end, closed="left")
        )
        return s.RevisionsOut(
            delivery_date=delivery_date,
            cutoff=cutoff,
            used_publish_time=available[-1] if available else None,
            runs=runs,
            actual=[
                s.ActualPoint(start_time=t, actual_mw=v)
                for t, v in hourly.select("start_time", "actual_mw").iter_rows()
            ],
        )

    # --- horizon explorer ---------------------------------------------------------------

    def _horizon_pairs(
        self, first: date, last: date, horizon_h: int, rule: MatchingRule
    ) -> pl.DataFrame:
        start, end = self._bounds(first, last)
        key = ("hpairs", first, last, horizon_h, rule)
        return self._cached(
            key,
            lambda: horizon_pairs(
                self.data.forecasts, self.hourly(rule), start, end, timedelta(hours=horizon_h)
            ),
        )

    def horizon(self, first: date, last: date, horizon_h: int, rule: MatchingRule) -> s.HorizonOut:
        key = ("horizon", first, last, horizon_h, rule)
        return self._cached(key, lambda: self._horizon(first, last, horizon_h, rule))

    def _horizon(self, first: date, last: date, horizon_h: int, rule: MatchingRule) -> s.HorizonOut:
        pairs = self._horizon_pairs(first, last, horizon_h, rule)
        return s.HorizonOut(
            horizon_h=horizon_h,
            points=[
                s.HorizonPoint(
                    start_time=r["start_time"],
                    publish_time=r["publish_time"],
                    lead_h=_f(r["lead_h"]),
                    forecast_mw=_f(r["forecast_mw"]),
                    actual_mw=_f(r["actual_mw"]),
                )
                for r in pairs.iter_rows(named=True)
            ],
            summary=s.Summary(**asdict(metrics.summarize(pairs, self.capacity_mw))),
            coverage=self._coverage(pairs),
        )

    @staticmethod
    def _coverage(pairs: pl.DataFrame) -> float:
        return 0.0 if pairs.is_empty() else 1 - pairs["forecast_mw"].null_count() / pairs.height

    # --- accuracy -----------------------------------------------------------------------

    def accuracy(
        self, first: date, last: date, horizon_h: int, rule: MatchingRule
    ) -> s.AccuracyOut:
        key = ("accuracy", first, last, horizon_h, rule)
        return self._cached(key, lambda: self._accuracy(first, last, horizon_h, rule))

    def _group_stats(self, pairs: pl.DataFrame, by: pl.Expr) -> list[s.GroupStat]:
        g = metrics.grouped(pairs, by.alias("key"), self.capacity_mw)
        return [s.GroupStat(**{**r, "key": str(r["key"])}) for r in g.iter_rows(named=True)]

    def _accuracy(
        self, first: date, last: date, horizon_h: int, rule: MatchingRule
    ) -> s.AccuracyOut:
        cap = self.capacity_mw
        start, end = self._bounds(first, last)
        every = horizon_pairs_many(
            self.data.forecasts,
            self.hourly(rule),
            start,
            end,
            [timedelta(hours=h) for h in range(MAX_HORIZON_H + 1)],
        ).with_columns(pl.col("horizon_h").cast(pl.Int32))
        by_h = metrics.grouped(every, "horizon_h", cap).join(
            every.group_by("horizon_h").agg(
                (1 - pl.col("forecast_mw").null_count() / pl.len()).alias("coverage")
            ),
            on="horizon_h",
        )
        curve = [
            s.CurvePoint(
                horizon_h=r["horizon_h"],
                n=r["n"],
                bias_mw=r["bias_mw"],
                mae_mw=r["mae_mw"],
                rmse_mw=r["rmse_mw"],
                err_p10_mw=r["err_p10_mw"],
                err_p90_mw=r["err_p90_mw"],
                coverage=r["coverage"],
            )
            for r in by_h.sort("horizon_h").iter_rows(named=True)
        ]

        local_hour = pl.col("start_time").dt.convert_time_zone(UK.key).dt.hour()
        heat_frame = metrics.grouped(
            every.filter(pl.col("horizon_h").is_in(HEATMAP_HORIZONS)).with_columns(
                local_hour.alias("hour_local")
            ),
            pl.struct("horizon_h", "hour_local").alias("cell"),
            cap,
        ).unnest("cell")
        heat = [
            s.HeatCell(
                hour_local=r["hour_local"],
                horizon_h=r["horizon_h"],
                n=r["n"],
                mae_mw=r["mae_mw"],
                bias_mw=r["bias_mw"],
            )
            for r in heat_frame.sort("horizon_h", "hour_local").iter_rows(named=True)
        ]

        pairs = self._horizon_pairs(first, last, horizon_h, rule)
        errs = metrics.with_error(pairs.drop_nulls(["forecast_mw", "actual_mw"]))
        daily = metrics.grouped(pairs, "delivery_date", cap)
        return s.AccuracyOut(
            horizon_h=horizon_h,
            summary=s.Summary(**asdict(metrics.summarize(pairs, cap))),
            hindsight=s.Summary(
                **asdict(
                    metrics.summarize(
                        hindsight_pairs(self.data.forecasts, self.hourly(rule), start, end), cap
                    )
                )
            ),
            curve=curve,
            heatmap=heat,
            heatmap_horizons=list(HEATMAP_HORIZONS),
            by_actual_level=self._group_stats(pairs, metrics.wind_level("actual_mw")),
            by_forecast_level=self._group_stats(pairs, metrics.wind_level("forecast_mw")),
            by_hour=self._group_stats(pairs, local_hour),
            error_histogram=[
                s.HistBin(**r) for r in metrics.histogram(errs["error_mw"]).iter_rows(named=True)
            ],
            daily=[
                s.DailyStat(
                    delivery_date=r["delivery_date"],
                    n=r["n"],
                    bias_mw=r["bias_mw"],
                    mae_mw=r["mae_mw"],
                    mean_actual_mw=r["mean_actual_mw"],
                )
                for r in daily.iter_rows(named=True)
            ],
            capacity_proxy_mw=cap,
        )

    # --- models -------------------------------------------------------------------------

    def _fitted(
        self, first: date, last: date, auction: AuctionId, rule: MatchingRule
    ) -> pl.DataFrame:
        def build() -> pl.DataFrame:
            cfg = models.FitConfig(trailing_days=self.settings.trailing_days)
            gate = AUCTIONS[auction].gate_local
            days = date_range(first - timedelta(days=cfg.trailing_days), last)
            pairs = decision_pairs(self.data.forecasts, self.hourly(rule), days, gate)
            return models.fit_and_apply(pairs, self.hourly(rule), date_range(first, last), cfg)

        return self._cached(("fitted", first, last, auction, rule), build)

    def models(
        self, first: date, last: date, auction: AuctionId, rule: MatchingRule
    ) -> s.ModelsOut:
        fitted = self._fitted(first, last, auction, rule)
        scores = models.model_scores(fitted)
        band = models.band_coverage(fitted)
        daily = (
            fitted.drop_nulls(["actual_mw", "debiased", "ratio"])
            .group_by("delivery_date")
            .agg(
                (pl.col("raw") - pl.col("actual_mw")).abs().mean().alias("raw_mae_mw"),
                (pl.col("debiased") - pl.col("actual_mw")).abs().mean().alias("debiased_mae_mw"),
                (pl.col("ratio") - pl.col("actual_mw")).abs().mean().alias("ratio_mae_mw"),
                (pl.col("raw") - pl.col("actual_mw")).mean().alias("raw_bias_mw"),
            )
            .sort("delivery_date")
        )
        return s.ModelsOut(
            auction=auction,
            scores=[s.ModelScore(**r) for r in scores.iter_rows(named=True)],
            band=s.BandCoverage(nominal=0.8, **band),
            daily=[s.DailyModelError(**r) for r in daily.iter_rows(named=True)],
            trailing_days=self.settings.trailing_days,
        )

    # --- ramps --------------------------------------------------------------------------

    def ramps(
        self, first: date, last: date, horizon_h: int, rule: MatchingRule, cfg: RampConfig
    ) -> s.RampsOut:
        key = ("ramps", first, last, horizon_h, rule, cfg)
        return self._cached(key, lambda: self._ramps(first, last, horizon_h, rule, cfg))

    def _ramps(
        self, first: date, last: date, horizon_h: int, rule: MatchingRule, cfg: RampConfig
    ) -> s.RampsOut:
        pairs = self._horizon_pairs(first, last, horizon_h, rule)
        classified = ramps.classify(pairs.select("start_time", "forecast_mw", "actual_mw"), cfg)
        ev = ramps.events(classified, cfg)
        return s.RampsOut(
            horizon_h=horizon_h,
            threshold_mw=cfg.threshold_mw,
            window_h=cfg.window_h,
            tolerance_h=cfg.tolerance_h,
            scores=s.RampScores(**asdict(ramps.scores(classified))),
            events=[
                s.RampEvent(
                    start_time=r["start_time"],
                    direction="up" if r["actual_ramp"] == 1 else "down",
                    delta_mw=_f(r["delta_mw"]),
                    outcome=r["outcome"],
                )
                for r in ev.iter_rows(named=True)
            ],
        )

    # --- quality ------------------------------------------------------------------------

    def quality(self, first: date, last: date) -> s.QualityOut:
        return self._cached(("quality", first, last), lambda: self._quality(first, last))

    def _quality(self, first: date, last: date) -> s.QualityOut:
        f, a = self.data.forecasts, self.data.actuals
        start, end = self._bounds(first, last)
        sched = self._schedule.filter(pl.col("publish_time").is_between(start, end, closed="left"))
        completeness = quality.period_completeness(a, first, last)
        return s.QualityOut(
            runs_total=sched.height,
            runs_per_day_expected=len(quality.RUN_SLOTS_UTC),
            late_runs=[
                s.LateRun(
                    publish_time=r["publish_time"],
                    slot_utc=f"{r['slot_min'] // 60:02d}:{r['slot_min'] % 60:02d}",
                    delay_min=float(r["delay_min"]),
                )
                for r in sched.filter(pl.col("late")).iter_rows(named=True)
            ],
            missing_runs=[
                {"date": str(m["date"]), "slot_utc": str(m["slot_utc"])}
                for m in quality.missing_runs(sched, first, last)
            ],
            short_runs=int(sched["short"].sum()),
            points_per_run_expected=quality.EXPECTED_POINTS,
            period_completeness=[
                s.DayCompleteness(**r) for r in completeness.iter_rows(named=True)
            ],
            incomplete_days=int((~completeness["complete"]).sum()),
            actual_publication_lag=quality.publication_lag(a),
            implausible_values=quality.implausible(f) + quality.implausible(a),
            ingest_issues=[s.IssueOut(**r) for r in self.data.issues.iter_rows(named=True)],
            past_target_rows=f.filter(pl.col("start_time") < pl.col("publish_time")).height,
        )

    # --- export -------------------------------------------------------------------------

    def export_pairs(
        self,
        first: date,
        last: date,
        rule: MatchingRule,
        horizon_h: int | None,
        auction: AuctionId | None,
    ) -> pl.DataFrame:
        if auction is not None:
            frame = self._fitted(first, last, auction, rule)
            cols = [
                "delivery_date",
                "start_time",
                "cutoff",
                "publish_time",
                "lead_h",
                "forecast_mw",
                "actual_mw",
                "available_at",
                "debiased",
                "ratio",
                "persistence",
                "band_low",
                "band_high",
                "history_days",
            ]
            frame = frame.select(cols)
        else:
            frame = self._horizon_pairs(first, last, horizon_h or 0, rule)
        return frame.with_columns((pl.col("forecast_mw") - pl.col("actual_mw")).alias("error_mw"))
