"""Shared fixtures.

* Small synthetic frames for unit tests, built with the canonical schemas.
* ``real_*`` fixtures build a warehouse from the committed seed snapshot in a
  temp directory, so integration and API tests run on the real January data
  without touching the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl
import pytest
from fastapi.testclient import TestClient

from windesk.api.app import create_app
from windesk.config import Settings
from windesk.ingest.normalize import ACTUAL_SCHEMA, FORECAST_SCHEMA
from windesk.services.analytics import Analytics
from windesk.store.repository import WarehouseData, load_warehouse
from windesk.store.warehouse import build_warehouse

BACKEND = Path(__file__).resolve().parents[1]
SEED = BACKEND / "data" / "seed"
FIXTURES = Path(__file__).parent / "fixtures"


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def forecasts_frame(rows: list[tuple[datetime, datetime, float]]) -> pl.DataFrame:
    """rows: (publish_time, start_time, generation_mw)."""
    return pl.DataFrame(rows, schema=list(FORECAST_SCHEMA), orient="row").cast(FORECAST_SCHEMA)


def actuals_frame(
    start: datetime, values: list[float], *, lag: timedelta = timedelta(minutes=30)
) -> pl.DataFrame:
    """Contiguous half-hourly actuals from ``start``; publication ``lag`` after period start."""
    times = [start + i * timedelta(minutes=30) for i in range(len(values))]
    return pl.DataFrame(
        {
            "start_time": times,
            "settlement_date": [t.date() for t in times],
            "settlement_period": [(t.hour * 2 + t.minute // 30) + 1 for t in times],
            "publish_time": [t + lag for t in times],
            "generation_mw": values,
        }
    ).cast(ACTUAL_SCHEMA)


def to_duck(con: duckdb.DuckDBPyConnection, name: str, frame: pl.DataFrame, tmp: Path) -> None:
    """Load a Polars frame into DuckDB as a table (via Parquet; pyarrow not required)."""
    path = tmp / f"{name}.parquet"
    frame.write_parquet(path)
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{path.as_posix()}')")


def from_duck(con: duckdb.DuckDBPyConnection, query: str, tmp: Path) -> pl.DataFrame:
    """Run a query and return a Polars frame (via Parquet; pyarrow not required)."""
    path = tmp / "result.parquet"
    con.execute(f"COPY ({query}) TO '{path.as_posix()}' (FORMAT parquet)")
    return pl.read_parquet(path)


def load_fixture(name: str) -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def real_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    tmp = tmp_path_factory.mktemp("warehouse")
    return Settings(
        env="test", seed_dir=SEED, warehouse_path=tmp / "warehouse.duckdb", log_level="WARNING"
    )


@pytest.fixture(scope="session")
def real_data(real_settings: Settings) -> WarehouseData:
    build_warehouse(real_settings.seed_dir, real_settings.warehouse_path)
    return load_warehouse(real_settings.warehouse_path)


@pytest.fixture(scope="session")
def real_analytics(real_data: WarehouseData, real_settings: Settings) -> Analytics:
    return Analytics(real_data, real_settings)


@pytest.fixture(scope="session")
def client(real_settings: Settings, real_analytics: Analytics) -> Iterator[TestClient]:
    with TestClient(create_app(real_settings, real_analytics)) as c:
        yield c
