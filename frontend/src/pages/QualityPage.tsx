import { useMeta, useQuality } from '../api/hooks'
import { ScopeFilters } from '../components/ScopeFilters'
import {
  Callout,
  Card,
  ErrorState,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  StatTile,
  StatusPill,
  type Tone,
} from '../components/ui/ui'
import { minutes, pct, ukDateTime, ukDay } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useScope } from '../state/filters'
import s from './pages.module.css'

interface Check {
  name: string
  tone: Tone
  result: string
  detail: string
}

export default function QualityPage() {
  const scope = useScope()
  const meta = useMeta().data?.data
  const query = useQuality({ first: scope.first, last: scope.last })
  const q = query.data?.data

  const checks: Check[] = q
    ? [
        {
          name: 'Forecast runs on schedule',
          tone: q.missing_runs.length ? 'critical' : q.late_runs.length ? 'warning' : 'good',
          result: `${q.runs_total} runs, ${q.missing_runs.length} missing, ${q.late_runs.length} late`,
          detail: `${q.runs_per_day_expected} runs a day expected (Elexon's glossary still says 4; the data shows 8).`,
        },
        {
          name: 'Complete forecast runs',
          tone: q.short_runs ? 'warning' : 'good',
          result: q.short_runs
            ? `${q.short_runs} short runs`
            : `All runs have ${q.points_per_run_expected} hourly points`,
          detail: 'Each WINDFOR run covers 21:00 the previous day to 21:00 two days ahead.',
        },
        {
          name: 'Every settlement period present',
          tone: q.incomplete_days ? 'critical' : 'good',
          result: q.incomplete_days
            ? `${q.incomplete_days} incomplete days`
            : `${q.period_completeness.length} of ${q.period_completeness.length} days complete`,
          detail:
            'Checked against the expected count for each day: 46, 48 or 50 periods, allowing for clock changes.',
        },
        {
          name: 'Plausible values',
          tone: q.implausible_values ? 'warning' : 'good',
          result: q.implausible_values
            ? `${q.implausible_values} values above 30 GW`
            : 'No negative or implausible values',
          detail:
            'Negative values and values above 30 GW (beyond GB metered wind capacity) are excluded and listed here.',
        },
        {
          name: 'Ingest anomalies',
          tone: q.ingest_issues.length ? 'warning' : 'good',
          result: q.ingest_issues.length
            ? `${q.ingest_issues.length} issue types`
            : 'None: no duplicates, misaligned or republished rows',
          detail: 'Raw rows that break the schema are recorded rather than silently dropped.',
        },
        {
          name: 'Already-started targets excluded',
          tone: 'info',
          result: `${q.past_target_rows.toLocaleString('en-GB')} rows never used`,
          detail:
            'Every run also restates hours that had already begun when it was published. Using them would make the forecast look more accurate than it was.',
        },
      ]
    : []

  return (
    <>
      <PageHeader
        eyebrow="Trust"
        title="Can these numbers be trusted?"
        lede="Every figure in this app comes from the snapshot below. These checks run on that snapshot, so problems in the data are visible rather than hidden."
      />
      <FilterBar>
        <ScopeFilters showMatching={false} />
      </FilterBar>

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {!q && query.isPending && <Loading />}
      {q && meta && (
        <>
          <Grid cols={4}>
            <Card>
              <StatTile
                label="Data version"
                value={<code className={s.hash}>{meta.data_version}</code>}
                detail={`Fetched ${meta.fetched_at.slice(0, 16).replace('T', ' ')} UTC`}
              />
            </Card>
            <Card>
              <StatTile
                label="Forecast rows"
                value={meta.forecast_rows.toLocaleString('en-GB')}
                detail={`${meta.forecast_runs} runs`}
              />
            </Card>
            <Card>
              <StatTile
                label="Outturn periods"
                value={meta.actual_rows.toLocaleString('en-GB')}
                detail="Half-hourly, Dec 2025 – 1 Feb 2026"
              />
            </Card>
            <Card>
              <StatTile
                label="Outturn publication lag"
                value={minutes(q.actual_publication_lag.p50_min)}
                detail={`p95 ${minutes(q.actual_publication_lag.p95_min)} · max ${minutes(q.actual_publication_lag.max_min)}`}
              />
            </Card>
          </Grid>

          <Reveal>
            <Card title="Checks">
              <ul className={s.checks}>
                {checks.map((c) => (
                  <li key={c.name}>
                    <StatusPill tone={c.tone}>
                      {c.tone === 'good'
                        ? 'Pass'
                        : c.tone === 'info'
                          ? 'Info'
                          : c.tone === 'warning'
                            ? 'Warning'
                            : 'Fail'}
                    </StatusPill>
                    <div>
                      <strong>{c.name}</strong>
                      <span className={s.checkResult}>{c.result}</span>
                      <p>{c.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </Reveal>

          <Grid cols={2}>
            <Reveal>
              <Card
                title="Late forecast runs"
                subtitle="More than 10 minutes after the scheduled slot."
              >
                {q.late_runs.length === 0 ? (
                  <Callout tone="good" title="None" />
                ) : (
                  <ul className={s.plainList}>
                    {q.late_runs.map((r) => (
                      <li key={r.publish_time}>
                        <StatusPill tone="warning">{minutes(r.delay_min)} late</StatusPill> The{' '}
                        {r.slot_utc} UTC run arrived at {ukDateTime(r.publish_time)} UK.
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </Reveal>
            <Reveal>
              <Card
                title="Settlement periods per day"
                subtitle="Observed / expected. Every cell should be full."
              >
                <div className={s.calendar} role="list">
                  {q.period_completeness.map((d) => (
                    <div
                      key={d.settlement_date}
                      role="listitem"
                      className={s.calCell}
                      data-complete={d.complete || undefined}
                      title={`${ukDay(d.settlement_date)}: ${d.observed}/${d.expected}`}
                    >
                      <span>{d.settlement_date.slice(8)}</span>
                      <small>{pct(d.observed / d.expected)}</small>
                    </div>
                  ))}
                </div>
              </Card>
            </Reveal>
          </Grid>
        </>
      )}
    </>
  )
}
