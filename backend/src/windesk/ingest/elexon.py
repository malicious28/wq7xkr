"""Thin async client for the two Elexon Insights datasets we use.

Only transport concerns live here: building requests, retrying transient
failures and returning raw JSON rows. Parsing and validation happen in
``windesk.ingest.normalize`` so the client can be stubbed with recorded
fixtures in tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from windesk.logs import get_logger

log = get_logger(__name__)

RawRow = dict[str, Any]

_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


@dataclass(frozen=True, slots=True)
class Chunk:
    """One request's worth of data: a dataset over a half-open date range."""

    dataset: str
    start: date
    end: date  # exclusive

    @property
    def key(self) -> str:
        return f"{self.dataset}_{self.start.isoformat()}_{self.end.isoformat()}"


def month_chunks(dataset: str, start: date, end_inclusive: date) -> Iterator[Chunk]:
    """Split ``[start, end_inclusive]`` into calendar-month chunks.

    The ``/stream`` endpoints accept a whole month per call; monthly chunks
    keep each snapshot file small enough to diff and re-fetch independently.
    """
    cursor = start
    stop = end_inclusive + timedelta(days=1)
    while cursor < stop:
        next_month = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
        chunk_end = min(next_month, stop)
        yield Chunk(dataset, cursor, chunk_end)
        cursor = chunk_end


class ElexonClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 60.0,
        max_attempts: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_s,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "windesk/0.1"},
        )
        self._max_attempts = max_attempts

    async def __aenter__(self) -> ElexonClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _get_rows(self, path: str, params: dict[str, str]) -> list[RawRow]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential_jitter(initial=1, max=30),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                n = attempt.retry_state.attempt_number
                log.info("elexon.request", path=path, params=params, attempt=n)
                resp = await self._client.get(path, params=params)
                resp.raise_for_status()
                payload = resp.json()
        # /stream returns a bare list; paged endpoints wrap it in {"data": [...]}.
        rows = payload["data"] if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            msg = f"Unexpected payload shape from {path}: {type(rows).__name__}"
            raise TypeError(msg)
        return rows

    async def windfor(self, chunk: Chunk) -> list[RawRow]:
        """Forecast runs *published* within the chunk."""
        return await self._get_rows(
            "/datasets/WINDFOR/stream",
            {
                "publishDateTimeFrom": _utc_midnight(chunk.start),
                "publishDateTimeTo": _utc_midnight(chunk.end),
            },
        )

    async def fuelhh_wind(self, chunk: Chunk) -> list[RawRow]:
        """Half-hourly wind outturn for settlement dates within the chunk."""
        return await self._get_rows(
            "/datasets/FUELHH/stream",
            {
                "settlementDateFrom": chunk.start.isoformat(),
                # settlementDateTo is inclusive on the Elexon side.
                "settlementDateTo": (chunk.end - timedelta(days=1)).isoformat(),
                "fuelType": "WIND",
            },
        )

    async def fetch(self, chunk: Chunk) -> list[RawRow]:
        match chunk.dataset:
            case "WINDFOR":
                return await self.windfor(chunk)
            case "FUELHH":
                return await self.fuelhh_wind(chunk)
            case other:
                msg = f"Unknown dataset {other!r}"
                raise ValueError(msg)


def _utc_midnight(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
