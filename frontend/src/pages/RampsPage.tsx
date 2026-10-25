import { useMemo } from 'react'

import { useHorizon, useRamps } from '../api/hooks'
import type { RampEvent } from '../api/types'
import { EChart } from '../charts/EChart'
import { rampOption } from '../charts/options/series'
import { ScopeFilters } from '../components/ScopeFilters'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  Card,
  ErrorState,
  Field,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  Select,
  StatTile,
  StatusPill,
} from '../components/ui/ui'
import { pct, signedMw, ukDateTime } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useNumberParam, useScope } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './pages.module.css'

const eventColumns: Column<RampEvent>[] = [
  { key: 't', header: 'Starts (UK)', cell: (e) => ukDateTime(e.start_time) },
  { key: 'dir', header: 'Direction', cell: (e) => (e.direction === 'up' ? 'Up ▲' : 'Down ▼') },
  { key: 'd', header: 'Change', cell: (e) => signedMw(e.delta_mw), align: 'right' },
  {
    key: 'o',
    header: 'Forecast',
    cell: (e) => (
      <StatusPill tone={e.outcome === 'hit' ? 'good' : 'critical'}>
        {e.outcome === 'hit' ? 'Caught' : 'Missed'}
      </StatusPill>
    ),
  },
]

export default function RampsPage() {
  const scope = useScope()
  const { tokens } = useTheme()
  const [horizon, setHorizon] = useNumberParam('h', 24, 0, 48)
  const [threshold, setThreshold] = useNumberParam('mw', 2000, 500, 6000)
  const [window, setWindow] = useNumberParam('w', 3, 1, 6)
  const [tolerance, setTolerance] = useNumberParam('tol', 1, 0, 3)
  const range = { first: scope.first, last: scope.last, matching: scope.matching }
  const query = useRamps({
    ...range,
    horizon_h: horizon,
    threshold_mw: threshold,
    window_h: window,
    tolerance_h: tolerance,
  })
  const series = useHorizon({ ...range, horizon_h: horizon })
  const d = query.data?.data
  const option = useMemo(
    () => (d && series.data ? rampOption(series.data.data.points, d.events, tokens) : null),
    [d, series.data, tokens],
  )

  return (
    <>
      <PageHeader
        eyebrow="Ramp events"
        title="Did it see the big swings coming?"
        lede="A large, fast change in wind is when a desk gets caught short. A ramp is a change of at least the threshold within the window. The forecast catches it if it predicts a ramp in the same direction within the timing tolerance."
      />
      <FilterBar>
        <Field label="Horizon">
          {(id) => (
            <Select
              id={id}
              value={String(horizon)}
              onChange={(v) => setHorizon(Number(v))}
              options={[1, 6, 12, 24, 36, 48].map((h) => ({
                value: String(h),
                label: `${h} h ahead`,
              }))}
            />
          )}
        </Field>
        <Field label="Ramp size">
          {(id) => (
            <Select
              id={id}
              value={String(threshold)}
              onChange={(v) => setThreshold(Number(v))}
              options={[1000, 1500, 2000, 3000, 4000].map((m) => ({
                value: String(m),
                label: `≥ ${m / 1000} GW`,
              }))}
            />
          )}
        </Field>
        <Field label="Within">
          {(id) => (
            <Select
              id={id}
              value={String(window)}
              onChange={(v) => setWindow(Number(v))}
              options={[1, 2, 3, 4, 6].map((w) => ({ value: String(w), label: `${w} h` }))}
            />
          )}
        </Field>
        <Field label="Timing tolerance">
          {(id) => (
            <Select
              id={id}
              value={String(tolerance)}
              onChange={(v) => setTolerance(Number(v))}
              options={[0, 1, 2, 3].map((t) => ({ value: String(t), label: `± ${t} h` }))}
            />
          )}
        </Field>
        <ScopeFilters />
      </FilterBar>

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {!d && query.isPending && <Loading />}
      {d && (
        <>
          <Grid cols={4}>
            <Card>
              <StatTile
                size="l"
                label="Ramps caught (POD)"
                value={pct(d.scores.pod)}
                detail={`${d.scores.hits} of ${d.scores.hits + d.scores.misses} ramp hours`}
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="False alarms (FAR)"
                value={pct(d.scores.far)}
                detail={`${d.scores.false_alarms} predicted ramp hours that did not happen`}
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="Critical success index"
                value={pct(d.scores.csi)}
                detail="Hits ÷ (hits + misses + false alarms)"
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="Ramp events"
                value={String(d.events.length)}
                detail={`${d.events.filter((e) => e.outcome === 'hit').length} caught · ${d.events.filter((e) => e.outcome !== 'hit').length} missed`}
              />
            </Card>
          </Grid>
          <Reveal>
            <Card
              title="Ramp events on the outturn"
              subtitle="▲ up-ramps and ▼ down-ramps mark where each event starts. Green = the forecast caught it, red = missed."
            >
              {option ? (
                <EChart
                  option={option}
                  label="Actual generation with ramp events marked"
                  height={380}
                  stale={query.isPlaceholderData}
                />
              ) : (
                <Loading />
              )}
              <div className={s.legendRow}>
                <StatusPill tone="good">Caught</StatusPill>
                <StatusPill tone="critical">Missed</StatusPill>
              </div>
            </Card>
          </Reveal>
          <Grid cols={2}>
            <Reveal>
              <Card title="Contingency table" subtitle="Hour-by-hour classification.">
                <table className={s.contingency}>
                  <thead>
                    <tr>
                      <th />
                      <th scope="col">Ramp happened</th>
                      <th scope="col">No ramp</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <th scope="row">Ramp forecast</th>
                      <td data-tone="good">{d.scores.hits} hits</td>
                      <td data-tone="warn">{d.scores.false_alarms} false alarms</td>
                    </tr>
                    <tr>
                      <th scope="row">No ramp forecast</th>
                      <td data-tone="bad">{d.scores.misses} misses</td>
                      <td>{d.scores.correct_negatives} correct negatives</td>
                    </tr>
                  </tbody>
                </table>
              </Card>
            </Reveal>
            <Reveal>
              <Card title="Events">
                <DataTable
                  caption="Ramp events"
                  columns={eventColumns}
                  rows={d.events}
                  rowKey={(e) => e.start_time}
                  maxHeight={280}
                />
              </Card>
            </Reveal>
          </Grid>
        </>
      )}
    </>
  )
}
