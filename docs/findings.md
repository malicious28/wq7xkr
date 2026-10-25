# Data findings: January 2026

These results come from the committed snapshot (`data_version c589a65ee65e`) and are reproducible with `windesk build`. They update the pre-implementation estimates in `research.md` §3.

## 1. WINDFOR runs about 15% above FUELHH, and the gap is proportional

Fixed-horizon accuracy, delivery 2 Jan – 1 Feb 2026, `hour_mean` matching:

| Horizon | MAE | Bias | RMSE | Hours with a forecast |
|---|---|---|---|---|
| 1 h | 1,691 MW | +1,474 MW | 2,162 MW | 100% |
| 12 h | 1,803 MW | +1,597 MW | 2,271 MW | 100% |
| 24 h | 1,948 MW | +1,738 MW | 2,407 MW | 100% |
| 48 h | 2,310 MW | +1,791 MW | 2,874 MW | 79% |

At 48 h, hours from 22:00 to 01:00 can have no forecast: no run published 48 h earlier reaches that far.

**Grouped by what the forecast said** (the view a buyer can act on), the forecast/actual energy ratio is 1.10–1.16 at every level, rising to 1.21–1.26 above 18 GW:

| Forecast level | Bias |
|---|---|
| 0–3 GW | +266 MW |
| 3–6 GW | +683 MW |
| 6–9 GW | +806 MW |
| 9–12 GW | +1,341 MW |
| 12–15 GW | +1,185 MW |
| 15+ GW | +2,748 MW |

Grouping by *actual* level instead shows a large bias in calm hours (+1.66 GW below 3 GW). That is selection on the outcome (regression to the mean), not a real calm-hour bias. The app offers both groupings and explains the difference.

## 2. The likely causes are coverage and curtailment

- A proportional gap at every level fits the two datasets covering different sets of wind farms.
- The extra gap in strong winds, and overnight (+2.4 GW at 02:00 vs +1.2 GW at 16:00), fits curtailment: FUELHH is metered after balancing actions, and constraints peak when wind is high and demand is low.
- The daily bias ranges from −70 MW to +5 GW. It depends on grid conditions, so a fixed offset would be wrong.
- **Not tested**: confirming this needs NESO balancing-action (BOA) volumes, which are outside the brief's data scope.

## 3. The timestamps are aligned

Shifting outturn against forecast by −3 h to +3 h: correlation 0.9225 / 0.9352 / **0.9427** / **0.9445** / 0.9406 / 0.9311, and de-biased MAE is lowest at 0 to +1 h. The bias is not a time-alignment artefact.

## 4. Planning around the error works, out of sample

At the N2EX gate, a trailing 28-day ratio adjustment, using only data available at each gate, cuts MAE from 2,013 to 1,259 MW (**+37% skill**). The 80% band covers 86.2% of hours. See ADR 0004.

## 5. Elexon's "latest forecast" is a hindsight series

Elexon's server-side `/forecast/generation/wind/latest` returns, for each hour, the newest run that covered it. For **all 745** hours from 2 January to 2 February, that run was published *after* the hour had started. Comparing outturn with "latest" therefore compares it with restated values. The `earliest` view is clean, and our snapshot matches it exactly (`tests/integration/test_upstream_reconciliation.py`).

## 6. Data quality

- 8 runs a day at 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC. Every run has 73 hourly points.
- One late run: the 11:30 UTC run on 15 Jan arrived at 12:25.
- FUELHH is complete: 48 periods every day, no duplicates, no republications, publication lag p50 30 min (max 145 min).
- 20.5% of WINDFOR rows (7,801) restate hours that had already started when published. They are never used.
