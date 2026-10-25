# ADR 0007: What we took from comparable tools, and what we rejected

- Status: accepted
- Date: 2026-10-26

## Method

- **gbelectricity.uk** (closed source, the closest public product) was inspected with [REA](https://github.com/morluto/rea) 6.8.0:
  - `list-browser-targets` → `inspect-web-page --include-script-sources` → `analyze-javascript-application`, run in a disposable Linux container. REA's verified-file reader fails on Windows (`ESTALE`).
  - Only architecture and behaviour were studied. No code or assets were copied.
- **Competing submissions** (WindCast, WildFlow) are public, so their source was read directly.
- **Our own repo** was audited by an independent reviewer using [Ponytail](https://github.com/DietrichGebert/ponytail)'s `/ponytail-audit` rules: smallest complete change, deletion before addition, never cut validation, security or tests.

## Adopted

| From | Idea | Where |
|---|---|---|
| gbelectricity.uk | Elexon's server-side `/forecast/generation/wind/{earliest,latest}` views as an **independent oracle** | `tests/integration/test_upstream_reconciliation.py`: the snapshot matches Elexon's earliest run per hour (completeness); live re-check opt-in via `pytest -m network` |
| gbelectricity.uk | Refuse to present a metric on too small a sample | Models already require 7 history days; unchanged |
| WindCast | A per-day **vintage matrix** (every run that covered a delivery day) | `domain/revisions.py`, `GET /api/revisions`, "How the forecast moved" card |
| Ponytail audit | Bounded LRU memo; integer horizons; cache only 200s; JSON 404 for unknown `/api/*`; one shared gate dependency; delete test-only helpers, the duplicate 500 handler, the fake CSV stream and the unused `orjson` | `services/analytics.py`, `api/app.py`, `api/deps.py`, `api/routes/analytics.py` |
| Ponytail audit | Re-sync Lenis on every new glass lens (a theme toggle used to freeze scrolling) | `motion/MotionProvider.tsx` |

## Found along the way

- **Elexon's `latest` endpoint is entirely hindsight.** For all 745 January hours, the "latest" run was published *after* the hour itself. A tool that compares outturn with "latest" is comparing it with restated values. Our selection never returns those rows, and a test now proves it.
- **WindCast's procurement band leaks the future.** Its error quantiles pool all of January, including days after the decision. Ours are fitted per day on data available at that gate (ADR 0004).

## Rejected (and why)

- **Proxy + direct-fetch transport with a circuit breaker** (gbelectricity.uk). It exists because that site fetches live upstream data in the browser. We serve an immutable snapshot from our own API, so the browser never calls Elexon.
- **Visibility-aware polling and retry schedules.** No live data, nothing to poll.
- **A duplicated backend tree for serverless deploys** (WildFlow keeps `api/backend/` as a copy). One container image is the single source (ADR 0005).
- **User-entered demand for buy volumes** (WindCast). It's useful, but demand is outside the brief's data scope. The P10 "conservative wind" energy already gives the desk the figure to subtract from its own demand.
- **Removing `httpx2`** (an audit suggestion). Starlette's `TestClient` imports it, so it is a real test dependency.
