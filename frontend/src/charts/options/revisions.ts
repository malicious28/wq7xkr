/**
 * Forecast revisions: every WINDFOR run that covered one delivery day, so the
 * desk can see how the forecast moved as the day approached.
 *
 * There can be ~20 runs, far more than categorical colours allow, and they are
 * ordered by age, so they use an ordinal one-hue ramp (older = fainter). Only
 * the run the desk could use at the gate is drawn in the forecast colour, and
 * runs published after the gate are dashed.
 */
import type { ChartTokens } from '../../theme/context'
import { mw, ukDateTime, ukWallClockMs } from '../../lib/format'
import { baseOption, line, mwAxis, timeAxis, tooltipBox, type TooltipRow } from './base'

export interface RevisionRun {
  publish_time: string
  available: boolean
  points: { start_time: string; forecast_mw: number }[]
}

export interface RevisionActual {
  start_time: string
  actual_mw: number
}

export const USED_RUN = 'Run used at gate'
export const ACTUAL = 'Actual outturn'

/** Opacity for the i-th of n runs, oldest faintest; never below a visible floor. */
export function runOpacity(i: number, n: number): number {
  return n <= 1 ? 1 : 0.18 + (0.62 * i) / (n - 1)
}

export function revisionsOption(
  runs: RevisionRun[],
  actual: RevisionActual[],
  usedPublishTime: string | null,
  t: ChartTokens,
  showActual: boolean,
) {
  const series: object[] = runs.map((r, i) => {
    const used = r.publish_time === usedPublishTime
    const colour = used ? t.forecast : t.textSecondary
    return {
      ...line(colour, { dashed: !r.available, width: used ? 2.5 : 1.25 }),
      name: used ? USED_RUN : `Run ${ukDateTime(r.publish_time)}`,
      z: used ? 4 : 2,
      lineStyle: {
        color: colour,
        width: used ? 2.5 : 1.25,
        type: r.available ? 'solid' : 'dashed',
        opacity: used ? 1 : runOpacity(i, runs.length),
      },
      data: r.points.map((p) => [ukWallClockMs(p.start_time), p.forecast_mw]),
    }
  })
  if (showActual) {
    series.push({
      ...line(t.actual, { step: true }),
      name: ACTUAL,
      z: 5,
      data: actual.map((a) => [ukWallClockMs(a.start_time), a.actual_mw]),
    })
  }

  const byPublish = new Map(runs.map((r) => [r.publish_time, r]))
  const used = usedPublishTime ? byPublish.get(usedPublishTime) : undefined
  const latestAvailable = [...runs].reverse().find((r) => r.available)

  return {
    ...baseOption(t),
    legend: {
      ...baseOption(t).legend,
      data: [USED_RUN, ...(showActual ? [ACTUAL] : [])],
    },
    xAxis: timeAxis(t),
    yAxis: { ...mwAxis(t), min: 0 },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
      formatter: (params: { axisValue: number }[]) => {
        const x = params[0]?.axisValue
        if (x == null) return ''
        const valueAt = (r: RevisionRun | undefined) =>
          r?.points.find((p) => ukWallClockMs(p.start_time) === x)?.forecast_mw ?? null
        const first = runs[0]
        const last = runs.at(-1)
        const rows: TooltipRow[] = [
          { color: t.forecast, label: 'Run used at gate', value: mw(valueAt(used)) },
          { color: t.textSecondary, label: 'First run', value: mw(valueAt(first)) },
          {
            color: t.textSecondary,
            label: 'Last run before gate',
            value: mw(valueAt(latestAvailable)),
          },
          { color: t.textSecondary, label: 'Final run', value: mw(valueAt(last)), dashed: true },
        ]
        const a = actual.find((p) => ukWallClockMs(p.start_time) === x)
        if (showActual && a) rows.push({ color: t.actual, label: 'Actual', value: mw(a.actual_mw) })
        const spread = runs
          .map(valueAt)
          .filter((v): v is number => v != null)
          .reduce<[number, number]>(
            ([lo, hi], v) => [Math.min(lo, v), Math.max(hi, v)],
            [Infinity, -Infinity],
          )
        const foot =
          spread[0] <= spread[1]
            ? `Runs disagree by ${mw(spread[1] - spread[0])} at this hour`
            : undefined
        // x is already UK wall-clock time expressed as UTC, so read it back as UTC.
        return tooltipBox(`${new Date(x).toISOString().slice(11, 16)} UK`, rows, foot)
      },
    },
    series,
  }
}

/**
 * How far the forecast moved between the first run and the run used at the gate.
 * Runs cover different hours (later runs skip hours already started), so the
 * change is averaged only over the hours both runs cover.
 */
export function revisionSummary(
  runs: RevisionRun[],
  usedPublishTime: string | null,
): { firstToUsedMw: number | null; commonHours: number; runs: number; leadSpanH: number | null } {
  const first = runs[0]
  const used = runs.find((r) => r.publish_time === usedPublishTime)
  const last = runs.at(-1)
  const usedAt = new Map(used?.points.map((p) => [p.start_time, p.forecast_mw]))
  const diffs = (first?.points ?? [])
    .filter((p) => usedAt.has(p.start_time))
    .map((p) => usedAt.get(p.start_time)! - p.forecast_mw)
  const span =
    first && last
      ? (Date.parse(last.publish_time) - Date.parse(first.publish_time)) / 3_600_000
      : null
  return {
    firstToUsedMw: diffs.length ? diffs.reduce((a, b) => a + b, 0) / diffs.length : null,
    commonHours: diffs.length,
    runs: runs.length,
    leadSpanH: span,
  }
}
