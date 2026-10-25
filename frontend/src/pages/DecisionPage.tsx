import { useMemo } from 'react'

import { useDecision, useMeta } from '../api/hooks'
import type { AuctionId, DecisionPoint } from '../api/types'
import { EChart } from '../charts/EChart'
import { decisionOption } from '../charts/options/series'
import { DayStepper } from '../components/DayStepper'
import { RevisionsCard } from '../components/RevisionsCard'
import { RunTimeline } from '../components/RunTimeline'
import { ScopeFilters } from '../components/ScopeFilters'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  Button,
  Callout,
  Card,
  ErrorState,
  Field,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  Segmented,
  Select,
  StatTile,
} from '../components/ui/ui'
import { gwh, hours, minutes, mw, signedMw, ukDateTime, ukDay, ukTime, ukZone } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useParam, useScope } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './pages.module.css'

const DEFAULT_DAY = '2026-01-15'
const MARGINS = [0, 15, 30, 60, 120]

type AuctionChoice = AuctionId | 'custom'

const columns: Column<DecisionPoint>[] = [
  { key: 't', header: 'Hour (UK)', cell: (p) => ukTime(p.start_time) },
  { key: 'lead', header: 'Lead', cell: (p) => hours(p.lead_h), align: 'right' },
  { key: 'f', header: 'WINDFOR', cell: (p) => mw(p.forecast_mw), align: 'right' },
  { key: 'adj', header: 'Adjusted', cell: (p) => mw(p.ratio_mw), align: 'right' },
  { key: 'p10', header: 'P10', cell: (p) => mw(p.band_low_mw), align: 'right' },
  { key: 'p90', header: 'P90', cell: (p) => mw(p.band_high_mw), align: 'right' },
  { key: 'a', header: 'Actual', cell: (p) => mw(p.actual_mw), align: 'right' },
  {
    key: 'e',
    header: 'Error',
    cell: (p) =>
      signedMw(p.forecast_mw != null && p.actual_mw != null ? p.forecast_mw - p.actual_mw : null),
    align: 'right',
  },
]

