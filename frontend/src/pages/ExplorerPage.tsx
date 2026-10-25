import { useMemo } from 'react'

import { useHorizon } from '../api/hooks'
import type { HorizonPoint } from '../api/types'
import { EChart } from '../charts/EChart'
import { horizonOption } from '../charts/options/series'
import { ScopeFilters } from '../components/ScopeFilters'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  Button,
  Card,
  ErrorState,
  Field,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  Slider,
  StatTile,
} from '../components/ui/ui'
import { hours, mw, pct, signedMw, ukDateTime, ukDay } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useDebounced } from '../lib/useDebounced'
import { useNumberParam, useScope } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './pages.module.css'

const columns: Column<HorizonPoint>[] = [
  { key: 't', header: 'Target (UK)', cell: (p) => ukDateTime(p.start_time) },
  {
    key: 'pub',
    header: 'Run published',
    cell: (p) => (p.publish_time ? ukDateTime(p.publish_time) : '—'),
  },
  { key: 'lead', header: 'Lead', cell: (p) => hours(p.lead_h), align: 'right' },
  { key: 'f', header: 'Forecast', cell: (p) => mw(p.forecast_mw), align: 'right' },
  { key: 'a', header: 'Actual', cell: (p) => mw(p.actual_mw), align: 'right' },
  {
    key: 'e',
    header: 'Error',
    cell: (p) =>
      signedMw(p.forecast_mw != null && p.actual_mw != null ? p.forecast_mw - p.actual_mw : null),
    align: 'right',
  },
]

export default function ExplorerPage() {
  const scope = useScope()
  const [horizon, setHorizon] = useNumberParam('h', 24, 0, 48)
  const queryHorizon = useDebounced(horizon)
  const { tokens } = useTheme()
  const query = useHorizon({
    first: scope.first,
    last: scope.last,
    matching: scope.matching,
    horizon_h: queryHorizon,
  })
  const d = query.data?.data
  const option = useMemo(
    () => (d ? horizonOption(d.points, tokens, horizon) : null),
    [d, tokens, horizon],
  )
  const csv = `/api/export/pairs.csv?first=${scope.first}&last=${scope.last}&horizon_h=${horizon}&matching=${scope.matching}`

  return (
    <>
      <PageHeader
        eyebrow="Forecast vs actual"
        title="How far ahead can you trust it?"
        lede="Drag the horizon. For every target hour, the forecast shown is the latest run published at least that many hours earlier, so you see exactly what was known that far ahead, with no hindsight."
      />
      <FilterBar>
        <div className={s.sliderField}>
          <Field label="Forecast horizon">
            {(id) => (
              <Slider
                id={id}
                value={horizon}
                min={0}
                max={48}
                onChange={setHorizon}
                format={(v) => `${v} h`}
                marks={[0, 12, 24, 36, 48]}
              />
            )}
          </Field>
        </div>
        <ScopeFilters />
      </FilterBar>

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {!d && query.isPending && <Loading />}
      {d && (
        <>
          <Grid cols={4}>
            <Card>
              <StatTile
                label="Mean absolute error"
                value={mw(d.summary.mae_mw)}
                detail={`${d.summary.n} hours · nMAE ${pct(d.summary.nmae, 1)}`}
              />
            </Card>
            <Card>
              <StatTile
                label="Bias"
                value={signedMw(d.summary.bias_mw)}
                detail="Forecast − actual, mean"
              />
            </Card>
            <Card>
              <StatTile
                label="RMSE"
                value={mw(d.summary.rmse_mw)}
                detail={`WAPE ${pct(d.summary.wape, 1)}`}
              />
            </Card>
            <Card>
              <StatTile
                label="Hours with a forecast"
                value={pct(d.coverage)}
                detail={
                  d.coverage < 1
                    ? 'Some hours fall beyond the runs’ reach at this horizon'
                    : 'Every target hour covered'
                }
              />
            </Card>
          </Grid>
          <Reveal>
            <Card
              title={`Actual vs forecast made ≥ ${horizon} h ahead`}
              subtitle={
                scope.preset
                  ? `${ukDay(scope.first)} – ${ukDay(scope.last)}. Scroll or use the slider below the chart to zoom.`
                  : undefined
              }
              actions={
                <Button icon="download" href={csv} download>
                  CSV
                </Button>
              }
            >
              {option && (
                <EChart
                  option={option}
                  label={`Actual and ${horizon}-hour-ahead forecast`}
                  height={420}
                  stale={query.isPlaceholderData}
                />
              )}
              <DataTable
                caption="Forecast and actual per hour"
                columns={columns}
                rows={d.points}
                rowKey={(p) => p.start_time}
                collapsible
              />
            </Card>
          </Reveal>
        </>
      )}
    </>
  )
}
