"""Property-based tests for the no-look-ahead core.

``select_asof`` is checked against a deliberately naive reference
implementation on randomly generated forecast histories, and against the
invariants a trader relies on:

1. a run published after the cutoff is never selected;
2. the selected run actually contains the target;
3. no run that also qualifies is newer than the selected one (maximality);
4. a null result means no run qualified.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.conftest import forecasts_frame, utc
from windesk.domain import clock
from windesk.domain.asof import select_asof

BASE = utc(2026, 1, 1)
UTC_US = pl.Datetime("us", "UTC")


@st.composite
def histories(draw: st.DrawFn) -> tuple[pl.DataFrame, pl.DataFrame]:
    n_runs = draw(st.integers(1, 8))
    pub_offsets = draw(
        st.lists(st.integers(0, 96 * 60), min_size=n_runs, max_size=n_runs, unique=True)
    )
    rows: list[tuple[datetime, datetime, float]] = []
    for off in pub_offsets:
        pub = BASE + timedelta(minutes=off)
        hours = draw(st.sets(st.integers(0, 120), min_size=1, max_size=20))
        rows.extend((pub, BASE + timedelta(hours=h), float(off + h)) for h in hours)
    n_targets = draw(st.integers(1, 15))
    targets = pl.DataFrame(
        {
            "start_time": [
                BASE + timedelta(hours=draw(st.integers(0, 120))) for _ in range(n_targets)
            ],
            "cutoff": [
                BASE + timedelta(minutes=draw(st.integers(-60, 130 * 60))) for _ in range(n_targets)
            ],
        }
    ).cast({"start_time": UTC_US, "cutoff": UTC_US})
    return forecasts_frame(rows), targets


def _reference(forecasts: pl.DataFrame, start: datetime, cutoff: datetime) -> float | None:
    best: tuple[datetime, float] | None = None
    for pub, tgt, gen in forecasts.iter_rows():
        if tgt == start and pub <= cutoff and (best is None or pub > best[0]):
            best = (pub, gen)
    return None if best is None else best[1]


@settings(max_examples=300, deadline=None)
@given(histories())
def test_select_asof_matches_naive_reference(data: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    forecasts, targets = data
    out = select_asof(forecasts, targets)
    assert out.height == targets.height
    for row in out.iter_rows(named=True):
        assert row["forecast_mw"] == _reference(forecasts, row["start_time"], row["cutoff"])


@settings(max_examples=300, deadline=None)
@given(histories())
def test_selection_never_looks_ahead_and_is_maximal(
    data: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    forecasts, targets = data
    out = select_asof(forecasts, targets)
    for row in out.iter_rows(named=True):
        covering = forecasts.filter(pl.col("start_time") == row["start_time"])
        qualifying = covering.filter(pl.col("publish_time") <= row["cutoff"])
        if row["publish_time"] is None:
            assert qualifying.is_empty()
            continue
        assert row["publish_time"] <= row["cutoff"]
        assert row["publish_time"] in covering["publish_time"].to_list()
        assert row["publish_time"] == qualifying["publish_time"].max()


@settings(max_examples=200, deadline=None)
@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 12, 31)))
def test_settlement_days_tile_time_with_46_48_or_50_periods(d: date) -> None:
    start, end = clock.settlement_day_bounds(d)
    assert clock.periods_in_day(d) in {46, 48, 50}
    assert end == clock.settlement_day_bounds(d + timedelta(days=1))[0]  # no gaps, no overlap
    assert (end - start) == clock.periods_in_day(d) * clock.PERIOD
