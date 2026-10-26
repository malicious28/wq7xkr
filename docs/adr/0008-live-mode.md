# ADR 0008: Live mode reuses the January pipeline on data fetched on demand

- Status: accepted
- Date: 2026-10-26

## Context

The January study shows that a trailing ratio correction cuts WINDFOR's error by about a third. A buyer will ask the obvious next question: what does it say for tomorrow, and has it kept working since January? Answering that needs the same method running every day on current data, not only on the committed snapshot.

## Decision

A **Try now** page (`/live`) and two endpoints (`/api/live/summary`, `/api/live/day`) run the existing pipeline on recent Elexon data:

```
LiveService.get()          fetch WINDFOR + FUELHH from (live_start − trailing window) to now
  └─ normalise             same schema contract as the snapshot ingest
fit_live(now)              decision_pairs(..., not_after=now)   → as-of selection, cutoff = min(gate, now)
  └─ models.fit_and_apply  same out-of-sample correction and P10–P90 band
```

- **Nothing new in the domain layer.** The only change is an optional `not_after` cap on the cutoff: for a day whose gate is still ahead, the newest run published *so far* is used, and the day is marked provisional. Once its gate passes, the day is locked to the run that was available at the gate, so the scoreboard is exactly what a buyer would have seen.
- **Every day from `live_start` (1 October 2026) is kept**, so the page shows Elexon's forecast, Windesk's correction and the outturn side by side, plus a running scoreboard.
- **Freshness follows the data.** Data is re-fetched when the next WINDFOR run should have landed (plus 10 minutes' grace) or after 30 minutes at most. Run times are read from the last three days of data, because in UTC they move by an hour between summer and winter. The browser polls every 5 minutes; the server only calls Elexon when a refresh is due.
- **Single flight, fail soft.** Concurrent requests share one fetch behind an asyncio lock. If Elexon fails, the last good data is served with `stale: true`; with no data at all the endpoints return 503. Startup never waits on Elexon: the first fetch runs in the background.
- **Model fits are memoised per fetch and auction**, so the correction runs once per refresh, not once per request.
- `WINDESK_LIVE_ENABLED=false` turns the feature off (the endpoints return 404); `WINDESK_LIVE_START` moves the start date.

## Consequences

- The January analysis stays reproducible from the hashed snapshot; live data is never written to the warehouse and is not covered by `data_version`.
- Live mode depends on Elexon at request time. A cold fetch takes about 2–3 seconds for ~8 weeks of data. That cost grows with the window, so a long-running deployment should move `live_start` forward or persist fetched months.
- Live mode exercises the October clock change on real data (25 October has 25 hours), which the January snapshot could not.
- Tests drive the service with a simulated Elexon that serves both datasets with a known 15% bias and never returns anything published after the simulated clock. They cover the provisional cutoff, no look-ahead, the stale fallback, the 503 path, the refresh schedule and the 25-hour day.