export default function DecisionPage() {
  const meta = useMeta().data?.data
  const scope = useScope()
  const [params, update] = useParam()
  const { tokens } = useTheme()

  const day = params.get('day') ?? DEFAULT_DAY
  const auction = (params.get('auction') ?? meta?.auctions[0]?.id ?? 'n2ex_da') as AuctionChoice
  const gate = params.get('gate') ?? '12:00'
  const margin = Number(params.get('margin') ?? 0)
  const hindsight = params.get('hindsight') !== 'off'
  const showBand = params.get('band') !== 'off'
  const showAdjusted = params.get('adjusted') !== 'off'

  const decisionParams = {
    delivery_date: day,
    auction: auction === 'custom' ? undefined : auction,
    gate_local: auction === 'custom' ? gate : undefined,
    margin_min: margin,
    matching: scope.matching,
  }
  const query = useDecision(decisionParams, Boolean(meta))
  const d = query.data?.data

  const option = useMemo(
    () =>
      d
        ? decisionOption(d.points, d.actuals_half_hourly, tokens, {
            showActual: hindsight,
            showAdjusted,
            showBand,
            cutoffIso: d.cutoff,
          })
        : null,
    [d, tokens, hindsight, showAdjusted, showBand],
  )

  const minDay = meta ? meta.actual_first.slice(0, 10) : day
  const maxDay = meta ? meta.actual_last.slice(0, 10) : day
  const auctionMeta = meta?.auctions.find((a) => a.id === auction)
  const adjustedEnergy = d?.points.reduce((acc, p) => acc + (p.ratio_mw ?? 0), 0)
  const hasAdjusted = d?.points.some((p) => p.ratio_mw != null)
  const errorMwh =
    d?.energy_forecast_mwh != null && d.energy_actual_mwh != null
      ? d.energy_forecast_mwh - d.energy_actual_mwh
      : null
  // The export reproduces preset gates only; offering it for a custom gate or a margin
  // would download pairs that differ from the chart.
  const csv =
    auction !== 'custom' && margin === 0
      ? `/api/export/pairs.csv?first=${day}&last=${day}&auction=${auction}&matching=${scope.matching}`
      : null

  return (
    <>
      <PageHeader
        eyebrow="Decision support · requirement 1"
        title="The forecast you could act on"
        lede="Pick a delivery day and an auction. This shows the latest WINDFOR run that was published before the gate closed, how old it was, and the range the outturn is likely to fall in, based only on errors already known at that point."
      />

      <FilterBar>
        <DayStepper
          label="Delivery day"
          value={day}
          min={minDay}
          max={maxDay}
          onChange={(v) => update({ day: v === DEFAULT_DAY ? null : v })}
        />
        <Segmented<AuctionChoice>
          label="Auction (gate on D−1, UK time)"
          value={auction}
          onChange={(v) => update({ auction: v === meta?.auctions[0]?.id ? null : v })}
          options={[
            ...(meta?.auctions ?? []).map((a) => ({
              value: a.id as AuctionChoice,
              label: `${a.venue === 'Nord Pool' ? 'N2EX' : a.product === 'Hourly' ? 'EPEX 60' : 'EPEX 30'} · ${a.gate_local}`,
              title: a.name,
            })),
            { value: 'custom', label: 'Custom' },
          ]}
        />
        {auction === 'custom' && (
          <Field label="Gate time">
            {(id) => (
              <input
                id={id}
                type="time"
                className={s.timeInput}
                value={gate}
                onChange={(e) => update({ gate: e.target.value })}
              />
            )}
          </Field>
        )}
        <Field label="Safety margin">
          {(id) => (
            <Select
              id={id}
              value={String(margin)}
              onChange={(v) => update({ margin: v === '0' ? null : v })}
              options={MARGINS.map((m) => ({
                value: String(m),
                label: m === 0 ? 'None' : `${m} min before gate`,
              }))}
            />
          )}
        </Field>
        <ScopeFilters />
        <Segmented
          label="Outturn"
          value={hindsight ? 'on' : 'off'}
          onChange={(v) => update({ hindsight: v === 'on' ? null : 'off' })}
          options={[
            { value: 'off', label: 'As at gate' },
            { value: 'on', label: 'With hindsight' },
          ]}
        />
      </FilterBar>

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
      {!d && query.isPending && <Loading label="Selecting the run" />}

      {d && (
        <>
          <Grid cols={3} className={s.runGrid}>
            <Card
              className={s.span2}
              title="Forecast run used"
              subtitle={`Gate ${d.gate_local} UK on ${ukDay(d.cutoff.slice(0, 10))}${d.margin_min ? `, minus ${d.margin_min} min margin` : ''}${auctionMeta ? ` · ${auctionMeta.name}` : ''}`}
            >
              {d.run ? (
                <div className={s.runHeadline}>
                  <StatTile
                    size="l"
                    label="Published"
                    value={`${ukTime(d.run.publish_time)} ${ukZone(d.run.publish_time)}`}
                    detail={`${ukDay(d.run.publish_time.slice(0, 10))} · ${minutes(d.run_age_min)} before the cutoff`}
                  />
                  <StatTile
                    label="Lead time across the day"
                    value={`${hours(d.points[0]?.lead_h)} – ${hours(d.points.at(-1)?.lead_h)}`}
                    detail="From publication to each delivery hour"
                  />
                  <StatTile
                    label="Newer runs published later"
                    value={String(d.newer_runs_after_cutoff)}
                    detail="Not usable for this decision"
                  />
                </div>
              ) : (
                <Callout tone="critical" title="No forecast run before the cutoff" />
              )}
              <RunTimeline
                runs={d.runs_in_window}
                chosen={d.run}
                cutoff={d.cutoff}
                deliveryStart={d.points[0]?.start_time ?? d.cutoff}
                deliveryEnd={new Date(
                  new Date(d.points.at(-1)?.start_time ?? d.cutoff).getTime() + 3_600_000,
                ).toISOString()}
              />
            </Card>
            <div className={s.stack}>
              {d.warnings.length === 0 ? (
                <Callout tone="good" title="Run arrived on schedule">
                  The latest run was available {minutes(d.run_age_min)} before the cutoff.
                </Callout>
              ) : (
                d.warnings.map((w) => (
                  <Callout key={w} tone="warning">
                    {w}
                  </Callout>
                ))
              )}
              <Callout tone="info" title="How the band is built">
                From the previous {d.history_days ?? '—'} days of errors at this same gate, counting
                only outturn already published at the cutoff.
              </Callout>
            </div>
          </Grid>

          <Reveal>
            <Grid cols={4}>
              <Card>
                <StatTile
                  label="Wind energy forecast"
                  accent={tokens.forecast}
                  value={gwh(d.energy_forecast_mwh)}
                  detail="WINDFOR, delivery day total"
                />
              </Card>
              <Card>
                <StatTile
                  label="Bias-adjusted"
                  accent={tokens.adjusted}
                  value={hasAdjusted ? gwh(adjustedEnergy) : '—'}
                  detail="Trailing ratio adjustment"
                />
              </Card>
              <Card>
                <StatTile
                  label="Conservative (P10)"
                  accent={tokens.band}
                  value={gwh(d.energy_conservative_mwh)}
                  detail="Plan for at least this much"
                />
              </Card>
              <Card>
                <StatTile
                  label={hindsight ? 'Actual outturn' : 'Actual outturn (hidden)'}
                  accent={tokens.actual}
                  value={hindsight ? gwh(d.energy_actual_mwh) : '•••'}
                  detail={
                    hindsight && errorMwh != null
                      ? `WINDFOR was ${errorMwh > 0 ? 'high' : 'low'} by ${gwh(Math.abs(errorMwh))}`
                      : 'Switch to hindsight to compare'
                  }
                />
              </Card>
            </Grid>
          </Reveal>

          <Reveal>
            <Card
              title={`Wind generation, ${ukDay(day)}`}
              subtitle={`Hourly WINDFOR from the ${d.run ? ukDateTime(d.run.publish_time) : '—'} run${showBand ? ', with the 80% range the outturn is expected to fall in' : ''}${hindsight ? ', and the half-hourly outturn' : ''}.`}
              actions={
                csv && (
                  <Button icon="download" href={csv} download>
                    CSV
                  </Button>
                )
              }
              footer={
                <>
                  WINDFOR is hourly, so a half-hourly product uses the same value for both
                  half-hours. The P10 line is the conservative wind assumption: plan to buy the rest
                  of demand on top of it.
                </>
              }
            >
              <div className={s.chartToggles}>
                <Segmented
                  label="Range"
                  hideLabel
                  value={showBand ? 'on' : 'off'}
                  onChange={(v) => update({ band: v === 'on' ? null : 'off' })}
                  options={[
                    { value: 'on', label: 'P10–P90 range' },
                    { value: 'off', label: 'No range' },
                  ]}
                />
                <Segmented
                  label="Adjusted"
                  hideLabel
                  value={showAdjusted ? 'on' : 'off'}
                  onChange={(v) => update({ adjusted: v === 'on' ? null : 'off' })}
                  options={[
                    { value: 'on', label: 'Show adjusted' },
                    { value: 'off', label: 'Hide adjusted' },
                  ]}
                />
              </div>
              {option && (
                <EChart
                  option={option}
                  label={`Forecast and range for ${ukDay(day)}`}
                  height={380}
                  stale={query.isPlaceholderData}
                />
              )}
              <DataTable
                caption="Hourly values for the delivery day"
                columns={columns}
                rows={d.points}
                rowKey={(p) => p.start_time}
                collapsible
              />
            </Card>
          </Reveal>

          <Reveal>
            <RevisionsCard params={decisionParams} hindsight={hindsight} />
          </Reveal>

          {hindsight && d.day_summary && (
            <Reveal>
              <Grid cols={4}>
                <Card>
                  <StatTile
                    label="Day bias"
                    value={signedMw(d.day_summary.bias_mw)}
                    detail="Mean of forecast − actual"
                  />
                </Card>
                <Card>
                  <StatTile
                    label="Day MAE"
                    value={mw(d.day_summary.mae_mw)}
                    detail={`${d.day_summary.n} hours`}
                  />
                </Card>
                <Card>
                  <StatTile
                    label="Worst hour (P90 |error|)"
                    value={mw(d.day_summary.abs_err_p90_mw)}
                  />
                </Card>
                <Card>
                  <StatTile
                    label="Hours inside the range"
                    value={`${d.points.filter((p) => p.actual_mw != null && p.band_low_mw != null && p.actual_mw >= p.band_low_mw && p.actual_mw <= (p.band_high_mw ?? Infinity)).length} / ${d.points.filter((p) => p.band_low_mw != null).length}`}
                    detail="Target: about 80%"
                  />
                </Card>
              </Grid>
            </Reveal>
          )}
        </>
      )}
    </>
  )
}
