# ADR 0003: Matching hourly forecasts to half-hourly outturn

- Status: accepted
- Date: 2026-10-25

## Context

WINDFOR is hourly (`HH:00`). FUELHH is half-hourly mean power. Comparing them needs a stated rule, and the rule changes the numbers.

## Decision

- **Default `hour_mean`**: compare forecast hour `HH:00` with the mean of the `HH:00` and `HH:30` periods. This is energy-consistent, since both sides describe the same hour's MWh. Hours missing either half are dropped, never half-measured.
- **Option `on_the_hour`**: compare with the `HH:00` period only, for readers who treat WINDFOR values as point estimates.
- The hourly actual's `available_at` is the **later** of its two periods' first publications. The no-look-ahead rules (ADR 0001) filter on it.

## Evidence

Shifting the outturn series by −3 h to +3 h against the forecast shows correlation peaking between 0 and +1 h. The bias is not an alignment artefact.

## Consequences

The rule is a parameter on every endpoint and a selector in every view, and it is named in the CSV header. Half-hourly products (EPEX 15:30) use the hourly forecast value for both half-hours, and the UI says so.
