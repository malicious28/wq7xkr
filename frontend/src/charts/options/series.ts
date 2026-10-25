/**
 * Time-series charts: the decision day, the horizon explorer and ramps.
 */
import type { DecisionPoint, HorizonPoint, RampEvent } from '../../api/types'
import type { ChartTokens } from '../../theme/context'
import { hours, mw, signedMw, ukDateTime, ukTime, ukWallClockMs } from '../../lib/format'
import { baseOption, line, mwAxis, timeAxis, tooltipBox, type TooltipRow } from './base'

type Pt = [number, number | null]

interface HalfHour {
  start_time: string
  actual_mw: number
}

export interface DecisionChartOpts {
  showActual: boolean
  showAdjusted: boolean
  showBand: boolean
  cutoffIso?: string
}

export const SERIES = {
  forecast: 'WINDFOR forecast',
  adjusted: 'Bias-adjusted',
  actual: 'Actual outturn',
  band: 'P10–P90 range',
} as const

export function decisionOption(
  points: DecisionPoint[],
  halfHourly: HalfHour[],
  t: ChartTokens,
  opts: DecisionChartOpts,
) {
  const x = points.map((p) => ukWallClockMs(p.start_time))
  const low: Pt[] = points.map((p, i) => [x[i]!, p.band_low_mw])
  const width: Pt[] = points.map((p, i) => [
    x[i]!,
    p.band_low_mw != null && p.band_high_mw != null ? p.band_high_mw - p.band_low_mw : null,
  ])
  const byX = new Map(points.map((p, i) => [x[i]!, p]))
  const hhByX = new Map(halfHourly.map((h) => [ukWallClockMs(h.start_time), h.actual_mw]))

  const series: object[] = []
  if (opts.showBand) {
    series.push(
      {
        ...line('transparent'),
        name: '_band_low',
        data: low,
        stack: 'band',
        silent: true,
        lineStyle: { width: 0 },
        tooltip: { show: false },
      },
      {
        ...line('transparent'),
        name: SERIES.band,
        data: width,
        stack: 'band',
        silent: true,
        lineStyle: { width: 0 },
        areaStyle: { color: t.band },
        itemStyle: { color: t.band },
      },
    )
  }
  series.push({
    ...line(t.forecast),
    name: SERIES.forecast,
    data: points.map((p, i) => [x[i]!, p.forecast_mw]),
  })
  if (opts.showAdjusted) {
    series.push({
      ...line(t.adjusted, { dashed: true }),
      name: SERIES.adjusted,
      data: points.map((p, i) => [x[i]!, p.ratio_mw]),
    })
  }
  if (opts.showActual) {
    series.push({
      ...line(t.actual, { step: true }),
      name: SERIES.actual,
      data: halfHourly.map((h) => [ukWallClockMs(h.start_time), h.actual_mw]),
    })
  }

  return {
    ...baseOption(t),
    legend: {
      ...baseOption(t).legend,
      data: [
        SERIES.forecast,
        opts.showAdjusted && SERIES.adjusted,
        opts.showActual && SERIES.actual,
        opts.showBand && SERIES.band,
      ].filter(Boolean),
    },
    grid: { ...baseOption(t).grid, right: 72 },
    xAxis: timeAxis(t),
    yAxis: { ...mwAxis(t), min: 0 },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
      formatter: (params: { axisValue: number }[]) => {
        const axisX = params[0]?.axisValue
        if (axisX == null) return ''
        const hourX = axisX - (axisX % 3_600_000)
        const p = byX.get(hourX)
        const rows: TooltipRow[] = []
        if (p) {
          rows.push({ color: t.forecast, label: 'WINDFOR forecast', value: mw(p.forecast_mw) })
          if (opts.showAdjusted)
            rows.push({
              color: t.adjusted,
              label: 'Bias-adjusted',
              value: mw(p.ratio_mw),
              dashed: true,
            })
          if (opts.showBand && p.band_low_mw != null) {
            rows.push({ color: t.forecast, label: 'P10 (conservative)', value: mw(p.band_low_mw) })
            rows.push({ color: t.forecast, label: 'P90 (optimistic)', value: mw(p.band_high_mw) })
          }
        }
        const actual = hhByX.get(axisX)
        if (opts.showActual && actual != null)
          rows.push({ color: t.actual, label: 'Actual (half-hour)', value: mw(actual) })
        const title = p ? `${ukTime(p.start_time)} UK · lead ${hours(p.lead_h)}` : ''
        return tooltipBox(title, rows)
      },
    },
    series,
  }
}

