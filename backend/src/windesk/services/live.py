"""Live mode: the same method, run on recent Elexon data instead of the snapshot.

Every analysis in the app is built for the committed January snapshot. Live
mode reuses that exact pipeline (client, normalisation, as-of selection,
out-of-sample correction) on data fetched from Elexon, from ``live_start``
up to the newest forecast run, so a buyer can see tomorrow's prediction and
how the method has scored on recent days.

Freshness follows the data: WINDFOR publishes 8 runs a day and FUELHH every
half hour, so data is re-fetched once the next run should have landed (plus a
grace period, since runs can be late) or after at most 30 minutes. The run
times are read from the data rather than hard-coded: in UTC they shift by an
hour between summer and winter. If Elexon fails, the last good data keeps
being served, marked stale.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

import polars as pl

from windesk.config import Settings
from windesk.domain import models
from windesk.domain.auctions import AUCTIONS, AuctionId
from windesk.domain.clock import UK
from windesk.domain.matching import MatchingRule, hourly_actuals
from windesk.domain.pairs import date_range, decision_pairs
from windesk.domain.quality import RUN_SLOTS_UTC
from windesk.ingest.elexon import ElexonClient, month_chunks
from windesk.ingest.normalize import normalize_actuals, normalize_forecasts
from windesk.logs import get_logger

log = get_logger(__name__)

MAX_AGE = timedelta(minutes=30)
RUN_GRACE = timedelta(minutes=10)


class LiveUnavailableError(RuntimeError):
    """Elexon could not be reached and there is no earlier data to fall back on."""


@dataclass(frozen=True, slots=True)
class LiveData:
    forecasts: pl.DataFrame
    actuals: pl.DataFrame
    hourly: pl.DataFrame
    fetched_at: datetime
    run_slots: tuple[time, ...] = RUN_SLOTS_UTC


def run_slots(forecasts: pl.DataFrame, now: datetime) -> tuple[time, ...]:
    """UTC times of day at which runs were published over the last 3 days.

    A slot must appear at least twice, so one late or ad-hoc run is ignored.
    Falls back to the January schedule when there is too little data.
    """
    recent = forecasts.filter(pl.col("publish_time") > now - timedelta(days=3))
    counts = recent.select(pl.col("publish_time").unique().dt.time().alias("slot"))
    slots = counts.group_by("slot").len().filter(pl.col("len") >= 2)["slot"].sort().to_list()
    return tuple(slots) or RUN_SLOTS_UTC


def next_run_due(after: datetime, slots: tuple[time, ...] = RUN_SLOTS_UTC) -> datetime:
    """The first scheduled WINDFOR run strictly after ``after`` (UTC)."""
    after = after.astimezone(UTC)
    for days in (0, 1):
        day = after.date() + timedelta(days=days)
        for slot in sorted(slots):
            due = datetime.combine(day, slot, tzinfo=UTC)
            if due > after:
                return due
    msg = "unreachable: there is always a run within 24 h"
    raise AssertionError(msg)


def refresh_due(fetched_at: datetime, slots: tuple[time, ...] = RUN_SLOTS_UTC) -> datetime:
    """When data fetched at ``fetched_at`` should be refreshed."""
    return min(fetched_at + MAX_AGE, next_run_due(fetched_at, slots) + RUN_GRACE)


ClientFactory = Callable[[], ElexonClient]


class LiveService:
    def __init__(
        self,
        settings: Settings,
        client_factory: ClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self._client_factory = client_factory or (
            lambda: ElexonClient(
                settings.elexon_base_url,
                timeout_s=settings.http_timeout_s,
                max_attempts=settings.http_max_attempts,
            )
        )
        self.clock = clock or (lambda: datetime.now(UTC))
        self._data: LiveData | None = None
        self._fitted: dict[tuple[datetime, AuctionId], pl.DataFrame] = {}
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    @property
    def history_start(self) -> date:
        # Enough history before live_start for the trailing correction window.
        return self.settings.live_start - timedelta(days=self.settings.trailing_days + 2)

    async def get(self) -> tuple[LiveData, bool]:
        """Fresh data if possible; otherwise the last good data, flagged stale."""
        data = self._data
        if data is not None and self.clock() < refresh_due(data.fetched_at, data.run_slots):
            return data, False
        async with self._lock:  # single flight: concurrent requests share one fetch
            data = self._data
            if data is not None and self.clock() < refresh_due(data.fetched_at, data.run_slots):
                return data, False
            try:
                self._data = await self._fetch()
                self._last_error = None
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                log.warning("live.refresh_failed", error=self._last_error)
                if self._data is None:
                    raise LiveUnavailableError(self._last_error) from exc
                return self._data, True
            return self._data, False

    async def _fetch(self) -> LiveData:
        now = self.clock()
        today_uk = now.astimezone(UK).date()
        start = self.history_start
        chunks = [
            *month_chunks("WINDFOR", start - timedelta(days=2), now.date()),
            *month_chunks("FUELHH", start, today_uk),
        ]
        async with self._client_factory() as client:
            results = await asyncio.gather(*(client.fetch(c) for c in chunks))
        raw: dict[str, list[dict[str, object]]] = {"WINDFOR": [], "FUELHH": []}
        for chunk, rows in zip(chunks, results, strict=True):
            raw[chunk.dataset].extend(rows)
        forecasts, _ = normalize_forecasts(raw["WINDFOR"])
        actuals, _ = normalize_actuals(raw["FUELHH"])
        # Never treat a run "published" in the future as available (clock skew guard).
        forecasts = forecasts.filter(pl.col("publish_time") <= now)
        log.info(
            "live.refreshed",
            forecasts=forecasts.height,
            actuals=actuals.height,
            newest_run=str(forecasts["publish_time"].max()),
        )
        return LiveData(
            forecasts=forecasts,
            actuals=actuals,
            hourly=hourly_actuals(actuals, MatchingRule.HOUR_MEAN),
            fetched_at=now,
            run_slots=run_slots(forecasts, now),
        )

    async def fitted(self, auction: AuctionId) -> tuple[LiveData, bool, pl.DataFrame]:
        """Corrected decision pairs, computed once per fetch and auction.

        Results are as of the fetch time, so every request between refreshes
        sees the same numbers and the model runs once per refresh.
        """
        data, stale = await self.get()
        key = (data.fetched_at, auction)
        if key not in self._fitted:
            self._fitted = {k: v for k, v in self._fitted.items() if k[0] == data.fetched_at}
            self._fitted[key] = fit_live(
                data,
                AUCTIONS[auction].gate_local,
                data.fetched_at,
                self.settings.live_start,
                self.settings.trailing_days,
            )
        return data, stale, self._fitted[key]

    @property
    def last_error(self) -> str | None:
        return self._last_error


def last_forecast_day(data: LiveData) -> date:
    newest = data.forecasts["start_time"].max()
    if not isinstance(newest, datetime):
        msg = "no forecasts in live data"
        raise LiveUnavailableError(msg)
    return newest.astimezone(UK).date()


def fit_live(
    data: LiveData, gate: time, now: datetime, live_start: date, trailing_days: int
) -> pl.DataFrame:
    """Decision pairs for every day from ``live_start`` to the newest forecast day,
    each corrected using only what was known at min(gate, now)."""
    cfg = models.FitConfig(trailing_days=trailing_days)
    last = last_forecast_day(data)
    history_from = live_start - timedelta(days=trailing_days)
    pairs = decision_pairs(
        data.forecasts, data.hourly, date_range(history_from, last), gate, not_after=now
    )
    return models.fit_and_apply(pairs, data.hourly, date_range(live_start, last), cfg)


DayStatus = Literal["final", "in_progress", "upcoming"]


def day_status(day: pl.DataFrame) -> DayStatus:
    """final (all outturn in), in_progress, or upcoming (none yet)."""
    actual_hours = day["actual_mw"].drop_nulls().len()
    if actual_hours == 0:
        return "upcoming"
    if actual_hours < day.height:
        return "in_progress"
    return "final"


def mae(day: pl.DataFrame, col: str) -> float | None:
    both = day.drop_nulls(["actual_mw", col])
    if both.is_empty():
        return None
    return float((both[col] - both["actual_mw"]).abs().mean())  # type: ignore[arg-type]


def energy(day: pl.DataFrame, col: str) -> float | None:
    values = day[col].drop_nulls()
    return float(values.sum()) if values.len() else None  # hourly MW sum = MWh


def scoreboard_frame(fitted: pl.DataFrame) -> pl.DataFrame:
    """Hours where Elexon, Windesk and the outturn are all known."""
    return fitted.drop_nulls(["actual_mw", "raw", "ratio"])


def score(frame: pl.DataFrame) -> dict[str, float | int | None]:
    if frame.is_empty():
        return {
            "n_hours": 0,
            "elexon_mae_mw": None,
            "windesk_mae_mw": None,
            "skill": None,
            "band_coverage": None,
            "elexon_bias_mw": None,
            "windesk_bias_mw": None,
        }
    e = frame["raw"] - frame["actual_mw"]
    w = frame["ratio"] - frame["actual_mw"]
    e_mae, w_mae = float(e.abs().mean()), float(w.abs().mean())  # type: ignore[arg-type]
    banded = frame.drop_nulls(["band_low", "band_high"])
    coverage = (
        float(banded.select(pl.col("actual_mw").is_between("band_low", "band_high").mean()).item())
        if banded.height
        else None
    )
    return {
        "n_hours": frame.height,
        "elexon_mae_mw": e_mae,
        "windesk_mae_mw": w_mae,
        "skill": 1 - w_mae / e_mae if e_mae else None,
        "band_coverage": coverage,
        "elexon_bias_mw": float(e.mean()),  # type: ignore[arg-type]
        "windesk_bias_mw": float(w.mean()),  # type: ignore[arg-type]
    }
