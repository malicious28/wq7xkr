import { useMemo } from 'react'

import { useLiveDay, useLiveSummary, useMeta } from '../api/hooks'
import type { AuctionId, LiveDay } from '../api/types'
import { EChart } from '../charts/EChart'
import { liveDailyOption } from '../charts/options/live'
import { decisionOption } from '../charts/options/series'
import { DayStepper } from '../components/DayStepper'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  Callout,
  Card,
  ErrorState,
  FilterBar,
  Grid,
  Loading,
  PageHeader,
  Segmented,
  StatTile,
  StatusPill,
} from '../components/ui/ui'
import { dayState, defaultLiveDay } from '../lib/live'
import { addDays, gwh, mw, pct, ukDateTime, ukDay, ukTime, ukToday } from '../lib/format'
import { Reveal } from '../motion/Reveal'
import { useParam } from '../state/filters'
import { useTheme } from '../theme/context'
import s from './pages.module.css'

const DEFAULT_AUCTION: AuctionId = 'n2ex_da'

const columns: Column<LiveDay>[] = [
  { key: 'd', header: 'Delivery day', cell: (d) => ukDay(d.delivery_date) },
  { key: 's', header: 'Status', cell: (d) => dayState(d).label },
  { key: 'e', header: 'Elexon', cell: (d) => gwh(d.energy_elexon_mwh), align: 'right' },
  { key: 'w', header: 'Windesk', cell: (d) => gwh(d.energy_windesk_mwh), align: 'right' },
  { key: 'a', header: 'Actual', cell: (d) => gwh(d.energy_actual_mwh), align: 'right' },
  { key: 'em', header: 'Elexon MAE', cell: (d) => mw(d.elexon_mae_mw), align: 'right' },
  { key: 'wm', header: 'Windesk MAE', cell: (d) => mw(d.windesk_mae_mw), align: 'right' },
]

