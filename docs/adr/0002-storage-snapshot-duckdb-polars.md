# ADR 0002: Immutable raw snapshot → DuckDB warehouse → in-memory Polars

- Status: accepted
- Date: 2026-10-25

## Context

The dataset is small: about 38k forecast rows and 3k outturn periods for December 2025 to 1 February 2026. It has to be:

1. **reproducible**: the same deploy shows the same numbers;
2. **traceable**: any figure can be traced back to the source rows;
3. **available** when Elexon is down.

## Decision

- **Ingest** (`windesk fetch`, the only networked step) stores each month's raw API response verbatim as gzipped JSON. Files are written with `mtime=0`, so identical content produces identical bytes. A manifest records SHA-256 hashes. `data_version` is a hash over those hashes and is stamped on every API response and CSV export.
- **Build** (`windesk build`, offline and deterministic) verifies every hash, normalises rows into a strict schema, and records anomalies as `issues` rather than silently dropping them. It writes a DuckDB file with primary keys and `CHECK` constraints, through a temp file and an atomic rename.
- **Serve**: the build also writes the validated tables as Parquet (`warehouse.serving/`). The API loads that Parquet into Polars once at startup and pre-warms the default views. All analytics are pure functions over those frames, memoised in a bounded LRU.
- **DuckDB is build-time only** (the `build` dependency group). The Parquet files it validates are the files the API serves, so DuckDB (65 MB) and `pyarrow` (about 150 MB) are both absent from the runtime image, and Parquet stores instants as UTC.

## Consequences

- The committed seed snapshot (about 220 KB) makes the Docker build hermetic. The image builds the warehouse at build time and never calls Elexon.
- A real bug was caught and pinned by a regression test: DuckDB renders `TIMESTAMPTZ` in the host's time zone. On the development machine (IST) every timestamp shifted by +05:30. The session is pinned to UTC, the hand-off is Parquet, and the frames are cast to the canonical schema.
- Refreshing the data is `windesk fetch && windesk build`, which produces a new `data_version`.

## Rejected

- *Postgres/TimescaleDB*: a second service to run, for 40k rows.
- *Live fetching per request*: not reproducible, and fragile when Elexon is slow or down.
- *pandas*: Polars' strict dtypes and `join_asof` with `by=` suit the as-of problem better.
