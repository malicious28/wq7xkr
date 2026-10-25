"""Ingest pipeline: Elexon -> raw snapshot -> normalised frames -> warehouse.

Stages are deliberately separate commands:

* ``fetch`` touches the network and writes the immutable seed snapshot.
* ``build`` is offline and deterministic: snapshot in, warehouse out.

The deployed image only ever runs ``build`` against the committed snapshot,
so the demo works even if Elexon is unavailable and results are reproducible.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from windesk.ingest.elexon import ElexonClient, month_chunks
from windesk.ingest.normalize import Issue, normalize_actuals, normalize_forecasts
from windesk.ingest.snapshot import Manifest, read_rows, write_chunk, write_manifest
from windesk.logs import get_logger

log = get_logger(__name__)


async def fetch_snapshot(
    client: ElexonClient, seed_dir: Path, start: date, end_inclusive: date, *, source: str
) -> Manifest:
    """Fetch both datasets month by month and write a fresh snapshot.

    Forecasts are fetched by *publish* date. A run published on day D-2 can
    target day D, so the forecast window starts two days before ``start``
    and every target in range has its full set of candidate runs.
    """
    chunks = [
        *month_chunks("WINDFOR", start - timedelta(days=2), end_inclusive),
        *month_chunks("FUELHH", start, end_inclusive),
    ]
    results = await asyncio.gather(*(client.fetch(c) for c in chunks))
    manifest = Manifest(source=source)
    for chunk, rows in zip(chunks, results, strict=True):
        manifest.files.append(write_chunk(seed_dir, chunk, rows))
        log.info("snapshot.chunk", key=chunk.key, rows=len(rows))
    write_manifest(seed_dir, manifest)
    log.info("snapshot.done", data_version=manifest.data_version, files=len(manifest.files))
    return manifest


@dataclass(frozen=True, slots=True)
class Dataset:
    forecasts: pl.DataFrame
    actuals: pl.DataFrame
    issues: list[Issue]
    data_version: str
    fetched_at: str


def load_snapshot(seed_dir: Path) -> Dataset:
    """Read and normalise the snapshot, verifying every file hash."""
    manifest = Manifest.load(seed_dir)
    raw: dict[str, list[dict[str, object]]] = {"WINDFOR": [], "FUELHH": []}
    for f in manifest.files:
        raw[f.dataset].extend(read_rows(seed_dir, f))
    forecasts, f_issues = normalize_forecasts(raw["WINDFOR"])
    actuals, a_issues = normalize_actuals(raw["FUELHH"])
    return Dataset(
        forecasts=forecasts,
        actuals=actuals,
        issues=[*f_issues, *a_issues],
        data_version=manifest.data_version,
        fetched_at=manifest.fetched_at,
    )
