"""HTTP contract tests on the real snapshot."""

from __future__ import annotations

import functools
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from windesk.api.app import create_app
from windesk.config import Settings
from windesk.services.analytics import Analytics

RANGE = "first=2026-01-02&last=2026-02-01"


def test_healthz_reports_data_version(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert len(body["data_version"]) == 12


@pytest.mark.parametrize(
    "path",
    [
        "/api/meta",
        "/api/decision?delivery_date=2026-01-15",
        "/api/decision?delivery_date=2026-01-15&auction=epex_da_30&margin_min=30",
        "/api/decision?delivery_date=2026-01-15&gate_local=11:00",
        f"/api/horizon?{RANGE}&horizon_h=12",
        f"/api/accuracy?{RANGE}&matching=on_the_hour",
        f"/api/models?{RANGE}&auction=epex_da_60",
        f"/api/ramps?{RANGE}&threshold_mw=1500",
        f"/api/quality?{RANGE}",
    ],
)
def test_every_endpoint_returns_an_enveloped_response(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"]["data_version"] == client.get("/healthz").json()["data_version"]
    assert r.headers["x-request-id"]


def test_custom_gate_overrides_auction(client: TestClient) -> None:
    d = client.get("/api/decision?delivery_date=2026-01-15&gate_local=12:00").json()["data"]
    assert d["auction"] is None
    assert d["gate_local"] == "12:00"
    assert d["run"]["publish_time"].startswith("2026-01-14T11:30")


def test_margin_moves_cutoff_earlier(client: TestClient) -> None:
    d = client.get("/api/decision?delivery_date=2026-01-15&margin_min=30").json()["data"]
    assert d["cutoff"].startswith("2026-01-14T09:20")
    assert d["run"]["publish_time"].startswith("2026-01-14T07:30")


@pytest.mark.parametrize(
    ("path", "fragment"),
    [
        ("/api/decision?delivery_date=2025-06-01", "Data covers"),
        ("/api/accuracy?first=2026-01-05&last=2026-01-02", "on or after"),
        ("/api/accuracy?first=2026-01-02&last=2026-02-01&horizon_h=99", ""),
        ("/api/decision?delivery_date=2026-01-15&auction=bogus", ""),
        ("/api/export/pairs.csv?first=2026-01-02&last=2026-01-03", "exactly one"),
    ],
)
def test_bad_requests_are_rejected_with_422(client: TestClient, path: str, fragment: str) -> None:
    r = client.get(path)
    assert r.status_code == 422
    assert fragment in r.text


def test_csv_export_is_traceable(client: TestClient) -> None:
    r = client.get("/api/export/pairs.csv?first=2026-01-02&last=2026-01-02&horizon_h=24")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    assert lines[0].startswith("# data_version=")
    assert lines[1].split(",")[:3] == ["delivery_date", "start_time", "cutoff"]
    assert len(lines) == 2 + 24
    assert r.headers["x-data-version"] in lines[0]


def test_openapi_schema_is_published(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert "/api/decision" in spec["paths"]
    assert "DecisionOut" in spec["components"]["schemas"]


def test_spa_is_served_with_history_fallback(
    tmp_path: Path, real_analytics: Analytics, real_settings: Settings
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    settings = real_settings.model_copy(update={"static_dir": tmp_path})
    with TestClient(create_app(settings, real_analytics)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/accuracy").text == "<html>app</html>"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/assets/app.js").status_code == 200
        assert c.get("/../pyproject.toml").text == "<html>app</html>"
        assert c.get("/api/meta").status_code == 200
        typo = c.get("/api/does-not-exist")  # an API typo is a JSON 404, never the SPA page
        assert typo.status_code == 404
        assert typo.headers["content-type"].startswith("application/json")


def test_revisions_lists_every_run_and_marks_the_one_used(client: TestClient) -> None:
    rev = client.get("/api/revisions?delivery_date=2026-01-15").json()["data"]
    dec = client.get("/api/decision?delivery_date=2026-01-15").json()["data"]
    publishes = [r["publish_time"] for r in rev["runs"]]
    assert publishes == sorted(publishes)
    assert rev["used_publish_time"] == dec["run"]["publish_time"]
    assert all(r["available"] == (r["publish_time"] <= rev["cutoff"]) for r in rev["runs"])
    for run in rev["runs"]:  # no point for an hour that had already started at publication
        assert all(p["start_time"] >= run["publish_time"] for p in run["points"])
    assert len(rev["actual"]) == 24


@pytest.mark.parametrize("path", ["/api/decision", "/api/revisions"])
def test_gate_dependency_is_shared(client: TestClient, path: str) -> None:
    custom = client.get(f"{path}?delivery_date=2026-01-15&gate_local=12:00").json()["meta"]
    assert custom["params"]["auction"] is None
    assert custom["params"]["gate_local"] == "12:00"
    assert client.get(f"{path}?delivery_date=2026-01-15&auction=").status_code == 422


def test_fractional_horizon_is_rejected(client: TestClient) -> None:
    # Each float would otherwise be a fresh memo key (an unbounded-memory lever).
    assert client.get(f"/api/horizon?{RANGE}&horizon_h=24.000001").status_code == 422


def test_only_successful_api_responses_are_cacheable(client: TestClient) -> None:
    ok = client.get("/api/meta")
    bad = client.get("/api/decision?delivery_date=2025-06-01")
    assert ok.headers["cache-control"] == "public, max-age=300"
    assert bad.status_code == 422
    assert "cache-control" not in bad.headers


def test_memo_is_a_bounded_lru(real_analytics: Analytics, monkeypatch: pytest.MonkeyPatch) -> None:
    import windesk.services.analytics as svc

    monkeypatch.setattr(svc, "MEMO_MAX_ENTRIES", 3)
    memo = real_analytics._memo
    saved = dict(memo)
    memo.clear()
    try:
        for i in range(10):
            real_analytics._cached(("probe", i), functools.partial(int, i))
        assert list(memo) == [("probe", 7), ("probe", 8), ("probe", 9)]
        real_analytics._cached(("probe", 7), lambda: -1)  # a hit refreshes recency
        real_analytics._cached(("probe", 10), lambda: 10)
        assert ("probe", 7) in memo
        assert ("probe", 8) not in memo
    finally:
        memo.clear()
        memo.update(saved)


def test_startup_prewarms_the_default_views(real_settings: Settings) -> None:
    with TestClient(create_app(real_settings)) as c:
        analytics: Analytics = c.app.state.analytics  # type: ignore[attr-defined]
        kinds = {key[0] for key in analytics._memo if isinstance(key, tuple)}
        assert {"accuracy", "fitted", "quality", "decision"} <= kinds


def test_security_headers_on_every_response(client: TestClient) -> None:
    for path in ("/healthz", "/api/meta", "/api/does-not-exist"):
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
