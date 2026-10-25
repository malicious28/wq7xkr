"""Client, pipeline and warehouse against recorded Elexon responses (no network)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import httpx
import polars as pl
import pytest
import respx

from tests.conftest import load_fixture
from windesk.ingest.elexon import Chunk, ElexonClient
from windesk.ingest.pipeline import fetch_snapshot, load_snapshot
from windesk.store.repository import load_warehouse
from windesk.store.warehouse import build_warehouse

BASE = "https://elexon.test/bmrs/api/v1"


def _client() -> ElexonClient:
    return ElexonClient(BASE, max_attempts=3, timeout_s=5)


@respx.mock
async def test_client_retries_transient_errors_then_succeeds() -> None:
    route = respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("boom"),
            httpx.Response(200, json=load_fixture("fuelhh_wind_2026-01-15.json")),
        ]
    )
    async with _client() as c:
        rows = await c.fetch(Chunk("FUELHH", date(2026, 1, 15), date(2026, 1, 16)))
    assert len(rows) == 48
    assert route.call_count == 3
    params = route.calls.last.request.url.params
    assert params["settlementDateTo"] == "2026-01-15"  # inclusive upstream
    assert params["fuelType"] == "WIND"


@respx.mock
async def test_client_does_not_retry_client_errors() -> None:
    route = respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(return_value=httpx.Response(400))
    async with _client() as c:
        with pytest.raises(httpx.HTTPStatusError):
            await c.fetch(Chunk("WINDFOR", date(2026, 1, 15), date(2026, 1, 16)))
    assert route.call_count == 1


@respx.mock
async def test_client_unwraps_paged_payload_and_rejects_garbage() -> None:
    respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(
        side_effect=[
            httpx.Response(200, json={"data": load_fixture("windfor_2026-01-15_two_runs.json")}),
            httpx.Response(200, json={"data": "nope"}),
        ]
    )
    async with _client() as c:
        chunk = Chunk("WINDFOR", date(2026, 1, 15), date(2026, 1, 16))
        assert len(await c.fetch(chunk)) == 146
        with pytest.raises(TypeError, match="Unexpected payload"):
            await c.fetch(chunk)


async def test_client_rejects_unknown_dataset() -> None:
    async with _client() as c:
        with pytest.raises(ValueError, match="Unknown dataset"):
            await c.fetch(Chunk("FOO", date(2026, 1, 1), date(2026, 1, 2)))


@respx.mock
async def test_fetch_build_load_round_trip(tmp_path: Path) -> None:
    respx.get(f"{BASE}/datasets/WINDFOR/stream").mock(
        return_value=httpx.Response(200, json=load_fixture("windfor_2026-01-15_two_runs.json"))
    )
    respx.get(f"{BASE}/datasets/FUELHH/stream").mock(
        return_value=httpx.Response(200, json=load_fixture("fuelhh_wind_2026-01-15.json"))
    )
    seed = tmp_path / "seed"
    async with _client() as c:
        manifest = await fetch_snapshot(c, seed, date(2026, 1, 15), date(2026, 1, 15), source=BASE)
    assert {f.dataset for f in manifest.files} == {"WINDFOR", "FUELHH"}
    assert (seed / "manifest.json").exists()

    ds = build_warehouse(seed, tmp_path / "wh.duckdb")
    loaded = load_warehouse(tmp_path / "wh.duckdb")
    assert loaded.data_version == manifest.data_version == ds.data_version
    assert loaded.forecasts.equals(ds.forecasts)
    assert loaded.actuals.equals(ds.actuals)


def test_repository_returns_utc_even_if_duckdb_default_zone_differs(
    tmp_path: Path,
    real_settings: object,
) -> None:
    """Regression: DuckDB renders TIMESTAMPTZ in the host zone unless pinned.

    The warehouse is written with a non-UTC session zone on purpose; the
    repository must still return instants that equal the source data.
    """
    seed = Path(real_settings.seed_dir)  # type: ignore[attr-defined]
    target = tmp_path / "wh.duckdb"
    ds = build_warehouse(seed, target)
    con = duckdb.connect(str(target))
    con.execute("SET TimeZone = 'Asia/Kolkata'")
    row = con.execute("SELECT start_time::VARCHAR FROM actuals ORDER BY start_time LIMIT 1")
    rendered = row.fetchone()
    con.close()
    assert rendered is not None
    assert rendered[0].endswith("+05:30")  # DuckDB really does render in the session zone

    loaded = load_warehouse(target)
    assert loaded.actuals["start_time"].dtype == pl.Datetime("us", "UTC")
    assert loaded.actuals["start_time"][0] == ds.actuals["start_time"][0]


def test_missing_warehouse_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="windesk build"):
        load_warehouse(tmp_path / "nope.duckdb")


def test_committed_seed_loads_and_verifies(real_settings: object) -> None:
    ds = load_snapshot(Path(real_settings.seed_dir))  # type: ignore[attr-defined]
    assert ds.issues == []
    assert ds.actuals.height == 31 * 48 * 2 + 48
