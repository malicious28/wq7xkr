"""DuckDB warehouse: the queryable, versioned form of the snapshot.

Built offline from the seed snapshot (``windesk build``): DuckDB enforces the
schema (keys, CHECK constraints) and is the place for ad-hoc SQL. Tables:

    forecasts(publish_time, start_time, generation_mw)
    actuals(start_time, settlement_date, settlement_period, publish_time, generation_mw)
    issues(dataset, code, severity, count, detail)
    meta(key, value)            -- data_version, fetched_at, built_at, schema_version

It also writes the same tables as Parquet into ``<name>.serving/``, which is
what the API loads (see ``repository``). Both are built under temporary names
and renamed into place, so a reader never sees a half-built warehouse.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl

from windesk.ingest.pipeline import Dataset, load_snapshot
from windesk.logs import get_logger
from windesk.store.repository import serving_dir

log = get_logger(__name__)

SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE forecasts (
    publish_time  TIMESTAMPTZ NOT NULL,
    start_time    TIMESTAMPTZ NOT NULL,
    generation_mw DOUBLE      NOT NULL CHECK (generation_mw >= 0),
    PRIMARY KEY (publish_time, start_time)
);
CREATE TABLE actuals (
    start_time        TIMESTAMPTZ NOT NULL PRIMARY KEY,
    settlement_date   DATE        NOT NULL,
    settlement_period SMALLINT    NOT NULL CHECK (settlement_period BETWEEN 1 AND 50),
    publish_time      TIMESTAMPTZ NOT NULL,
    generation_mw     DOUBLE      NOT NULL CHECK (generation_mw >= 0)
);
CREATE TABLE issues (
    dataset  VARCHAR NOT NULL,
    code     VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    count    INTEGER NOT NULL,
    detail   VARCHAR NOT NULL
);
CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL);
"""


def build_warehouse(seed_dir: Path, target: Path) -> Dataset:
    ds = load_snapshot(seed_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".building")
    tmp.unlink(missing_ok=True)

    issues = pl.DataFrame(
        [asdict(i) for i in ds.issues],
        schema={
            "dataset": pl.String,
            "code": pl.String,
            "severity": pl.String,
            "count": pl.Int32,
            "detail": pl.String,
        },
    )
    meta = pl.DataFrame(
        {
            "key": ["data_version", "fetched_at", "built_at", "schema_version"],
            "value": [
                ds.data_version,
                ds.fetched_at,
                datetime.now(UTC).isoformat(timespec="seconds"),
                SCHEMA_VERSION,
            ],
        }
    )

    # The Parquet files DuckDB loads are also the serving tables: DuckDB validates
    # every row against the schema constraints, and only then are both promoted.
    # The API reads the Parquet with Polars, so DuckDB never ships at runtime.
    serving = serving_dir(target)
    staging = serving.with_name(serving.name + ".building")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    con = duckdb.connect(str(tmp))
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(_DDL)
        for name, frame in (
            ("forecasts", ds.forecasts),
            ("actuals", ds.actuals),
            ("issues", issues),
            ("meta", meta),
        ):
            parquet = staging / f"{name}.parquet"
            frame.write_parquet(parquet)
            con.execute(
                f"INSERT INTO {name} SELECT * FROM read_parquet(?)",  # noqa: S608 - fixed names
                [str(parquet)],
            )
        con.execute("CHECKPOINT")
    finally:
        con.close()

    tmp.replace(target)
    shutil.rmtree(serving, ignore_errors=True)
    staging.rename(serving)
    log.info(
        "warehouse.built",
        path=str(target),
        data_version=ds.data_version,
        forecasts=ds.forecasts.height,
        actuals=ds.actuals.height,
        issues=len(ds.issues),
    )
    return ds
