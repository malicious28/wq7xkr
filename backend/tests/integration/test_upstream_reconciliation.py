"""Reconcile the snapshot against Elexon's own server-side forecast views.

Elexon exposes per-target "earliest" and "latest" WINDFOR values
(``/forecast/generation/wind/{earliest,latest}``). They are an independent
oracle, computed by the data owner, for two properties of our pipeline:

* **Completeness**: the first run that covered each hour in our snapshot must
  be the run Elexon reports as earliest, with the same value.
* **No look-ahead**: Elexon's "latest" is the newest run overall, and for every
  January hour it was published *after* the hour itself, so it is a hindsight
  series. Our selection at horizon 0 must never return those rows.

The responses are recorded fixtures, so this runs offline. The live variant is
marked ``network`` and deselected by default.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest

from tests.conftest import FIXTURES
from windesk.domain.asof import select_asof
from windesk.store.repository import WarehouseData

UTC_US = pl.Datetime("us", "UTC")


def _oracle(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "start_time": [r["startTime"] for r in rows],
            "oracle_publish": [r["publishTime"] for r in rows],
            "oracle_mw": [float(r["generation"]) for r in rows],
        }
    ).with_columns(
        pl.col("start_time").str.to_datetime(time_zone="UTC", time_unit="us"),
        pl.col("oracle_publish").str.to_datetime(time_zone="UTC", time_unit="us"),
    )


def _load(kind: str) -> pl.DataFrame:
    body = json.loads((FIXTURES / f"elexon_wind_{kind}_2026-01.json").read_text(encoding="utf-8"))
    return _oracle(body["data"] if isinstance(body, dict) else body)


def _per_target(forecasts: pl.DataFrame, pick: str) -> pl.DataFrame:
    """The earliest or latest run covering each target, from our snapshot."""
    ordered = forecasts.sort("start_time", "publish_time")
    agg = pl.first if pick == "earliest" else pl.last
    return ordered.group_by("start_time").agg(
        agg("publish_time").alias("our_publish"), agg("generation_mw").alias("our_mw")
    )


@pytest.mark.parametrize("kind", ["earliest", "latest"])
def test_snapshot_matches_elexon_server_side_vintages(real_data: WarehouseData, kind: str) -> None:
    oracle = _load(kind)
    assert oracle.height == 745
    # Runs published after the snapshot was taken cannot be in it (window edge).
    newest = real_data.forecasts["publish_time"].max()
    oracle = oracle.filter(pl.col("oracle_publish") <= newest)
    ours = _per_target(real_data.forecasts, kind)
    joined = oracle.join(ours, on="start_time", how="left")
    assert joined.height >= 740
    assert joined["our_publish"].null_count() == 0, "snapshot is missing runs Elexon has"
    mismatched = joined.filter(
        (pl.col("our_publish") != pl.col("oracle_publish"))
        | (pl.col("our_mw") != pl.col("oracle_mw"))
    )
    assert mismatched.is_empty(), mismatched.head()


def test_elexon_latest_is_hindsight_and_never_selected(real_data: WarehouseData) -> None:
    latest = _load("latest")
    assert (latest["oracle_publish"] > latest["start_time"]).all()

    targets = latest.select("start_time", pl.col("start_time").alias("cutoff"))  # horizon 0
    selected = select_asof(real_data.forecasts, targets)
    assert (selected["publish_time"] <= selected["start_time"]).all()
    leaked = selected.join(latest, on="start_time").filter(
        pl.col("publish_time") == pl.col("oracle_publish")
    )
    assert leaked.is_empty()


@pytest.mark.network
@pytest.mark.parametrize("kind", ["earliest", "latest"])
def test_recorded_fixture_still_matches_live_elexon(kind: str) -> None:
    url = f"https://data.elexon.co.uk/bmrs/api/v1/forecast/generation/wind/{kind}"
    params = {"from": "2026-01-02T00:00Z", "to": "2026-02-02T00:00Z", "format": "json"}
    resp = httpx.get(url, params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    live = _oracle(body["data"] if isinstance(body, dict) else body)
    assert live.sort("start_time").equals(_load(kind).sort("start_time"))


def test_fixture_window_covers_the_analysis_scope() -> None:
    oracle = _load("earliest")
    first, last = oracle["start_time"].min(), oracle["start_time"].max()
    assert isinstance(first, datetime)
    assert isinstance(last, datetime)
    assert first.date().isoformat() == "2026-01-02"
    assert last.date().isoformat() == "2026-02-02"
    assert Path(FIXTURES).is_dir()
