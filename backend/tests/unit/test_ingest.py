"""Normalisation and snapshot integrity."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.conftest import load_fixture, utc
from windesk.ingest.elexon import Chunk, month_chunks
from windesk.ingest.normalize import normalize_actuals, normalize_forecasts
from windesk.ingest.snapshot import Manifest, read_rows, write_chunk, write_manifest


def _wf(pub: str, start: str, gen: float) -> dict[str, object]:
    return {"dataset": "WINDFOR", "publishTime": pub, "startTime": start, "generation": gen}


def _fh(start: str, pub: str, gen: float, sp: int = 1, fuel: str = "WIND") -> dict[str, object]:
    return {
        "dataset": "FUELHH",
        "publishTime": pub,
        "startTime": start,
        "settlementDate": start[:10],
        "settlementPeriod": sp,
        "fuelType": fuel,
        "generation": gen,
    }


def test_recorded_windfor_fixture_normalises_cleanly() -> None:
    df, issues = normalize_forecasts(load_fixture("windfor_2026-01-15_two_runs.json"))
    assert issues == []
    assert df.height == 146  # two runs x 73 hourly points
    assert str(df.schema["start_time"]) == "Datetime(time_unit='us', time_zone='UTC')"
    assert df["publish_time"].n_unique() == 2


def test_recorded_fuelhh_fixture_normalises_cleanly() -> None:
    df, issues = normalize_actuals(load_fixture("fuelhh_wind_2026-01-15.json"))
    assert issues == []
    assert df.height == 48
    assert df["start_time"].is_sorted()
    assert df["settlement_period"].to_list() == list(range(1, 49))


def test_forecast_anomalies_become_issues_not_silent_drops() -> None:
    rows = [
        _wf("2026-01-15T09:30:00Z", "2026-01-16T00:00:00Z", 100),
        _wf("2026-01-15T09:30:00Z", "2026-01-16T00:00:00Z", 120),  # duplicate (last kept)
        _wf("2026-01-15T09:30:00Z", "2026-01-16T01:30:00Z", 100),  # misaligned
        _wf("2026-01-15T09:30:00Z", "2026-01-16T02:00:00Z", -5),  # negative
    ]
    df, issues = normalize_forecasts(rows)
    codes = {i.code: i.count for i in issues}
    assert codes == {"duplicate_points": 1, "misaligned_start": 1, "negative_generation": 1}
    assert df["generation_mw"].to_list() == [120.0]


def test_republished_period_keeps_latest_value_but_first_availability() -> None:
    rows = [
        _fh("2026-01-15T00:00:00Z", "2026-01-15T00:30:00Z", 100),
        _fh("2026-01-15T00:00:00Z", "2026-01-15T03:00:00Z", 110),
        _fh("2026-01-15T00:30:00Z", "2026-01-15T01:00:00Z", 50, sp=2, fuel="CCGT"),
    ]
    df, issues = normalize_actuals(rows)
    assert {i.code for i in issues} == {"republished_periods", "non_wind_rows"}
    row = df.row(0, named=True)
    assert row["generation_mw"] == 110.0
    assert row["publish_time"] == utc(2026, 1, 15, 0, 30)


def test_empty_inputs_produce_typed_empty_frames() -> None:
    f, _ = normalize_forecasts([])
    a, _ = normalize_actuals([])
    assert f.is_empty()
    assert a.is_empty()
    assert "generation_mw" in f.columns
    assert "settlement_period" in a.columns


def test_month_chunks_split_on_calendar_months() -> None:
    chunks = list(month_chunks("FUELHH", date(2025, 12, 15), date(2026, 2, 1)))
    assert [(c.start, c.end) for c in chunks] == [
        (date(2025, 12, 15), date(2026, 1, 1)),
        (date(2026, 1, 1), date(2026, 2, 1)),
        (date(2026, 2, 1), date(2026, 2, 2)),
    ]


def test_snapshot_bytes_and_version_are_deterministic(tmp_path: Path) -> None:
    rows = load_fixture("fuelhh_wind_2026-01-15.json")
    chunk = Chunk("FUELHH", date(2026, 1, 15), date(2026, 1, 16))
    a = write_chunk(tmp_path / "a", chunk, rows)
    b = write_chunk(tmp_path / "b", chunk, list(reversed(rows))[::-1])
    assert a.sha256 == b.sha256
    assert Manifest("x", [a]).data_version == Manifest("x", [b]).data_version


def test_tampered_snapshot_is_refused(tmp_path: Path) -> None:
    rows = load_fixture("fuelhh_wind_2026-01-15.json")
    f = write_chunk(tmp_path, Chunk("FUELHH", date(2026, 1, 15), date(2026, 1, 16)), rows)
    manifest = Manifest("x", [f])
    write_manifest(tmp_path, manifest)
    assert Manifest.load(tmp_path).data_version == manifest.data_version
    assert len(read_rows(tmp_path, f)) == 48
    (tmp_path / f.path).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="does not match its manifest hash"):
        read_rows(tmp_path, f)
