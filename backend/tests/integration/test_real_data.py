"""Checks on the committed January 2026 snapshot.

* A differential test: DuckDB's native ASOF JOIN, an independent engine,
  must agree with the Polars as-of selection on every target.
* Golden values: the headline numbers the product presents. Any change to
  them must be deliberate (update here, explain in the commit).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import polars as pl
import pytest

from tests.conftest import from_duck, to_duck
from windesk.domain.auctions import AuctionId
from windesk.domain.matching import MatchingRule
from windesk.domain.pairs import horizon_pairs
from windesk.services.analytics import Analytics
from windesk.store.repository import WarehouseData

FIRST, LAST = date(2026, 1, 2), date(2026, 2, 1)


@pytest.mark.parametrize("horizon_h", [0, 1, 24, 48])
def test_polars_asof_agrees_with_duckdb_asof_join(
    real_data: WarehouseData, real_analytics: Analytics, horizon_h: int, tmp_path: Path
) -> None:
    hourly = real_analytics.hourly(MatchingRule.HOUR_MEAN)
    start, end = real_analytics._bounds(FIRST, LAST)
    ours = horizon_pairs(real_data.forecasts, hourly, start, end, timedelta(hours=horizon_h))

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    to_duck(con, "f", real_data.forecasts, tmp_path)
    to_duck(con, "t", ours.select("start_time", "cutoff"), tmp_path)
    theirs = from_duck(
        con,
        """
        SELECT t.start_time, f.generation_mw AS forecast_mw
        FROM t ASOF LEFT JOIN f
          ON t.start_time = f.start_time AND t.cutoff >= f.publish_time
        ORDER BY t.start_time
    """,
        tmp_path,
    )
    con.close()
    merged = ours.select("start_time", "forecast_mw").join(theirs, on="start_time", suffix="_duck")
    assert merged.height == ours.height
    mismatched = merged.filter(pl.col("forecast_mw").ne_missing(pl.col("forecast_mw_duck")))
    assert mismatched.is_empty()


def test_golden_headline_accuracy(real_analytics: Analytics) -> None:
    acc = real_analytics.accuracy(FIRST, LAST, 24, MatchingRule.HOUR_MEAN)
    assert acc.summary.n == 744
    assert acc.summary.mae_mw == pytest.approx(1947.65, abs=0.01)
    assert acc.summary.bias_mw == pytest.approx(1738.11, abs=0.01)
    assert acc.capacity_proxy_mw == 18382.0
    curve = {c.horizon_h: c for c in acc.curve}
    assert curve[48].coverage == pytest.approx(589 / 744)
    # Error grows with horizon.
    assert curve[1].mae_mw < curve[24].mae_mw < curve[48].mae_mw  # type: ignore[operator]


def test_golden_model_skill_at_n2ex_gate(real_analytics: Analytics) -> None:
    m = real_analytics.models(FIRST, LAST, AuctionId.N2EX_DA, MatchingRule.HOUR_MEAN)
    scores = {s.model: s for s in m.scores}
    assert scores["raw"].mae_mw == pytest.approx(2013.01, abs=0.01)
    assert scores["ratio"].skill_vs_raw == pytest.approx(0.3746, abs=1e-4)
    assert scores["debiased"].skill_vs_raw == pytest.approx(0.2635, abs=1e-4)
    assert m.band.coverage == pytest.approx(0.8616, abs=1e-4)


def test_quality_findings_on_january(real_analytics: Analytics) -> None:
    q = real_analytics.quality(FIRST, LAST)
    assert q.runs_per_day_expected == 8
    assert [r.slot_utc for r in q.late_runs] == ["11:30"]
    assert q.late_runs[0].delay_min == 55
    assert q.missing_runs == []
    assert q.incomplete_days == 0


def test_decision_selects_run_before_gate(real_analytics: Analytics) -> None:
    from datetime import time

    d = real_analytics.decision(
        date(2026, 1, 15), time(9, 50), AuctionId.N2EX_DA, 0, MatchingRule.HOUR_MEAN
    )
    assert d.run is not None
    assert d.run.publish_time.isoformat() == "2026-01-14T09:30:00+00:00"
    assert d.run_age_min == 20
    assert len(d.points) == 24
    assert all(p.lead_h is not None and p.lead_h > 0 for p in d.points)
    assert not any(p.actual_known_at_cutoff for p in d.points)
    assert d.history_days == 28


def test_hindsight_forecast_is_reported_but_flattering(real_analytics: Analytics) -> None:
    acc = real_analytics.accuracy(FIRST, LAST, 24, MatchingRule.HOUR_MEAN)
    assert acc.hindsight.mae_mw == pytest.approx(1662, abs=1)
    # Hindsight beats even the 1-hour-ahead forecast: the illusion a "latest" view creates.
    assert acc.hindsight.mae_mw < acc.curve[1].mae_mw < acc.summary.mae_mw  # type: ignore[operator]
