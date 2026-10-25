# Research and design brief

Status: draft for review, written before implementation. Facts marked **[verified]** were checked against the live Elexon Insights API on 2026-10-25. Everything else cites its source.

## 1. The problem

A GB utility's day-ahead desk buys the power its customers need beyond what wind will supply. They buy one day ahead, so they rely on the public wind forecast. They need two things:

1. **The forecast they could actually have seen at decision time.** That means the newest one published before the auction closes, not just the newest one now.
2. **How wrong that forecast tends to be**, in MW, at the relevant horizon, so they can size a buffer.

The hard part is not plotting two lines. The comparison has to be honest about time: no look-ahead, correct time-zone handling, and a stated rule for matching the two datasets.

### Scope interpretation

"Purchase decisions made in January 2026" means decision days 1–31 Jan 2026. Those decisions cover **delivery days 2 Jan – 1 Feb 2026**. So the dataset needs:
- forecasts published from 31 Dec 2025 onwards;
- actuals up to the end of 1 Feb 2026.

## 2. Domain facts that drive the design

### Day-ahead auctions (GB has been decoupled from European market coupling since 1 Jan 2021)

| Auction | Products | Gate closure (UK time, D-1) | Source |
|---|---|---|---|
| EPEX GB hourly | 60 min | 09:20 | [S&P Global notice](https://www.spglobal.com/commodity-insights/en/pricing-benchmarks/our-methodology/subscriber-notes/120920-platts-to-amend-uk-day-ahead-power-assessments-timing-from-jan-4) (secondary) |
| Nord Pool N2EX GB | 60 min | 09:50, results by 10:00 | [Nord Pool](https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-day-ahead-gb-auction) (primary, checked) |
| EPEX GB half-hourly | 30 min | 15:30 | [EPEX trading brochure](https://www.epexspot.com/sites/default/files/download_center_files/21-03-09_Trading%20Brochure.pdf) |

Decision time is therefore **configurable, with these three auctions as presets**, not hard-coded.

### Settlement periods and time

- A settlement day runs from 00:00 to 24:00 Europe/London time.
- It has 48 half-hour periods normally, 46 on the spring clock-change day **[verified: 2026-03-29]** and 50 in autumn.
- FUELHH `settlementDate` is a local date, but `startTime` is UTC **[verified]**.
- January is GMT, so UTC and UK time match, which hides time-zone bugs. **Everything is stored and computed in UTC. Conversion to UK time happens only at the API edge**, and tests cover the clock-change days.

## 3. Data facts **[verified]**

### WINDFOR (forecast)

- **Endpoint:** `GET https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream?publishDateTimeFrom&publishDateTimeTo`. No API key needed.
- **Cadence:** 8 runs a day, at **02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC**.
  - Elexon's [glossary](https://www.elexon.co.uk/bsc/glossary/wind-generation-forecast/) still says 4 runs a day. It is out of date.
  - Runs can be late. On 2026-01-15 the 11:30 run arrived at 12:25.
- **Resolution:** **hourly**. Each run has 73 points, from 21:00 the previous day to 21:00 on D+2. The maximum horizon is about 66 h.
- **Past rows:** about 20% of rows have `startTime < publishTime`, i.e. hours that had already passed. These are excluded, otherwise forecasts look more accurate than they were.
- **Range:** January values span 2.25–21.4 GW.

### FUELHH (actuals)

- **Endpoint:** `/datasets/FUELHH/stream?settlementDateFrom&settlementDateTo&fuelType=WIND`.
- **Resolution:** half-hourly. January is complete: 31 × 48 periods, no duplicates.
- **Lag:** published 30–145 minutes after the period starts.
- **Coverage:** grid-metered (Balancing Mechanism) wind only. It excludes wind on local networks (roughly 6.5 GW of capacity according to NESO) and is measured after curtailment.

### API behaviour

- The `/stream` endpoints return a whole month in one call (about 2.4 MB).
- The paged endpoints reject date ranges over 7 days.
- There is no published rate limit. The client uses retry with backoff anyway.
- **Legacy BMRS** needed an API key and was shut down in 2024. Older clients such as [ElexonDataPortal](https://github.com/OSUKED/ElexonDataPortal) no longer work.

### Headline finding: WINDFOR runs about 1.6–1.9 GW above FUELHH

Method: for each target hour, take the latest run published at least H hours earlier and compare it with FUELHH at the same `startTime`.

| H (h) | MAE (MW) | Bias (MW) | RMSE (MW) | P90 \|err\| (MW) |
|---|---|---|---|---|
| 1 | 1,801 | +1,596 | 2,294 | 3,799 |
| 12 | 1,898 | +1,704 | 2,379 | 3,898 |
| 24 | 2,050 | +1,854 | 2,518 | 4,133 |
| 48 | 2,380 | +1,879 | 2,938 | 4,778 |

- **Bias makes up most of the MAE.** The bias is larger at high wind (about 2.1–2.6 GW when actuals are above 12 GW) and overnight.
- **Likely causes, both unconfirmed:**
  - WINDFOR forecasts output before curtailment, while FUELHH reflects curtailment of Scottish wind farms;
  - and/or the two datasets cover different sets of wind farms.
- **Testing the cause** would need NESO's wind BOA volumes dataset, which is outside the brief's data scope, so it goes under future work.
- **Product value:** removing the bias, using only error data that was available at decision time, should cut error substantially. This is the strongest single message for the client.

## 4. How forecast accuracy is measured

Following Madsen, Pinson, Kariniotakis et al. (2005), *Standardizing the performance evaluation of short-term wind power prediction models*:

- **Errors by horizon.** Report bias (mean error), MAE and RMSE as functions of horizon, not as one number. Sign convention: error = forecast − actual, so positive means the forecast was too high.
- **Normalised error (nMAE).** Divide MAE by a capacity proxy. The installed capacity behind FUELHH is not in the data, so the max observed actual is used and the proxy is labelled as such.
- **No MAPE.** It blows up at low wind. Use MW error, plus WAPE (total absolute error / total actual) for a percentage.
- **Error distributions.** Show P10/P50/P90 of the error by horizon bucket, hour of day and wind level. These turn the forecast into a range a trader can act on.
- **Band coverage.** Check how often the actual value fell inside the stated P10–P90 band.
- **Ramp events.** Count how often swings of more than 2 GW within 3 hours were forecast correctly, missed, or falsely predicted.
- **Comparison models.** Compare against simple baselines: persistence, and WINDFOR minus its own trailing bias.

### Matching rule (forecast is hourly, actuals are half-hourly)

- **Default:** compare each forecast hour with the mean of the two half-hours it covers (`HH:00` and `HH:30`). This is the energy-consistent choice.
- **Option:** compare only on-the-hour periods.
- The rule is shown in the UI.

### No look-ahead, anywhere

- The forecast is the run with the greatest `publishTime ≤ decision time − safety margin`.
- Any bias correction uses only actuals already published by the decision time (FUELHH `publishTime ≤ decision time`).
- Early January corrections therefore need December actuals. That counts as "data relevant to January decisions" and is noted in the README.

## 5. Gaps in existing tools

| Tool | What it lacks for a day-ahead buyer |
|---|---|
| BMRS website | Raw data only. No point-in-time view of past runs, no accuracy measurement. |
| NESO data portal | Raw data, no evaluation. |
| LCP Enact, Modo, Montel, Kpler | Paid and closed. They sell their own forecasts rather than auditing the public one. |
| Open Climate Fix (PVNet, Quartz) | Solar forecasting models, not evaluation tools for buyers. |

None of them answer the trader's real question: *"what did the public forecast say at my gate closure, how wrong is it usually at this horizon, hour and wind level, and how big should my buffer be?"* This product answers it, and every number can be traced back to the source data.

## 6. Product scope

### Must have: the two requirements

1. **Decision view.**
   - Pick a delivery day and an auction preset (or a custom decision time).
   - Show the run that was available, with its publish time and age, and warn if it arrived after the gate closed.
   - Show forecast vs actual for the delivery day, the P10–P90 error band, and the shortfall to cover.
2. **Accuracy view.**
   - Headline stats, error vs horizon curve, horizon × hour-of-day heatmap, error by wind level, error distribution, and the bias story.

### Should have: what makes it trustworthy

3. **Data quality panel:** late or missing runs, periods per day, completeness of actuals, out-of-range values.
4. **Methodology drawer** in the app, plus CSV export of the exact forecast/actual pairs behind every metric.
5. **Version stamp:** `data_version` (hash of the raw snapshot) and `generated_at` on every API response.

### Stretch

6. Bias-corrected forecast with a skill score against raw WINDFOR.
7. Ramp event analysis.

## 7. Architecture

```
Elexon Insights API ──► ingest (httpx + retry) ──► raw JSON snapshot (immutable, hashed)
                                                     │
                                                     ▼
                                    DuckDB/Parquet: forecasts, actuals
                                                     │
                       domain: as-of selection, matching, metrics (pure functions)
                                                     │
                                   FastAPI (typed Pydantic responses, OpenAPI)
                                                     │
                     React + TS (Vite, TanStack Query, ECharts) served by the same container
```

### Technology choices

| Choice | Why | Rejected alternative |
|---|---|---|
| FastAPI + Pydantic v2 | Typed contracts and free OpenAPI docs; the frontend types are generated from them | Flask (no typed contracts) |
| DuckDB + Parquet | In-process, a single file, SQL window functions for "latest run before time T". January is about 21k rows. | TimescaleDB/Postgres (needs another service for no benefit at this size) |
| Polars | Fast, explicit dataframe code for the metrics | pandas (also fine, less strict about types) |
| Committed seed snapshot | The deployed demo still works if Elexon is down, and results are reproducible | Fetching live on every request |
| httpx + tenacity | Async client with retry/backoff; easy to stub with respx in tests | ElexonDataPortal (dead), elexonpy (generated, heavy) |
| React + TypeScript + Vite | Required stack; strict typing | CRA (deprecated) |
| TanStack Query | Caching, loading and error states handled properly | Hand-rolled `useEffect` fetching |
| Apache ECharts | Heatmaps, box plots and zoom over long series | Recharts (no heatmaps or box plots) |
| One multi-stage Docker image on Heroku (container stack) | Docker is used in production, not only locally. One URL, no CORS. | Split Vercel frontend + separate backend (two deploys, CORS) |

### Engineering practices to show in review

- **Clean layering:** the domain layer has no I/O and is fully unit-tested.
- **Property-based tests (Hypothesis)** for the as-of rule: a run published after the decision time is never selected.
- **Clock-change tests** for 46- and 50-period days.
- **Recorded API fixtures (respx)**, so the test suite never hits the network.
- **GitHub Actions CI:** ruff, mypy --strict, pytest with coverage, eslint, tsc, vitest, Docker build.
- **Operations:** structured logging, `/healthz`, and settings via environment variables (pydantic-settings).
- **Design records:** short ADRs in `docs/adr/` for storage, matching rule and deployment.
- **Honest AI disclosure** in the README.

## 8. Risks and open questions

- **Exchange gate times** are configurable presets. The EPEX time comes from a secondary source.
- **The cause of the bias is a hypothesis.** It is presented as such, with the test that would confirm it.
- **Heroku has no free tier** (roughly $5–7 per month). Vercel would need the backend as serverless Python functions, which fit DuckDB and the Docker requirement poorly.
- **Time budget:** 16 h. Stretch items are cut first.
