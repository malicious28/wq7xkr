"""Live endpoints ('Try now'): the same method on recent Elexon data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request, status

from windesk.api import schemas as s
from windesk.api.deps import AnalyticsDep, envelope
from windesk.domain.auctions import AUCTIONS, DEFAULT_AUCTION, AuctionId
from windesk.domain.clock import settlement_day_bounds
from windesk.services.live import (
    LiveData,
    LiveService,
    LiveUnavailableError,
    day_status,
    energy,
    mae,
    refresh_due,
    score,
    scoreboard_frame,
)

router = APIRouter(prefix="/api/live", tags=["live"])

AuctionQuery = Annotated[AuctionId, Query(description="Auction whose gate sets the decision")]


def _service(request: Request) -> LiveService:
    live: LiveService | None = getattr(request.app.state, "live", None)
    if live is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Live mode is disabled")
    return live


async def _load(
    request: Request, auction: AuctionId
) -> tuple[LiveService, LiveData, bool, pl.DataFrame]:
    live = _service(request)
    try:
        data, stale, fitted = await live.fitted(auction)
    except LiveUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Live Elexon data is temporarily unavailable; try again shortly.",
        ) from exc
    return live, data, stale, fitted


def _status(live: LiveService, data: LiveData, stale: bool, auction: AuctionId) -> s.LiveStatus:
    newest_run = data.forecasts["publish_time"].max()
    newest_actual = data.actuals["start_time"].max()
    return s.LiveStatus(
        fetched_at=data.fetched_at,
        newest_run=newest_run if isinstance(newest_run, datetime) else None,
        newest_actual=newest_actual if isinstance(newest_actual, datetime) else None,
        next_refresh=refresh_due(data.fetched_at, data.run_slots),
        stale=stale,
        auction=auction,
        gate_local=AUCTIONS[auction].gate_local.strftime("%H:%M"),
        live_start=live.settings.live_start,
    )


def _day(day: pl.DataFrame, d: date, fetched_at: datetime) -> s.LiveDay:
    cutoff = day["cutoff"][0]
    publish = day["publish_time"].max()
    start, end = settlement_day_bounds(d)
    return s.LiveDay(
        delivery_date=d,
        cutoff=cutoff,
        gate_passed=cutoff < fetched_at,
        run_publish_time=publish if isinstance(publish, datetime) else None,
        status=day_status(day),
        hours_in_day=int((end - start).total_seconds() // 3600),
        hours_forecast=day["raw"].drop_nulls().len(),
        hours_actual=day["actual_mw"].drop_nulls().len(),
        elexon_mae_mw=mae(day, "raw"),
        windesk_mae_mw=mae(day, "ratio"),
        energy_elexon_mwh=energy(day, "raw"),
        energy_windesk_mwh=energy(day, "ratio"),
        energy_p10_mwh=energy(day, "band_low"),
        energy_actual_mwh=energy(day, "actual_mw"),
    )


@router.get("/summary", response_model=s.Envelope[s.LiveSummaryOut])
async def live_summary(
    request: Request, analytics: AnalyticsDep, auction: AuctionQuery = DEFAULT_AUCTION
) -> s.Envelope[s.LiveSummaryOut]:
    """Every day since live_start: Elexon at the gate, Windesk's correction, and the outturn."""
    live, data, stale, fitted = await _load(request, auction)
    days = [
        _day(fitted.filter(pl.col("delivery_date") == d), d, data.fetched_at)
        for d in fitted["delivery_date"].unique().sort().to_list()
    ]
    out = s.LiveSummaryOut(
        status=_status(live, data, stale, auction),
        days=days,
        scoreboard=s.LiveScore.model_validate(score(scoreboard_frame(fitted))),
    )
    return envelope(out, analytics, auction=auction, live_start=live.settings.live_start)


@router.get("/day", response_model=s.Envelope[s.LiveDayOut])
async def live_day(
    request: Request,
    analytics: AnalyticsDep,
    delivery_date: Annotated[date, Query(description="Delivery day (UK local)")],
    auction: AuctionQuery = DEFAULT_AUCTION,
) -> s.Envelope[s.LiveDayOut]:
    """One live delivery day, hour by hour, in the same shape as the Decision view."""
    live, data, stale, fitted = await _load(request, auction)
    day = fitted.filter(pl.col("delivery_date") == delivery_date)
    if day.is_empty():
        first = live.settings.live_start
        last = fitted["delivery_date"].max()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Live data covers delivery days {first} to {last!s}",
        )
    start, end = settlement_day_bounds(delivery_date)
    hh = data.actuals.filter(pl.col("start_time").is_between(start, end, closed="left"))
    points = [
        s.DecisionPoint(
            start_time=r["start_time"],
            lead_h=r["lead_h"],
            forecast_mw=r["raw"],
            debiased_mw=r["debiased"],
            ratio_mw=r["ratio"],
            band_low_mw=r["band_low"],
            band_high_mw=r["band_high"],
            actual_mw=r["actual_mw"],
            actual_known_at_cutoff=r["available_at"] is not None
            and r["available_at"] <= r["cutoff"],
        )
        for r in day.iter_rows(named=True)
    ]
    out = s.LiveDayOut(
        status=_status(live, data, stale, auction),
        day=_day(day, delivery_date, data.fetched_at),
        points=points,
        actuals_half_hourly=[
            s.HalfHourActual(
                start_time=r["start_time"],
                settlement_period=r["settlement_period"],
                actual_mw=r["generation_mw"],
            )
            for r in hh.iter_rows(named=True)
        ],
    )
    return envelope(out, analytics, delivery_date=delivery_date, auction=auction)
