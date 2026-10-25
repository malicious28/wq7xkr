"""Read-only analytics endpoints. Thin: validate, delegate, wrap."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from windesk.api import schemas as s
from windesk.api.deps import (
    AnalyticsDep,
    FirstDay,
    GateDep,
    HorizonH,
    LastDay,
    MarginMin,
    Matching,
    check_range,
    envelope,
)
from windesk.domain.auctions import DEFAULT_AUCTION, AuctionId
from windesk.domain.matching import MatchingRule
from windesk.domain.ramps import RampConfig

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/meta", response_model=s.Envelope[s.MetaOut])
def meta(analytics: AnalyticsDep) -> s.Envelope[s.MetaOut]:
    """Dataset coverage, version, auction presets and scope presets."""
    return envelope(analytics.meta(), analytics)


@router.get("/decision", response_model=s.Envelope[s.DecisionOut])
def decision(
    analytics: AnalyticsDep,
    delivery_date: Annotated[date, Query(description="Delivery day (UK local)")],
    gate: GateDep,
    margin_min: MarginMin = 0,
    matching: Matching = MatchingRule.HOUR_MEAN,
) -> s.Envelope[s.DecisionOut]:
    """What the desk could see at gate closure for one delivery day, with an error band."""
    check_range(delivery_date, delivery_date, analytics)
    out = analytics.decision(delivery_date, gate.time, gate.auction, margin_min, matching)
    return envelope(
        out,
        analytics,
        delivery_date=delivery_date,
        auction=gate.auction,
        gate_local=gate.time.strftime("%H:%M"),
        margin_min=margin_min,
        matching=matching,
    )


@router.get("/revisions", response_model=s.Envelope[s.RevisionsOut])
def revisions(
    analytics: AnalyticsDep,
    delivery_date: Annotated[date, Query(description="Delivery day (UK local)")],
    gate: GateDep,
    margin_min: MarginMin = 0,
    matching: Matching = MatchingRule.HOUR_MEAN,
) -> s.Envelope[s.RevisionsOut]:
    """Every forecast run that covered one delivery day, and which were available at the gate."""
    check_range(delivery_date, delivery_date, analytics)
    out = analytics.revisions(delivery_date, gate.time, margin_min, matching)
    return envelope(
        out,
        analytics,
        delivery_date=delivery_date,
        auction=gate.auction,
        gate_local=gate.time.strftime("%H:%M"),
        margin_min=margin_min,
        matching=matching,
    )


@router.get("/horizon", response_model=s.Envelope[s.HorizonOut])
def horizon(
    analytics: AnalyticsDep,
    first: FirstDay,
    last: LastDay,
    horizon_h: HorizonH = 24,
    matching: Matching = MatchingRule.HOUR_MEAN,
) -> s.Envelope[s.HorizonOut]:
    """Forecast vs actual where each forecast is the latest run made >= horizon_h earlier."""
    check_range(first, last, analytics)
    out = analytics.horizon(first, last, horizon_h, matching)
    return envelope(out, analytics, first=first, last=last, horizon_h=horizon_h, matching=matching)


@router.get("/accuracy", response_model=s.Envelope[s.AccuracyOut])
def accuracy(
    analytics: AnalyticsDep,
    first: FirstDay,
    last: LastDay,
    horizon_h: HorizonH = 24,
    matching: Matching = MatchingRule.HOUR_MEAN,
) -> s.Envelope[s.AccuracyOut]:
    """Error by horizon, hour, wind level and day."""
    check_range(first, last, analytics)
    out = analytics.accuracy(first, last, horizon_h, matching)
    return envelope(out, analytics, first=first, last=last, horizon_h=horizon_h, matching=matching)


@router.get("/models", response_model=s.Envelope[s.ModelsOut])
def models(
    analytics: AnalyticsDep,
    first: FirstDay,
    last: LastDay,
    auction: AuctionId = DEFAULT_AUCTION,
    matching: Matching = MatchingRule.HOUR_MEAN,
) -> s.Envelope[s.ModelsOut]:
    """Out-of-sample skill of bias corrections and baselines at an auction's gate."""
    check_range(first, last, analytics)
    out = analytics.models(first, last, auction, matching)
    return envelope(out, analytics, first=first, last=last, auction=auction, matching=matching)


@router.get("/ramps", response_model=s.Envelope[s.RampsOut])
def ramps(
    analytics: AnalyticsDep,
    first: FirstDay,
    last: LastDay,
    horizon_h: HorizonH = 24,
    threshold_mw: Annotated[float, Query(gt=0, le=10_000)] = 2000,
    window_h: Annotated[int, Query(ge=1, le=12)] = 3,
    tolerance_h: Annotated[int, Query(ge=0, le=6)] = 1,
    matching: Matching = MatchingRule.HOUR_MEAN,
) -> s.Envelope[s.RampsOut]:
    """Ramp-event detection: hits, misses and false alarms."""
    check_range(first, last, analytics)
    cfg = RampConfig(threshold_mw=threshold_mw, window_h=window_h, tolerance_h=tolerance_h)
    out = analytics.ramps(first, last, horizon_h, matching, cfg)
    return envelope(
        out,
        analytics,
        first=first,
        last=last,
        horizon_h=horizon_h,
        threshold_mw=threshold_mw,
        window_h=window_h,
        tolerance_h=tolerance_h,
        matching=matching,
    )


@router.get("/quality", response_model=s.Envelope[s.QualityOut])
def quality(analytics: AnalyticsDep, first: FirstDay, last: LastDay) -> s.Envelope[s.QualityOut]:
    """Late/missing runs, period completeness, publication lag, ingest issues."""
    check_range(first, last, analytics)
    return envelope(analytics.quality(first, last), analytics, first=first, last=last)


@router.get(
    "/export/pairs.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_pairs(
    analytics: AnalyticsDep,
    first: FirstDay,
    last: LastDay,
    matching: Matching = MatchingRule.HOUR_MEAN,
    horizon_h: HorizonH | None = None,
    auction: AuctionId | None = None,
) -> Response:
    """The exact forecast/actual pairs behind the metrics, as CSV.

    Pass ``auction`` for gate-closure pairs (with model outputs) or
    ``horizon_h`` for fixed-horizon pairs.
    """
    check_range(first, last, analytics)
    if (auction is None) == (horizon_h is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Pass exactly one of auction or horizon_h"
        )
    frame = analytics.export_pairs(first, last, matching, horizon_h, auction)
    header = (
        f"# data_version={analytics.data.data_version} matching={matching.value} "
        f"{'auction=' + auction.value if auction else f'horizon_h={horizon_h}'}\n"
    )
    body = frame.write_csv(datetime_format="%Y-%m-%dT%H:%M:%SZ", float_precision=2)
    name = f"windesk_pairs_{first}_{last}_{auction.value if auction else f'h{horizon_h}'}.csv"
    return Response(
        header + body,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Data-Version": analytics.data.data_version,
        },
    )
