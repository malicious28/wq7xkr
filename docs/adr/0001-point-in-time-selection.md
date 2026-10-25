# ADR 0001: Point-in-time ("as-of") selection is the core abstraction

- Status: accepted
- Date: 2026-10-25

## Context

The desk buys at a gate closure on the day before delivery. The only forecast that matters is one that **was available at that moment**. WINDFOR publishes 8 runs a day, each covering about 66 hours, so every target hour has many candidate forecasts. Picking the wrong one, for example the newest *today*, quietly uses hindsight and makes the forecast look better than it was.

## Decision

One pure function, `domain.asof.select_asof(forecasts, targets)`, answers every "what was known?" question:

> For each target `(start_time, cutoff)`, choose the run with the greatest `publish_time <= cutoff` that contains `start_time`.

Two ways of setting the cutoff cover every view:

| View | Cutoff |
|---|---|
| Horizon explorer, accuracy curves | `target − H` |
| Decision view, models | `gate closure (local, D−1) − margin` |

It is implemented as a Polars `join_asof` grouped by target. Because the cutoff is always at or before the target, forecast points whose hour had already started at publication are excluded automatically.

## Consequences

- There is one place to get right, and it is tested three ways:
  - hand-written edge cases (publish time exactly at the cutoff, a newer run that doesn't contain the target);
  - **property-based tests** against a naive reference implementation on random histories;
  - a **differential test** against DuckDB's native `ASOF JOIN` on the real January data.
- Bias correction and error bands apply the same rule to *outturn*: only actuals already published at the cutoff (`FUELHH.publishTime`) are used.
- A metamorphic test corrupts every actual published after a cutoff and asserts that the day's outputs are unchanged.

## Rejected

- *Latest run before the delivery day starts*: ignores the gate time, which is a few hours earlier.
- *Bucket all (run, target) pairs by lead time*: valid for science, but not what a buyer sees at their gate.