export default function LivePage() {
  const meta = useMeta().data?.data
  const [params, update] = useParam()
  const { tokens } = useTheme()

  const auction = (params.get('auction') ?? DEFAULT_AUCTION) as AuctionId
  const summaryQuery = useLiveSummary(auction)
  const summary = summaryQuery.data?.data
  const status = summary?.status

  const fallbackDay = summary ? defaultLiveDay(summary.days, ukToday()) : undefined
  const day = params.get('day') ?? fallbackDay
  const dayQuery = useLiveDay(day, auction)
  const detail = dayQuery.data?.data
  const selected = summary?.days.find((d) => d.delivery_date === day) ?? detail?.day

  const dayOption = useMemo(
    () =>
      detail
        ? decisionOption(detail.points, detail.actuals_half_hourly, tokens, {
            showActual: detail.actuals_half_hourly.length > 0,
            showAdjusted: true,
            showBand: true,
            cutoffIso: detail.day.cutoff,
          })
        : null,
    [detail, tokens],
  )
  const dailyOption = useMemo(
    () => (summary ? liveDailyOption(summary.days, tokens) : null),
    [summary, tokens],
  )

  const board = summary?.scoreboard
  const firstDay = status?.live_start ?? day ?? ''
  const lastDay = summary?.days.at(-1)?.delivery_date ?? firstDay
  const state = selected ? dayState(selected) : null

  return (
    <>
      <PageHeader
        eyebrow="Try now · live Elexon data"
        title="Tomorrow's wind, corrected"
        lede="The same method as the January study, running on today's data. Each time Elexon publishes a new wind forecast, Windesk takes the newest run, removes the bias it has measured over the last four weeks, and gives a corrected number and a safe range for every hour. Every day since 1 October is kept, so you can check how it did."
      />

      {status && (
        <Callout
          tone={status.stale ? 'warning' : 'good'}
          title={status.stale ? 'Elexon is not responding: showing the last good data' : 'Live'}
        >
          Newest Elexon run {status.newest_run ? ukDateTime(status.newest_run) : '—'} UK · checked{' '}
          {ukTime(status.fetched_at)} · next check {ukTime(status.next_refresh)}. Decisions use the{' '}
          {status.gate_local} UK gate on the day before delivery.
        </Callout>
      )}

      <FilterBar>
        {day && (
          <DayStepper
            label="Delivery day"
            value={day}
            min={firstDay}
            max={lastDay}
            onChange={(v) => update({ day: v === fallbackDay ? null : v })}
          />
        )}
        <Segmented<AuctionId>
          label="Auction (gate on D−1, UK time)"
          value={auction}
          onChange={(v) => update({ auction: v === DEFAULT_AUCTION ? null : v })}
          options={(meta?.auctions ?? []).map((a) => ({
            value: a.id,
            label: `${a.venue === 'Nord Pool' ? 'N2EX' : a.product === 'Hourly' ? 'EPEX 60' : 'EPEX 30'} · ${a.gate_local}`,
            title: a.name,
          }))}
        />
      </FilterBar>

      {summaryQuery.isError && (
        <ErrorState error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />
      )}
      {!summary && summaryQuery.isPending && <Loading label="Fetching the latest Elexon runs" />}

      {selected && day && (
        <Reveal>
          <Card
            title={ukDay(day)}
            subtitle={
              selected.gate_passed
                ? `Uses the ${selected.run_publish_time ? ukDateTime(selected.run_publish_time) : '—'} run, the newest one published before the gate.`
                : `Uses the newest run so far (${selected.run_publish_time ? ukDateTime(selected.run_publish_time) : '—'}). It will change with each new Elexon run until the gate at ${status?.gate_local ?? ''} UK on ${ukDay(addDays(day, -1))}.`
            }
            actions={state && <StatusPill tone={state.tone}>{state.label}</StatusPill>}
            footer={
              <>
                The dashed line is Windesk&apos;s corrected forecast. The shaded range is where the
                outturn has landed about 80% of the time; its lower edge (P10) is the safe minimum
                to plan on.
              </>
            }
          >
            <Grid cols={4}>
              <StatTile
                label="Elexon predicted"
                accent={tokens.forecast}
                value={gwh(selected.energy_elexon_mwh)}
                detail={
                  selected.elexon_mae_mw != null
                    ? `Off by ${mw(selected.elexon_mae_mw)} an hour`
                    : selected.hours_forecast < selected.hours_in_day
                      ? `${selected.hours_forecast} of ${selected.hours_in_day} hours forecast so far`
                      : 'WINDFOR, day total'
                }
              />
              <StatTile
                label="Windesk predicted"
                accent={tokens.adjusted}
                value={gwh(selected.energy_windesk_mwh)}
                detail={
                  selected.windesk_mae_mw != null
                    ? `Off by ${mw(selected.windesk_mae_mw)} an hour`
                    : 'Bias removed, same hours'
                }
              />
              <StatTile
                label="Safe minimum (P10)"
                accent={tokens.band}
                value={gwh(selected.energy_p10_mwh)}
                detail="Plan for at least this much"
              />
              <StatTile
                label="Actually generated"
                accent={tokens.actual}
                value={selected.hours_actual ? gwh(selected.energy_actual_mwh) : 'Not yet'}
                detail={
                  selected.status === 'final'
                    ? 'All hours in'
                    : `${selected.hours_actual} of ${selected.hours_in_day} hours in`
                }
              />
            </Grid>
            {dayQuery.isError && <ErrorState error={dayQuery.error} />}
            {dayOption && (
              <div className={s.chartGap}>
                <EChart
                  option={dayOption}
                  label={`Elexon, Windesk and actual wind for ${ukDay(day)}`}
                  height={360}
                  stale={dayQuery.isPlaceholderData}
                />
              </div>
            )}
          </Card>
        </Reveal>
      )}

      {summary && board && (
        <Reveal>
          <Card
            title={`Scoreboard since ${ukDay(summary.status.live_start)}`}
            subtitle="Every hour where Elexon's forecast, Windesk's correction and the outturn are all known. Each day uses only what was published before its gate."
          >
            <Grid cols={4}>
              <StatTile
                label="Elexon average miss"
                accent={tokens.forecast}
                value={mw(board.elexon_mae_mw)}
                detail={`Mean absolute error, ${board.n_hours} hours`}
              />
              <StatTile
                label="Windesk average miss"
                accent={tokens.adjusted}
                value={mw(board.windesk_mae_mw)}
                detail="Same hours, same runs"
              />
              <StatTile
                size="l"
                label="Error reduced by"
                value={pct(board.skill)}
                detail="Windesk versus Elexon"
              />
              <StatTile
                label="Inside the safe range"
                value={pct(board.band_coverage)}
                detail="Target: about 80%"
              />
            </Grid>
            {dailyOption && (
              <div className={s.chartGap}>
                <EChart
                  option={dailyOption}
                  label="Daily mean absolute error, Elexon versus Windesk"
                  height={300}
                />
              </div>
            )}
            <DataTable
              caption="Every live delivery day, newest first"
              columns={columns}
              rows={[...summary.days].reverse()}
              rowKey={(d) => d.delivery_date}
              collapsible
            />
          </Card>
        </Reveal>
      )}

      {summary && (
        <div className={s.stack}>
          <Callout tone="info" title="Why this is a fair test">
            Each past day is scored with the run a buyer could actually have used at the gate, and
            the correction for that day was fitted only on errors already published by then. Nothing
            is re-fitted after the fact.
          </Callout>
        </div>
      )}
    </>
  )
}
