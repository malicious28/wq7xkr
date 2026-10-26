/**
 * Live mode: Elexon's day-ahead forecast against Windesk's correction, day by day.
 */
import type { LiveDay } from '../../api/types'
import type { ChartTokens } from '../../theme/context'
import { mw, ukDay } from '../../lib/format'
import { axisLabel, baseOption, categoryAxis, line, mwAxis, tooltipBox } from './base'

export const LIVE_SERIES = {
  elexon: 'Elexon (WINDFOR)',
  windesk: 'Windesk corrected',
} as const

/** Days with at least one scored hour, oldest first. */
export function scoredDays(days: LiveDay[]): LiveDay[] {
  return days.filter((d) => d.elexon_mae_mw != null && d.windesk_mae_mw != null)
}

export function liveDailyOption(days: LiveDay[], t: ChartTokens) {
  const scored = scoredDays(days)
  return {
    ...baseOption(t),
    legend: { ...baseOption(t).legend, data: [LIVE_SERIES.elexon, LIVE_SERIES.windesk] },
    grid: { ...baseOption(t).grid, right: 24 },
    xAxis: {
      ...categoryAxis(
        t,
        scored.map((d) => ukDay(d.delivery_date)),
      ),
      boundaryGap: false,
      axisLabel: { ...axisLabel(t), interval: Math.max(0, Math.ceil(scored.length / 8) - 1) },
    },
    yAxis: mwAxis(t, 'Daily MAE'),
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
      formatter: (params: { dataIndex: number }[]) => {
        const d = scored[params[0]?.dataIndex ?? -1]
        if (!d) return ''
        return tooltipBox(
          ukDay(d.delivery_date),
          [
            { color: t.forecast, label: LIVE_SERIES.elexon, value: mw(d.elexon_mae_mw) },
            {
              color: t.adjusted,
              label: LIVE_SERIES.windesk,
              value: mw(d.windesk_mae_mw),
              dashed: true,
            },
          ],
          d.status === 'final' ? undefined : `${d.hours_actual} of ${d.hours_forecast} hours in`,
        )
      },
    },
    series: [
      { ...line(t.forecast), name: LIVE_SERIES.elexon, data: scored.map((d) => d.elexon_mae_mw) },
      {
        ...line(t.adjusted, { dashed: true }),
        name: LIVE_SERIES.windesk,
        data: scored.map((d) => d.windesk_mae_mw),
      },
    ],
  }
}
