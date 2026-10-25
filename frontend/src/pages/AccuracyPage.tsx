import { useMemo } from 'react'

import { useAccuracy } from '../api/hooks'
import type { CurvePoint, GroupStat } from '../api/types'
import { EChart } from '../charts/EChart'
import {
  curveOption,
  dailyBiasOption,
  groupBiasOption,
  heatmapOption,
  histogramOption,
} from '../charts/options/accuracy'
import { ScopeFilters } from '../components/ScopeFilters'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  Callout,
  Card,
  ErrorState,
  Field,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  Segmented,
  Slider,
  StatTile,
} from '../components/ui/ui'
import { mw, pct, signedMw } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useDebounced } from '../lib/useDebounced'
import { useNumberParam, useParam, useScope } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './pages.module.css'

const curveColumns: Column<CurvePoint>[] = [
  { key: 'h', header: 'Horizon', cell: (c) => `${c.horizon_h} h` },
  { key: 'n', header: 'Hours', cell: (c) => c.n, align: 'right' },
  { key: 'mae', header: 'MAE', cell: (c) => mw(c.mae_mw), align: 'right' },
  { key: 'rmse', header: 'RMSE', cell: (c) => mw(c.rmse_mw), align: 'right' },
  { key: 'bias', header: 'Bias', cell: (c) => signedMw(c.bias_mw), align: 'right' },
  { key: 'p10', header: 'Error P10', cell: (c) => signedMw(c.err_p10_mw), align: 'right' },
  { key: 'p90', header: 'Error P90', cell: (c) => signedMw(c.err_p90_mw), align: 'right' },
]

const groupColumns: Column<GroupStat>[] = [
  { key: 'k', header: 'Bucket', cell: (g) => g.key },
  { key: 'n', header: 'Hours', cell: (g) => g.n, align: 'right' },
  { key: 'bias', header: 'Bias', cell: (g) => signedMw(g.bias_mw), align: 'right' },
  { key: 'mae', header: 'MAE', cell: (g) => mw(g.mae_mw), align: 'right' },
  { key: 'wape', header: 'WAPE', cell: (g) => pct(g.wape, 1), align: 'right' },
]

