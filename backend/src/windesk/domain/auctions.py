"""GB day-ahead auction presets.

GB has run its own day-ahead auctions since leaving EU market coupling on
1 Jan 2021. The gate closure is the latest moment a buyer can act, so it
defines which forecast run was genuinely available for a decision.

Times are UK local and configurable per request; these are presets, not
truths baked into the analytics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import StrEnum


class AuctionId(StrEnum):
    N2EX_DA = "n2ex_da"
    EPEX_DA_60 = "epex_da_60"
    EPEX_DA_30 = "epex_da_30"


@dataclass(frozen=True, slots=True)
class Auction:
    id: AuctionId
    name: str
    venue: str
    product: str
    gate_local: time
    source: str
    source_quality: str


AUCTIONS: dict[AuctionId, Auction] = {
    a.id: a
    for a in (
        Auction(
            AuctionId.N2EX_DA,
            "N2EX Day-Ahead",
            "Nord Pool",
            "Hourly",
            time(9, 50),
            "https://support.nordpoolgroup.com/support/solutions/articles/8000088463",
            "primary",
        ),
        Auction(
            AuctionId.EPEX_DA_60,
            "EPEX GB Day-Ahead (60 min)",
            "EPEX SPOT",
            "Hourly",
            time(9, 20),
            "https://www.spglobal.com/commodity-insights/en/pricing-benchmarks/our-methodology/subscriber-notes/120920-platts-to-amend-uk-day-ahead-power-assessments-timing-from-jan-4",
            "secondary",
        ),
        Auction(
            AuctionId.EPEX_DA_30,
            "EPEX GB Half-Hourly Auction",
            "EPEX SPOT",
            "Half-hourly",
            time(15, 30),
            "https://www.epexspot.com/sites/default/files/download_center_files/21-03-09_Trading%20Brochure.pdf",
            "primary",
        ),
    )
}

DEFAULT_AUCTION = AuctionId.N2EX_DA
