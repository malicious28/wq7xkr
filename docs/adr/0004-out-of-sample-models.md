# ADR 0004: Error bands and bias correction are fitted strictly out of sample

- Status: accepted
- Date: 2026-10-25

## Context

The brief asks for accuracy to be quantified so decisions can account for the error. A band fitted on January and then checked on January would cover 80% by construction, which tells the client nothing.

## Decision

For each delivery day D, at its own cutoff C:

```
history = decision pairs for days in [D − 28, D)   (same auction gate)
          whose hourly actual was published at or before C
```

Models fitted from that history, then applied to D:

| Model | Definition |
|---|---|
| `raw` | WINDFOR as published |
| `debiased` | raw − trailing **median** error of the target's 6-hour block (UK local) |
| `ratio` | raw ÷ trailing Σforecast / Σactual |
| `persistence` | last hourly outturn known at C, held flat |
| band | raw − trailing P90/P10 error by 6-hour block → an 80% interval for the actual |

- **Why 6-hour blocks**: the bias is strongly diurnal (about +2.4 GW overnight vs +1.2 GW in the afternoon). 28 days × 6 hours gives about 168 samples per quantile, against about 28 for a per-hour fit.
- **Minimum history**: 7 days. December data is fetched so that 1 January has a full window.
- **Scoring** uses only rows where *every* model is defined, so no model is flattered by easier hours.

## Result (N2EX gate, delivery 2 Jan – 1 Feb 2026)

| | MAE | Skill vs raw |
|---|---|---|
| raw | 2,013 MW | — |
| debiased | 1,483 MW | +26% |
| **ratio** | **1,259 MW** | **+37%** |
| persistence | 4,126 MW | −105% |

80% band coverage is **86.2%** (11.4% below, 2.4% above). That is slightly conservative and asymmetric, and it is reported as such.

## Consequences

The ratio model wins because the WINDFOR/FUELHH gap is roughly proportional (see `docs/findings.md`). A multiplicative band would likely calibrate better. That is listed as future work rather than tuned on the evaluation month.
