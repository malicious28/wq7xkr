# Comparable submissions: code review

Thirteen public repositories that solve the same brief were read in full (backend logic, tests, CI, Docker). The review was read-only: none of their code was run. Claims below come from reading code with file and line references, not from READMEs. Two repos were excluded: one was unavailable, and one is a research study rather than an app.

## The five traps, and who falls in

| | Real auction gate | As-of per hour | Bands fitted only on the past | Hourly vs half-hourly | UK time / clock changes | Tests (backend + frontend) | CI |
|---|---|---|---|---|---|---|---|
| **Windesk (ours)** | ✅ N2EX 09:50, EPEX 09:20, EPEX 15:30, custom gate, safety margin | ✅ property-tested; DuckDB differential test; reconciled with Elexon | ✅ per gate, trailing 28 days, uses the actual FUELHH publish time | ✅ mean of both halves; incomplete hours dropped | ✅ Europe/London; 46- and 50-period days tested | 113 + 37 | ✅ lint, strict types, tests, contract drift, Docker smoke test |
| prajwal483/4eaez3 | ✅ same 3 gates | ✅ | ✅ 14 days, matched to lead time, with a publication-lag guard | ⚠️ :00 half-hour only | ❌ UTC only (wrong in BST) | 53 + 55 | ✅ includes contract drift |
| ice-009/data-bricks_swe | ✅ EPEX, N2EX | ✅ | ⚠️ bias correction ✅ (D-2); band uses future days | ⚠️ :00 only | ✅ tested | 24 + 5 | ✅ includes Docker smoke test |
| DakshBhavsar007/dhiwndkfnw | ❌ 09:00 (3 of 4 presets after the real gates) | ✅ | ✅ D-2 rolling | ✅ mean | ✅ tested | 51 + 25 | ✅ (mypy advisory) |
| codes-stories/Wind-Forecast-Intelligence | ⚠️ 09:20 UTC, configurable | ✅ | n/a (no bands) | ✅ mean | ❌ UTC only | 116 + 48 | ❌ |
| afwaansarfaraz/AH0329 | ✅ 09:20 London | ✅ | n/a (descriptive only) | ✅ mean | ⚠️ latent BST bug | 52 + 21 | ❌ |
| khushbuyadav2208/WindWard | ❌ 10:00, admits 09:30 runs | ✅ | n/a | ⚠️ hour held flat | ⚠️ untested | 21 + 2 + 5 end-to-end | ✅ includes accessibility tests |
| heyranjanshaw07/WildFlow | ❌ 09:00 | ✅ | ❌ pooled over the month | ⚠️ :00 only | ⚠️ UTC hour labels | 27 + 4 | ❌ (backend duplicated) |
| Yogesh7702/WindCast | ❌ 09:00 UTC, one run per day | ❌ | ❌ pooled; leave-one-day-out bias uses future days | ⚠️ hour held flat | ❌ UTC only | 15 | ✅ |
| anilkumara9/kjhwrmgw6h | ✅ 09:50 (strict <) | ✅ | n/a | ⚠️ mean of whatever halves exist | ❌ UTC only | 8 | ❌ |
| Anshrastogi05/Wind-Forecast-Portal | ❌ 09:00 | ✅ | ❌ pooled over the month | ⚠️ hour held flat | ✅ tested | 19 | ⚠️ minimal |
| Shashi0103/GbSweCh | ❌ 12:00 UTC | ✅ | n/a | ⚠️ hour held flat | ❌ UTC only | 17 | ❌ |
| Prateekbaliyan/wind-dashboard | ❌ 11:00 (a wrong gate claim) | ⚠️ custom cutoff can look ahead | n/a | ✅ mean | ⚠️ untested | 17 + 2 | ❌ |
| AmitChapde/wind-forecast-dashboard | ❌ 09:00 | ✅ | n/a | ❌ drops 50% of hours | ⚠️ | 0 | ❌ |

**Headline:** the strongest competitor is **4eaez3**, which has real gates, honest bands and a contract-drift check. It is UTC-only, so it would be wrong under BST, and it ignores the :30 half-hour. Nobody else reconciles their data against Elexon's own forecast views or quantifies the hindsight trap.

## Ideas adopted from them

- **Measure the hindsight trap** (kjhwrmgw6h compares a "leaky" forecast with the honest one). The Accuracy page now reports that Elexon's "latest" forecast would score MAE 1,662 MW, 15% better than the 1,948 MW actually knowable 24 h ahead.
- **Security headers** (WindWard) on every response.
- **A higher coverage gate** (4eaez3 enforces 95%; ours went from 85% to 90%, with actual coverage at 95%).
- **The vintage matrix** (WindCast), now the "How the forecast moved" card.

## Considered and not adopted

- **Lead-time-matched bands** (4eaez3). Our bands are pooled by 6-hour block of the day. That block correlates with lead time at a fixed gate and gives about 168 samples per quantile instead of about 14 per lead hour. Our out-of-sample coverage (86% against 80% nominal) is documented in ADR 0004.
- **CDN `s-maxage`** (4eaez3). It only helps behind a CDN, and the Heroku deploy has none.
