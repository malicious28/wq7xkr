"""Request-scoped dependencies and shared query parameters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status

from windesk.api.schemas import Envelope, ResponseMeta
from windesk.domain.auctions import AUCTIONS, DEFAULT_AUCTION, AuctionId
from windesk.domain.matching import MatchingRule
from windesk.services.analytics import Analytics


def get_analytics(request: Request) -> Analytics:
    analytics: Analytics = request.app.state.analytics
    return analytics


AnalyticsDep = Annotated[Analytics, Depends(get_analytics)]

FirstDay = Annotated[date, Query(description="First delivery day (UK local), inclusive")]
LastDay = Annotated[date, Query(description="Last delivery day (UK local), inclusive")]
Matching = Annotated[MatchingRule, Query(description="Hourly matching rule")]
HorizonH = Annotated[int, Query(ge=0, le=48, description="Forecast horizon in hours")]

MAX_RANGE_DAYS = 92


@dataclass(frozen=True, slots=True)
class Gate:
    """The decision gate: an auction preset, or a custom UK-local time (auction is then None)."""

    time: time
    auction: AuctionId | None


def resolve_gate(
    auction: Annotated[AuctionId | None, Query()] = DEFAULT_AUCTION,
    gate_local: Annotated[
        time | None, Query(description="Custom gate time HH:MM (UK local, D-1); overrides auction")
    ] = None,
) -> Gate:
    if gate_local is not None:
        return Gate(gate_local.replace(second=0, microsecond=0, tzinfo=None), None)
    if auction is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide an auction or a custom gate_local"
        )
    return Gate(AUCTIONS[auction].gate_local, auction)


GateDep = Annotated[Gate, Depends(resolve_gate)]
MarginMin = Annotated[int, Query(ge=0, le=720, description="Safety margin before gate")]


def check_range(first: date, last: date, analytics: Analytics) -> None:
    if last < first:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "last must be on or after first")
    if (last - first).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Range limited to {MAX_RANGE_DAYS} days"
        )
    a = analytics.data.actuals["settlement_date"]
    lo, hi = a.min(), a.max()
    if not (isinstance(lo, date) and isinstance(hi, date)) or first < lo or last > hi:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Data covers delivery days {lo!s} to {hi!s}"
        )


def envelope[T](data: T, analytics: Analytics, **params: Any) -> Envelope[T]:
    clean = {
        k: (
            v.value
            if hasattr(v, "value")
            else v.isoformat()
            if isinstance(v, date | datetime)
            else v
        )
        for k, v in params.items()
    }
    return Envelope[T](
        data=data,
        meta=ResponseMeta(
            data_version=analytics.data.data_version, generated_at=datetime.now(UTC), params=clean
        ),
    )
