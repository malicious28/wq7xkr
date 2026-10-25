"""Read side of the warehouse: the serving Parquet tables, loaded with Polars.

``windesk build`` validates every row in DuckDB and writes the same tables as
Parquet beside the DuckDB file. The API reads only that Parquet, so DuckDB is a
build-time tool and never ships in the runtime image. Parquet stores instants
as UTC, and the frames are cast to the canonical schemas as a second check.
The dataset is small (~40k rows), so it is held in memory for the process life.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from windesk.ingest.normalize import ACTUAL_SCHEMA, FORECAST_SCHEMA
from windesk.logs import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WarehouseData:
    forecasts: pl.DataFrame
    actuals: pl.DataFrame
    issues: pl.DataFrame
    meta: dict[str, str]

    @property
    def data_version(self) -> str:
        return self.meta["data_version"]


def serving_dir(warehouse_path: Path) -> Path:
    """Where ``windesk build`` writes the serving Parquet for a given warehouse file."""
    return warehouse_path.with_name(warehouse_path.stem + ".serving")


def load_warehouse(path: Path) -> WarehouseData:
    serving = serving_dir(path)
    if not (serving / "meta.parquet").exists():
        msg = f"Warehouse not found at {serving}. Run `windesk build` first."
        raise FileNotFoundError(msg)
    forecasts = pl.read_parquet(serving / "forecasts.parquet").sort("publish_time", "start_time")
    actuals = pl.read_parquet(serving / "actuals.parquet").sort("start_time")
    meta_frame = pl.read_parquet(serving / "meta.parquet")
    data = WarehouseData(
        forecasts=forecasts.cast(FORECAST_SCHEMA),
        actuals=actuals.cast(ACTUAL_SCHEMA),
        issues=pl.read_parquet(serving / "issues.parquet"),
        meta=dict(zip(meta_frame["key"], meta_frame["value"], strict=True)),
    )
    log.info(
        "warehouse.loaded",
        data_version=data.data_version,
        forecasts=forecasts.height,
        actuals=actuals.height,
    )
    return data
