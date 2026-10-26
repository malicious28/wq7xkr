"""API contract. The frontend's TypeScript types are generated from these.

Conventions:
* Every instant is UTC (ISO-8601 with offset); the client renders it in
  Europe/London explicitly, never in the browser's zone.
* Power is MW; errors are ``forecast - actual``.
* Every response is wrapped in an :class:`Envelope` carrying the data version,
  so any number on screen can be traced to an exact snapshot.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from windesk.domain.auctions import AuctionId
from windesk.domain.matching import MatchingRule


class Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ResponseMeta(Schema):
    data_version: str = Field(description="Hash of the raw snapshot behind this response")
    generated_at: datetime
    params: dict[str, str | int | float | bool | None]


class Envelope[T](Schema):
    data: T
    meta: ResponseMeta


# --- shared -------------------------------------------------------------------------------


class Summary(Schema):
    n: int
    bias_mw: float | None
    mae_mw: float | None
    rmse_mw: float | None
    wape: float | None = Field(description="Sum |error| / sum actual")
    nmae: float | None = Field(description="MAE / capacity proxy (max observed outturn)")
    err_p10_mw: float | None
    err_p50_mw: float | None
    err_p90_mw: float | None
    abs_err_p90_mw: float | None
    mean_actual_mw: float | None
    mean_forecast_mw: float | None


class GroupStat(Summary):
    key: str


# --- meta ---------------------------------------------------------------------------------


class AuctionOut(Schema):
    id: AuctionId
    name: str
    venue: str
    product: str
    gate_local: str = Field(description="HH:MM, UK local time, on D-1")
    source: str
    source_quality: Literal["primary", "secondary"]


class ScopePreset(Schema):
    id: str
    label: str
    description: str
    delivery_first: date
    delivery_last: date


class MetaOut(Schema):
    data_version: str
    fetched_at: str
    built_at: str
    source: str
    forecast_runs: int
    forecast_rows: int
    actual_rows: int
    forecast_publish_first: datetime
    forecast_publish_last: datetime
    actual_first: datetime
    actual_last: datetime
    capacity_proxy_mw: float
    auctions: list[AuctionOut]
    scopes: list[ScopePreset]
    default_scope: str
    matching_rules: list[MatchingRule]
    trailing_days: int
    max_horizon_h: int


# --- decision view ------------------------------------------------------------------------


class RunInfo(Schema):
    publish_time: datetime
    points: int
    available: bool = Field(description="Published at or before the decision cutoff")
    late: bool
    delay_min: float


class DecisionPoint(Schema):
    start_time: datetime
    lead_h: float | None
    forecast_mw: float | None
    debiased_mw: float | None = Field(description="Raw minus trailing median error (additive)")
    ratio_mw: float | None = Field(description="Raw divided by trailing energy ratio")
    band_low_mw: float | None = Field(description="P10 of actual (conservative wind)")
    band_high_mw: float | None = Field(description="P90 of actual (optimistic wind)")
    actual_mw: float | None
    actual_known_at_cutoff: bool


class HalfHourActual(Schema):
    start_time: datetime
    settlement_period: int
    actual_mw: float


class DecisionOut(Schema):
    delivery_date: date
    auction: AuctionId | None
    gate_local: str
    cutoff: datetime
    margin_min: int
    run: RunInfo | None
    run_age_min: float | None
    runs_in_window: list[RunInfo]
    newer_runs_after_cutoff: int
    warnings: list[str]
    history_days: int | None
    points: list[DecisionPoint]
    actuals_half_hourly: list[HalfHourActual]
    energy_forecast_mwh: float | None
    energy_conservative_mwh: float | None = Field(description="Sum of hourly P10 (MWh)")
    energy_actual_mwh: float | None
    day_summary: Summary | None = Field(description="Raw forecast vs actual, once outturn is known")


# --- revisions ----------------------------------------------------------------------------


class RevisionPoint(Schema):
    start_time: datetime
    forecast_mw: float


class RevisionRun(Schema):
    publish_time: datetime
    available: bool = Field(description="Published at or before the decision cutoff")
    points: list[RevisionPoint]


class ActualPoint(Schema):
    start_time: datetime
    actual_mw: float


class RevisionsOut(Schema):
    delivery_date: date
    cutoff: datetime
    used_publish_time: datetime | None = Field(description="Newest run available at the cutoff")
    runs: list[RevisionRun] = Field(description="Every run covering the day, oldest first")
    actual: list[ActualPoint] = Field(description="Hourly outturn under the chosen matching rule")


# --- live ("Try now") -----------------------------------------------------------------------


class LiveStatus(Schema):
    fetched_at: datetime = Field(description="When Elexon was last read; results are as of then")
    newest_run: datetime | None = Field(description="Publish time of the newest WINDFOR run")
    newest_actual: datetime | None = Field(description="Start of the newest published half-hour")
    next_refresh: datetime = Field(description="When the next forecast run should have landed")
    stale: bool = Field(description="Elexon could not be reached; showing the last good data")
    auction: AuctionId
    gate_local: str
    live_start: date


class LiveDay(Schema):
    delivery_date: date
    cutoff: datetime
    gate_passed: bool = Field(description="False: the gate is still ahead, so this may update")
    run_publish_time: datetime | None
    status: Literal["final", "in_progress", "upcoming"]
    hours_in_day: int = Field(description="23, 24 or 25: clock-change days are short or long")
    hours_forecast: int
    hours_actual: int
    elexon_mae_mw: float | None
    windesk_mae_mw: float | None
    energy_elexon_mwh: float | None
    energy_windesk_mwh: float | None
    energy_p10_mwh: float | None
    energy_actual_mwh: float | None


class LiveScore(Schema):
    n_hours: int
    elexon_mae_mw: float | None
    windesk_mae_mw: float | None
    skill: float | None = Field(description="1 - Windesk MAE / Elexon MAE")
    band_coverage: float | None
    elexon_bias_mw: float | None
    windesk_bias_mw: float | None


class LiveSummaryOut(Schema):
    status: LiveStatus
    days: list[LiveDay]
    scoreboard: LiveScore


class LiveDayOut(Schema):
    status: LiveStatus
    day: LiveDay
    points: list[DecisionPoint]
    actuals_half_hourly: list[HalfHourActual]


# --- horizon explorer ---------------------------------------------------------------------


class HorizonPoint(Schema):
    start_time: datetime
    publish_time: datetime | None
    lead_h: float | None
    forecast_mw: float | None
    actual_mw: float | None


class HorizonOut(Schema):
    horizon_h: int
    points: list[HorizonPoint]
    summary: Summary
    coverage: float = Field(description="Share of target hours with a forecast at this horizon")


# --- accuracy -----------------------------------------------------------------------------


class CurvePoint(Schema):
    horizon_h: int
    n: int
    bias_mw: float | None
    mae_mw: float | None
    rmse_mw: float | None
    err_p10_mw: float | None
    err_p90_mw: float | None
    coverage: float


class HeatCell(Schema):
    hour_local: int
    horizon_h: int
    n: int
    mae_mw: float | None
    bias_mw: float | None


class HistBin(Schema):
    bin_start_mw: float
    count: int


class DailyStat(Schema):
    delivery_date: date
    n: int
    bias_mw: float | None
    mae_mw: float | None
    mean_actual_mw: float | None


class AccuracyOut(Schema):
    horizon_h: int
    summary: Summary
    hindsight: Summary = Field(
        description="The latest-ever run per hour (Elexon's 'latest'), published after the hour: "
        "what accuracy looks like with hindsight, never usable for a decision"
    )
    curve: list[CurvePoint]
    heatmap: list[HeatCell]
    heatmap_horizons: list[int]
    by_actual_level: list[GroupStat]
    by_forecast_level: list[GroupStat]
    by_hour: list[GroupStat]
    error_histogram: list[HistBin]
    daily: list[DailyStat]
    capacity_proxy_mw: float


# --- models -------------------------------------------------------------------------------


class ModelScore(Schema):
    model: Literal["raw", "debiased", "ratio", "persistence"]
    n: int
    bias_mw: float | None
    mae_mw: float | None
    rmse_mw: float | None
    skill_vs_raw: float | None
    skill_vs_persistence: float | None


class BandCoverage(Schema):
    n: int
    nominal: float
    coverage: float | None
    mean_width_mw: float | None
    below: float | None
    above: float | None


class DailyModelError(Schema):
    delivery_date: date
    raw_mae_mw: float | None
    debiased_mae_mw: float | None
    ratio_mae_mw: float | None
    raw_bias_mw: float | None


class ModelsOut(Schema):
    auction: AuctionId
    scores: list[ModelScore]
    band: BandCoverage
    daily: list[DailyModelError]
    trailing_days: int


# --- ramps --------------------------------------------------------------------------------


class RampScores(Schema):
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int
    pod: float | None
    far: float | None
    csi: float | None


class RampEvent(Schema):
    start_time: datetime
    direction: Literal["up", "down"]
    delta_mw: float | None
    outcome: str | None


class RampsOut(Schema):
    horizon_h: int
    threshold_mw: float
    window_h: int
    tolerance_h: int
    scores: RampScores
    events: list[RampEvent]


# --- quality ------------------------------------------------------------------------------


class IssueOut(Schema):
    dataset: str
    code: str
    severity: str
    count: int
    detail: str


class LateRun(Schema):
    publish_time: datetime
    slot_utc: str
    delay_min: float


class DayCompleteness(Schema):
    settlement_date: date
    expected: int
    observed: int
    complete: bool


class QualityOut(Schema):
    runs_total: int
    runs_per_day_expected: int
    late_runs: list[LateRun]
    missing_runs: list[dict[str, str]]
    short_runs: int
    points_per_run_expected: int
    period_completeness: list[DayCompleteness]
    incomplete_days: int
    actual_publication_lag: dict[str, float | None]
    implausible_values: int
    ingest_issues: list[IssueOut]
    past_target_rows: int = Field(
        description="Forecast rows whose target had already started at publication (never used)"
    )