export function horizonOption(points: HorizonPoint[], t: ChartTokens, horizonH: number) {
  const x = points.map((p) => ukWallClockMs(p.start_time))
  const byX = new Map(points.map((p, i) => [x[i]!, p]))
  return {
    ...baseOption(t),
    legend: { ...baseOption(t).legend, data: [SERIES.actual, SERIES.forecast] },
    grid: { ...baseOption(t).grid, bottom: 56 },
    xAxis: timeAxis(t),
    yAxis: { ...mwAxis(t), min: 0 },
    dataZoom: [
      { type: 'inside', throttle: 30 },
      {
        type: 'slider',
        height: 22,
        bottom: 8,
        borderColor: t.grid,
        backgroundColor: 'transparent',
        fillerColor: t.band,
        dataBackground: { lineStyle: { color: t.axis }, areaStyle: { color: 'transparent' } },
        handleStyle: { color: t.textMuted, borderColor: t.textMuted },
        moveHandleStyle: { color: t.textMuted },
        textStyle: { color: t.textMuted, fontSize: 10 },
        labelFormatter: '',
      },
    ],
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
      formatter: (params: { axisValue: number }[]) => {
        const p = byX.get(params[0]?.axisValue ?? -1)
        if (!p) return ''
        const err =
          p.forecast_mw != null && p.actual_mw != null ? p.forecast_mw - p.actual_mw : null
        const rows: TooltipRow[] = [
          { color: t.actual, label: 'Actual (hour mean)', value: mw(p.actual_mw) },
          { color: t.forecast, label: `Forecast ≥${horizonH} h ahead`, value: mw(p.forecast_mw) },
          { color: 'transparent', label: 'Error (forecast − actual)', value: signedMw(err) },
        ]
        const foot = p.publish_time
          ? `Run published ${ukDateTime(p.publish_time)} UK · lead ${hours(p.lead_h)}`
          : 'No run at this horizon'
        return tooltipBox(`${ukDateTime(p.start_time)} UK`, rows, foot)
      },
    },
    series: [
      { ...line(t.actual), name: SERIES.actual, data: points.map((p, i) => [x[i]!, p.actual_mw]) },
      {
        ...line(t.forecast),
        name: SERIES.forecast,
        data: points.map((p, i) => [x[i]!, p.forecast_mw]),
        connectNulls: false,
      },
    ],
  }
}

export function rampOption(points: HorizonPoint[], events: RampEvent[], t: ChartTokens) {
  const x = points.map((p) => ukWallClockMs(p.start_time))
  const actualByX = new Map(points.map((p, i) => [x[i]!, p.actual_mw]))
  const outcomeColor = (o: string | null) =>
    o === 'hit' ? t.good : o === 'miss' ? t.critical : t.textMuted
  const marker = (dir: 'up' | 'down') =>
    events
      .filter((e) => e.direction === dir)
      .map((e) => {
        const ex = ukWallClockMs(e.start_time)
        return {
          value: [ex, actualByX.get(ex) ?? null],
          itemStyle: { color: outcomeColor(e.outcome), borderColor: t.surface, borderWidth: 2 },
          event: e,
        }
      })
  const markerSeries = (dir: 'up' | 'down') => ({
    type: 'scatter' as const,
    name: dir === 'up' ? 'Up-ramp start' : 'Down-ramp start',
    symbol: dir === 'up' ? 'triangle' : 'path://M0,0 L10,0 L5,9 Z',
    symbolSize: 12,
    z: 5,
    data: marker(dir),
    tooltip: {
      trigger: 'item' as const,
      formatter: (p: { data: { event: RampEvent } }) => {
        const e = p.data.event
        return tooltipBox(`${ukDateTime(e.start_time)} UK`, [
          {
            color: outcomeColor(e.outcome),
            label: `${e.direction}-ramp over the window`,
            value: signedMw(e.delta_mw),
          },
          {
            color: 'transparent',
            label: 'Forecast outcome',
            value: e.outcome === 'hit' ? 'Caught' : 'Missed',
          },
        ])
      },
    },
  })
  return {
    ...baseOption(t),
    legend: { ...baseOption(t).legend, data: [SERIES.actual, SERIES.forecast] },
    grid: { ...baseOption(t).grid, bottom: 56 },
    xAxis: timeAxis(t),
    yAxis: { ...mwAxis(t), min: 0 },
    dataZoom: [
      { type: 'inside' },
      {
        type: 'slider',
        height: 22,
        bottom: 8,
        borderColor: t.grid,
        fillerColor: t.band,
        labelFormatter: '',
        textStyle: { color: t.textMuted },
      },
    ],
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
    },
    series: [
      {
        ...line(t.actual),
        name: SERIES.actual,
        data: points.map((p, i) => [x[i]!, p.actual_mw]),
        tooltip: { show: false },
      },
      {
        ...line(t.forecast, { width: 1.5 }),
        name: SERIES.forecast,
        data: points.map((p, i) => [x[i]!, p.forecast_mw]),
        tooltip: { show: false },
      },
      markerSeries('up'),
      markerSeries('down'),
    ],
  }
}