export default function AccuracyPage() {
  const scope = useScope()
  const [horizon, setHorizon] = useNumberParam('h', 24, 0, 48)
  const queryHorizon = useDebounced(horizon)
  const [params, update] = useParam()
  const heatMetric = params.get('heat') === 'bias' ? 'bias' : 'mae'
  const levelBy = params.get('level') === 'actual' ? 'actual' : 'forecast'
  const { tokens } = useTheme()

  const query = useAccuracy({
    first: scope.first,
    last: scope.last,
    matching: scope.matching,
    horizon_h: queryHorizon,
  })
  const d = query.data?.data
  const stale = query.isPlaceholderData

  const curve = useMemo(
    () => (d ? curveOption(d.curve, tokens, horizon) : null),
    [d, tokens, horizon],
  )
  const heat = useMemo(
    () => (d ? heatmapOption(d.heatmap, d.heatmap_horizons, heatMetric, tokens) : null),
    [d, tokens, heatMetric],
  )
  const levels = useMemo(
    () => (d ? (levelBy === 'forecast' ? d.by_forecast_level : d.by_actual_level) : []),
    [d, levelBy],
  )
  const levelChart = useMemo(
    () =>
      d
        ? groupBiasOption(
            levels,
            tokens,
            levelBy === 'forecast' ? 'Forecast level' : 'Actual level',
          )
        : null,
    [d, levels, tokens, levelBy],
  )
  const hourChart = useMemo(
    () =>
      d
        ? groupBiasOption(
            d.by_hour.map((g) => ({ ...g, key: `${String(g.key).padStart(2, '0')}:00` })),
            tokens,
            'Hour of day (UK)',
          )
        : null,
    [d, tokens],
  )
  const hist = useMemo(() => (d ? histogramOption(d.error_histogram, tokens) : null), [d, tokens])
  const daily = useMemo(() => (d ? dailyBiasOption(d.daily, tokens) : null), [d, tokens])

  return (
    <>
      <PageHeader
        eyebrow="Forecast accuracy · requirement 2"
        title="How wrong is the forecast, and when?"
        lede="Error measured by horizon, hour of day, wind level and day, following the standard protocol for evaluating wind forecasts. Error is forecast − actual, so positive means less wind than forecast."
      />
      <FilterBar>
        <div className={s.sliderField}>
          <Field label="Horizon for the breakdowns">
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
                size="l"
                label={`MAE at ${horizon} h`}
                value={mw(d.summary.mae_mw)}
                detail={`nMAE ${pct(d.summary.nmae, 1)} of ${mw(d.capacity_proxy_mw)} proxy`}
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="Bias"
                value={signedMw(d.summary.bias_mw)}
                detail={`${pct((d.summary.bias_mw ?? 0) / (d.summary.mae_mw ?? 1))} of the MAE`}
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="Middle 80% of errors"
                value={`${signedMw(d.summary.err_p10_mw)}`}
                detail={`to ${signedMw(d.summary.err_p90_mw)}`}
              />
            </Card>
            <Card>
              <StatTile
                size="l"
                label="WAPE"
                value={pct(d.summary.wape, 1)}
                detail="Σ|error| ÷ Σ actual"
              />
            </Card>
          </Grid>

          {d.hindsight.mae_mw != null && d.summary.mae_mw != null && (
            <Callout tone="warning" title="The hindsight trap">
              Elexon&apos;s &ldquo;latest&rdquo; forecast for each hour is published after that hour
              has started. Scored against those, the average error would be {mw(d.hindsight.mae_mw)}
              , {pct(1 - d.hindsight.mae_mw / d.summary.mae_mw)} smaller than the{' '}
              {mw(d.summary.mae_mw)} that was actually knowable {horizon} h ahead. Windesk never
              uses those runs.
            </Callout>
          )}

          <Reveal>
            <Card
              title="Error grows with horizon"
              subtitle="MAE, RMSE and bias for the latest run published at least h hours before each target hour, with the band holding the middle 80% of errors."
            >
              {curve && (
                <EChart
                  option={curve}
                  label="Error by forecast horizon"
                  height={340}
                  stale={stale}
                />
              )}
              <DataTable
                caption="Error by horizon"
                columns={curveColumns}
                rows={d.curve}
                rowKey={(c) => String(c.horizon_h)}
                collapsible
              />
            </Card>
          </Reveal>

          <Grid cols={2}>
            <Reveal>
              <Card
                title="Where in the day the error sits"
                subtitle="Hour of day (UK) against horizon. Errors are larger overnight, when demand is low and wind is curtailed most."
                actions={
                  <Segmented
                    label="Heatmap metric"
                    hideLabel
                    value={heatMetric}
                    onChange={(v) => update({ heat: v === 'mae' ? null : v })}
                    options={[
                      { value: 'mae', label: 'MAE' },
                      { value: 'bias', label: 'Bias' },
                    ]}
                  />
                }
              >
                {heat && (
                  <EChart
                    option={heat}
                    label={`Heatmap of ${heatMetric} by hour and horizon`}
                    height={460}
                    stale={stale}
                  />
                )}
              </Card>
            </Reveal>
            <div className={s.stack}>
              <Reveal>
                <Card
                  title="Bias by wind level"
                  subtitle={
                    levelBy === 'forecast'
                      ? 'Grouped by what the forecast said: the view a buyer can act on. The bias grows with the forecast level.'
                      : 'Grouped by what actually happened. Selecting on the outcome inflates the bias in calm hours (regression to the mean).'
                  }
                  actions={
                    <Segmented
                      label="Group by"
                      hideLabel
                      value={levelBy}
                      onChange={(v) => update({ level: v === 'forecast' ? null : v })}
                      options={[
                        { value: 'forecast', label: 'Forecast' },
                        { value: 'actual', label: 'Actual' },
                      ]}
                    />
                  }
                >
                  {levelChart && (
                    <EChart
                      option={levelChart}
                      label="Bias by wind level"
                      height={240}
                      stale={stale}
                    />
                  )}
                  <DataTable
                    caption="Error by wind level"
                    columns={groupColumns}
                    rows={levels}
                    rowKey={(g) => g.key}
                    collapsible
                  />
                </Card>
              </Reveal>
              <Reveal>
                <Card
                  title="Error distribution"
                  subtitle={`All hours at ${horizon} h ahead, in 500 MW bins.`}
                >
                  {hist && (
                    <EChart
                      option={hist}
                      label="Histogram of forecast errors"
                      height={200}
                      stale={stale}
                    />
                  )}
                </Card>
              </Reveal>
            </div>
          </Grid>

          <Grid cols={2}>
            <Reveal>
              <Card title="Bias by hour of day" subtitle={`At ${horizon} h ahead.`}>
                {hourChart && (
                  <EChart
                    option={hourChart}
                    label="Bias by hour of day"
                    height={260}
                    stale={stale}
                  />
                )}
              </Card>
            </Reveal>
            <Reveal>
              <Card
                title="Day by day"
                subtitle="Daily bias (bars) and MAE (line). The bias depends on the weather regime, so it cannot be treated as a constant."
              >
                {daily && (
                  <EChart option={daily} label="Daily bias and MAE" height={260} stale={stale} />
                )}
              </Card>
            </Reveal>
          </Grid>

          <Callout tone="info" title="Reading the bias">
            WINDFOR runs about 15% above FUELHH at every level, with an extra jump in strong winds
            and overnight. This fits two likely causes: curtailment of wind farms (FUELHH is
            measured after curtailment) and differences in which wind farms each dataset covers. The
            Models page shows how much of the error a no-look-ahead adjustment removes.
          </Callout>
        </>
      )}
    </>
  )
}
