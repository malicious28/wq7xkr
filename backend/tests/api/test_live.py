"""Live mode ('Try now') against a simulated Elexon.

``FakeElexon`` plays both datasets from one synthetic world: the true outturn
is a smooth daily cycle, and every WINDFOR run over-forecasts it by 15 % (the
bias we measured in January). The fake honours the same request semantics as
the real API (WINDFOR by publish time, FUELHH by settlement date) and never
returns anything published after the simulated "now".
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import forecasts_frame
from windesk.api.app import create_app
from windesk.config import Settings
from windesk.domain.clock import UK
from windesk.domain.quality import RUN_SLOTS_UTC
from windesk.ingest.elexon import Chunk
from windesk.services.analytics import Analytics
from windesk.services.live import LiveService, next_run_due, refresh_due, run_slots

LIVE_START = date(2026, 10, 1)
BIAS = 1.15


def truth(t: datetime) -> float:
    hours = t.timestamp() / 3600
    return 9000 + 4000 * math.sin(2 * math.pi * hours / 24)


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeElexon:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.fail = False
        self.calls = 0

    async def __aenter__(self) -> FakeElexon:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def fetch(self, chunk: Chunk) -> list[dict[str, Any]]:
        self.calls += 1
        if self.fail:
            msg = "Elexon is down"
            raise ConnectionError(msg)
        now = self.clock()
        if chunk.dataset == "WINDFOR":
            return self._windfor(chunk, now)
        return self._fuelhh(chunk, now)

    def _windfor(self, chunk: Chunk, now: datetime) -> list[dict[str, Any]]:
        rows = []
        day = chunk.start
        while day < chunk.end:
            for slot in RUN_SLOTS_UTC:
                pub = datetime.combine(day, slot, tzinfo=UTC)
                if pub > now:
                    continue
                first = pub.replace(minute=0) + timedelta(hours=1)
                rows += [
                    {
                        "dataset": "WINDFOR",
                        "publishTime": _iso(pub),
                        "startTime": _iso(first + timedelta(hours=h)),
                        "generation": round(BIAS * truth(first + timedelta(hours=h))),
                    }
                    for h in range(48)
                ]
            day += timedelta(days=1)
        return rows

    def _fuelhh(self, chunk: Chunk, now: datetime) -> list[dict[str, Any]]:
        rows = []
        t = datetime.combine(chunk.start, time(0), tzinfo=UK).astimezone(UTC)
        stop = datetime.combine(chunk.end, time(0), tzinfo=UK).astimezone(UTC)
        while t < stop:
            published = t + timedelta(minutes=30)
            if published <= now:
                local = t.astimezone(UK)
                rows.append(
                    {
                        "dataset": "FUELHH",
                        "publishTime": _iso(published),
                        "startTime": _iso(t),
                        "settlementDate": local.date().isoformat(),
                        "settlementPeriod": local.hour * 2 + local.minute // 30 + 1,
                        "fuelType": "WIND",
                        "generation": round(truth(t)),
                    }
                )
            t += timedelta(minutes=30)
        return rows


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# 08:00 UTC = 09:00 BST on 5 Oct: before the N2EX 09:50 gate for 6 Oct.
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)


@pytest.fixture
def world() -> tuple[Clock, FakeElexon, LiveService, Settings]:
    clock = Clock(NOW)
    fake = FakeElexon(clock)
    settings = Settings(env="test", live_start=LIVE_START, trailing_days=7, log_level="WARNING")
    return clock, fake, LiveService(settings, client_factory=lambda: fake, clock=clock), settings  # type: ignore[arg-type,return-value]


@pytest.fixture
def live_client(
    world: tuple[Clock, FakeElexon, LiveService, Settings], real_analytics: Analytics
) -> TestClient:
    *_, service, settings = world
    return TestClient(create_app(settings, real_analytics, live=service))


def _summary(client: TestClient) -> dict[str, Any]:
    with client:
        resp = client.get("/api/live/summary")
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


def test_summary_covers_live_start_to_the_newest_forecast_day(live_client: TestClient) -> None:
    data = _summary(live_client)
    days = [d["delivery_date"] for d in data["days"]]
    assert days[0] == "2026-10-01"
    # The 07:30 UTC run on 5 Oct reaches 48 h ahead, i.e. into 7 Oct.
    assert days[-1] == "2026-10-07"
    assert data["status"]["live_start"] == "2026-10-01"
    assert not data["status"]["stale"]


def test_day_statuses_follow_the_outturn(live_client: TestClient) -> None:
    by_day = {d["delivery_date"]: d for d in _summary(live_client)["days"]}
    assert by_day["2026-10-04"]["status"] == "final"
    assert by_day["2026-10-05"]["status"] == "in_progress"
    assert by_day["2026-10-06"]["status"] == "upcoming"


def test_tomorrow_uses_the_newest_run_before_the_gate_has_passed(live_client: TestClient) -> None:
    tomorrow = next(d for d in _summary(live_client)["days"] if d["delivery_date"] == "2026-10-06")
    assert tomorrow["gate_passed"] is False
    # The gate has not passed, so the cutoff is capped at "now" and the run used is
    # the newest one published by then: 07:30 UTC.
    assert datetime.fromisoformat(tomorrow["cutoff"]) == NOW
    assert datetime.fromisoformat(tomorrow["run_publish_time"]) == NOW.replace(hour=7, minute=30)
    assert tomorrow["energy_windesk_mwh"] < tomorrow["energy_elexon_mwh"]
    assert tomorrow["energy_p10_mwh"] <= tomorrow["energy_windesk_mwh"]


def test_past_days_never_use_a_run_published_after_their_gate(live_client: TestClient) -> None:
    for d in _summary(live_client)["days"]:
        if d["gate_passed"]:
            assert d["run_publish_time"] <= d["cutoff"]


def test_correction_beats_a_biased_elexon_forecast(live_client: TestClient) -> None:
    board = _summary(live_client)["scoreboard"]
    assert board["n_hours"] > 0
    assert board["elexon_bias_mw"] > 0
    assert board["windesk_mae_mw"] < board["elexon_mae_mw"] * 0.2
    assert board["skill"] > 0.8


def test_day_endpoint_returns_hourly_points_and_half_hours(live_client: TestClient) -> None:
    with live_client:
        resp = live_client.get("/api/live/day?delivery_date=2026-10-04")
        missing = live_client.get("/api/live/day?delivery_date=2026-09-01")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["points"]) == 24
    assert len(data["actuals_half_hourly"]) == 48
    assert all(p["ratio_mw"] is not None for p in data["points"])
    assert missing.status_code == 422
    assert "2026-10-01" in missing.json()["detail"]


def test_data_is_cached_until_the_next_run_is_due(
    world: tuple[Clock, FakeElexon, LiveService, Settings], live_client: TestClient
) -> None:
    clock, fake, *_ = world
    _summary(live_client)
    first_calls = fake.calls
    _summary(live_client)
    assert fake.calls == first_calls  # served from memory
    clock.now = next_run_due(NOW) + timedelta(minutes=11)
    _summary(live_client)
    assert fake.calls > first_calls


def test_elexon_outage_serves_last_good_data_marked_stale(
    world: tuple[Clock, FakeElexon, LiveService, Settings], live_client: TestClient
) -> None:
    clock, fake, *_ = world
    _summary(live_client)
    fake.fail = True
    clock.now = NOW + timedelta(hours=2)
    data = _summary(live_client)
    assert data["status"]["stale"] is True
    assert data["days"]


def test_elexon_never_reached_is_a_503(
    world: tuple[Clock, FakeElexon, LiveService, Settings], live_client: TestClient
) -> None:
    world[1].fail = True
    with live_client:
        resp = live_client.get("/api/live/summary")
    assert resp.status_code == 503


def test_live_mode_can_be_disabled(real_analytics: Analytics) -> None:
    settings = Settings(env="test", live_enabled=False, log_level="WARNING")
    with TestClient(create_app(settings, real_analytics)) as c:
        assert c.get("/api/live/summary").status_code == 404


@pytest.mark.parametrize(
    ("fetched", "due"),
    [
        (datetime(2026, 10, 5, 7, 31, tzinfo=UTC), datetime(2026, 10, 5, 8, 1, tzinfo=UTC)),
        (datetime(2026, 10, 5, 9, 25, tzinfo=UTC), datetime(2026, 10, 5, 9, 40, tzinfo=UTC)),
        (datetime(2026, 10, 5, 22, 45, tzinfo=UTC), datetime(2026, 10, 5, 23, 15, tzinfo=UTC)),
    ],
)
def test_refresh_follows_the_run_schedule(fetched: datetime, due: datetime) -> None:
    assert refresh_due(fetched) == due


def test_run_slots_are_read_from_the_data() -> None:
    summer = [time(3, 30), time(8, 30)]
    pubs = [datetime.combine(date(2026, 10, d), t, tzinfo=UTC) for d in (3, 4) for t in summer]
    pubs.append(datetime(2026, 10, 4, 13, 36, tzinfo=UTC))  # a one-off run is ignored
    frame = forecasts_frame([(p, p + timedelta(hours=1), 1.0) for p in pubs])
    slots = run_slots(frame, datetime(2026, 10, 5, tzinfo=UTC))
    assert slots == tuple(summer)
    assert next_run_due(datetime(2026, 10, 5, 4, 0, tzinfo=UTC), slots) == datetime(
        2026, 10, 5, 8, 30, tzinfo=UTC
    )
    assert run_slots(frame.clear(), datetime(2026, 10, 5, tzinfo=UTC)) == RUN_SLOTS_UTC


def test_next_run_wraps_to_the_following_day() -> None:
    assert next_run_due(datetime(2026, 10, 5, 23, 0, tzinfo=UTC)) == datetime(
        2026, 10, 6, 2, 30, tzinfo=UTC
    )


def test_clock_change_day_has_25_hours(real_analytics: Analytics) -> None:
    clock = Clock(datetime(2026, 10, 25, 23, 0, tzinfo=UTC))
    fake = FakeElexon(clock)
    settings = Settings(
        env="test", live_start=date(2026, 10, 24), trailing_days=7, log_level="WARNING"
    )
    service = LiveService(settings, client_factory=lambda: fake, clock=clock)  # type: ignore[arg-type,return-value]
    with TestClient(create_app(settings, real_analytics, live=service)) as c:
        days = {d["delivery_date"]: d for d in c.get("/api/live/summary").json()["data"]["days"]}
    assert days["2026-10-25"]["hours_in_day"] == 25
    assert days["2026-10-25"]["hours_forecast"] == 25
    assert days["2026-10-26"]["hours_in_day"] == 24
