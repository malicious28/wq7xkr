/**
 * Accuracy and model charts.
 *
 * Metric lines (MAE, RMSE, bias) are not entities, so they wear ink rather
 * than series colours: blue/orange/aqua/violet always mean forecast / actual /
 * adjusted / persistence across the whole app. Signed quantities use the
 * diverging scale (warm = forecast too high = buyer short).
 */
import type { CurvePoint, GroupStat, HeatCell, ModelScore } from '../../api/types'
import type { ChartTokens } from '../../theme/context'
import { mw, pct, signedMw, signedPct, ukDay } from '../../lib/format'
import { axisLabel, baseOption, categoryAxis, line, mwAxis, signColor, tooltipBox } from './base'

interface DailyStat {
  delivery_date: string
  bias_mw: number | null
  mae_mw: number | null
}

interface HistBin {
  bin_start_mw: number
  count: number
}

interface DailyModel {
  delivery_date: string
  raw_mae_mw: number | null
  ratio_mae_mw: number | null
  debiased_mae_mw: number | null
}

export function curveOption(curve: CurvePoint[], t: ChartTokens, selectedH: number) {
  const hs = curve.map((c) => c.horizon_h)
  const p10 = curve.map((c) => c.err_p10_mw)
  const spread = curve.map((c) =>
    c.err_p10_mw != null && c.err_p90_mw != null ? c.err_p90_mw - c.err_p10_mw : null,
  )
  return {
    ...baseOption(t),
    legend: { ...baseOption(t).legend, data: ['MAE', 'RMSE', 'Bias', 'Error P10–P90'] },
    grid: { ...baseOption(t).grid, bottom: 28 },
    xAxis: {
      ...categoryAxis(t, hs, 'Forecast horizon (hours ahead)'),
      boundaryGap: false,
      axisLabel: { ...axisLabel(t), interval: 5 },
    },
    yAxis: mwAxis(t),
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
      formatter: (params: { dataIndex: number }[]) => {
        const c = curve[params[0]?.dataIndex ?? -1]
        if (!c) return ''
        return tooltipBox(
          `${c.horizon_h} h ahead · n = ${c.n}`,
          [
            { color: t.textPrimary, label: 'MAE', value: mw(c.mae_mw) },
            { color: t.textSecondary, label: 'RMSE', value: mw(c.rmse_mw), dashed: true },
            { color: t.divPos, label: 'Bias (forecast − actual)', value: signedMw(c.bias_mw) },
            {
              color: t.band,
              label: 'Error P10 … P90',
              value: `${signedMw(c.err_p10_mw)} … ${signedMw(c.err_p90_mw)}`,
            },
          ],
          c.coverage < 1
            ? `Forecast available for ${pct(c.coverage)} of hours at this horizon`
            : undefined,
        )
      },
    },
    series: [
      {
        ...line('transparent'),
        name: '_p10',
        data: p10,
        stack: 'q',
        lineStyle: { width: 0 },
        silent: true,
      },
      {
        ...line('transparent'),
        name: 'Error P10–P90',
        data: spread,
        stack: 'q',
        lineStyle: { width: 0 },
        areaStyle: { color: t.band },
        itemStyle: { color: t.band },
        silent: true,
      },
      { ...line(t.textPrimary), name: 'MAE', data: curve.map((c) => c.mae_mw) },
      {
        ...line(t.textSecondary, { dashed: true }),
        name: 'RMSE',
        data: curve.map((c) => c.rmse_mw),
      },
      {
        ...line(t.divPos),
        name: 'Bias',
        data: curve.map((c) => c.bias_mw),
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: t.textMuted, type: 'solid', width: 1 },
          label: { color: t.textSecondary, formatter: `${selectedH} h`, fontSize: 11 },
          data: [{ xAxis: String(selectedH) }],
        },
      },
    ],
  }
}

export function heatmapOption(
  cells: HeatCell[],
  horizons: number[],
  metric: 'mae' | 'bias',
  t: ChartTokens,
) {
  const hoursOfDay = Array.from({ length: 24 }, (_, h) => h)
  const values = cells
    .map((c) => (metric === 'mae' ? c.mae_mw : c.bias_mw))
    .filter((v): v is number => v != null)
  const absMax = Math.max(1, ...values.map(Math.abs))
  const min = metric === 'mae' ? Math.min(...values) : -absMax
  const max = metric === 'mae' ? Math.max(...values) : absMax
  const data = cells.map((c) => [
    horizons.indexOf(c.horizon_h),
    c.hour_local,
    metric === 'mae' ? c.mae_mw : c.bias_mw,
    c.n,
  ])
  return {
    ...baseOption(t),
    grid: { left: 8, right: 8, top: 8, bottom: 76 },
    xAxis: {
      ...categoryAxis(
        t,
        horizons.map((h) => `${h} h`),
        'Horizon',
      ),
      splitArea: { show: false },
    },
    yAxis: {
      ...categoryAxis(
        t,
        hoursOfDay.map((h) => `${String(h).padStart(2, '0')}:00`),
      ),
      inverse: true,
      axisLabel: { ...axisLabel(t), interval: 2 },
    },
    visualMap: {
      type: 'continuous',
      dimension: 2, // the metric; the default (last dimension) is the sample count
      min,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 12,
      itemHeight: 220,
      text: metric === 'mae' ? [mw(max), mw(min)] : ['Forecast high', 'Forecast low'],
      textStyle: { color: t.textMuted, fontSize: 11 },
      inRange: { color: metric === 'mae' ? t.seq : [t.divNeg, t.divMid, t.divPos] },
    },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'item',
      formatter: (p: { data: [number, number, number | null, number] }) => {
        const [xi, hour, v, n] = p.data
        return tooltipBox(`${String(hour).padStart(2, '0')}:00 UK · ${horizons[xi]} h ahead`, [
          {
            color: 'transparent',
            label: metric === 'mae' ? 'Mean absolute error' : 'Bias (forecast − actual)',
            value: metric === 'mae' ? mw(v) : signedMw(v),
          },
          { color: 'transparent', label: 'Hours in sample', value: String(n) },
        ])
      },
    },
    series: [
      {
        type: 'heatmap',
        data,
        itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 3 },
        emphasis: { itemStyle: { borderColor: t.textPrimary, borderWidth: 1 } },
      },
    ],
  }
}

/** Bias per bucket as bars coloured by sign, labelled at the tip. */
export function groupBiasOption(groups: GroupStat[], t: ChartTokens, axisName: string) {
  return {
    ...baseOption(t),
    grid: { ...baseOption(t).grid, top: 24, bottom: 28 },
    xAxis: categoryAxis(
      t,
      groups.map((g) => g.key),
      axisName,
    ),
    yAxis: mwAxis(t, 'Bias MW'),
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const g = groups[p.dataIndex]
        if (!g) return ''
        return tooltipBox(g.key, [
          { color: signColor(t, g.bias_mw), label: 'Bias', value: signedMw(g.bias_mw) },
          { color: 'transparent', label: 'MAE', value: mw(g.mae_mw) },
          { color: 'transparent', label: 'Hours', value: String(g.n) },
        ])
      },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 36,
        data: groups.map((g) => ({
          value: g.bias_mw,
          itemStyle: {
            color: signColor(t, g.bias_mw),
            borderRadius: (g.bias_mw ?? 0) >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
          },
        })),
        label: {
          show: groups.length <= 8, // never a number on every bar; table + tooltip carry it
          position: 'top',
          color: t.textSecondary,
          fontSize: 11,
          formatter: (p: { value: number }) => signedMw(p.value).replace(' MW', ''),
        },
      },
    ],
  }
}

export function histogramOption(bins: HistBin[], t: ChartTokens) {
  const labels = bins.map((b) => b.bin_start_mw)
  return {
    ...baseOption(t),
    grid: { ...baseOption(t).grid, top: 16, bottom: 28 },
    xAxis: {
      ...categoryAxis(t, labels, 'Error, forecast − actual (MW, 500 MW bins)'),
      axisLabel: { ...axisLabel(t), formatter: (v: string) => `${Number(v) / 1000}K`, interval: 3 },
    },
    yAxis: {
      type: 'value',
      name: 'Hours',
      axisLabel: axisLabel(t),
      splitLine: { lineStyle: { color: t.grid } },
      nameTextStyle: { color: t.textMuted, fontSize: 11 },
    },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const b = bins[p.dataIndex]
        if (!b) return ''
        return tooltipBox(`${signedMw(b.bin_start_mw)} to ${signedMw(b.bin_start_mw + 500)}`, [
          { color: signColor(t, b.bin_start_mw + 250), label: 'hours', value: String(b.count) },
        ])
      },
    },
    series: [
      {
        type: 'bar',
        barCategoryGap: '8%',
        data: bins.map((b) => ({
          value: b.count,
          itemStyle: { color: signColor(t, b.bin_start_mw + 250), borderRadius: [3, 3, 0, 0] },
        })),
      },
    ],
  }
}

export function dailyBiasOption(daily: DailyStat[], t: ChartTokens) {
  return {
    ...baseOption(t),
    legend: { ...baseOption(t).legend, data: ['Daily bias', 'Daily MAE'] },
    grid: { ...baseOption(t).grid, bottom: 8 },
    xAxis: {
      ...categoryAxis(
        t,
        daily.map((d) => ukDay(d.delivery_date)),
      ),
      axisLabel: { ...axisLabel(t), interval: 4 },
    },
    yAxis: mwAxis(t),
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(127,127,127,0.08)' } },
      formatter: (params: { dataIndex: number }[]) => {
        const d = daily[params[0]?.dataIndex ?? -1]
        if (!d) return ''
        return tooltipBox(ukDay(d.delivery_date), [
          { color: signColor(t, d.bias_mw), label: 'Bias', value: signedMw(d.bias_mw) },
          { color: t.textPrimary, label: 'MAE', value: mw(d.mae_mw) },
        ])
      },
    },
    series: [
      {
        type: 'bar',
        name: 'Daily bias',
        barCategoryGap: '20%',
        itemStyle: { color: t.divPos },
        data: daily.map((d) => ({
          value: d.bias_mw,
          itemStyle: {
            color: signColor(t, d.bias_mw),
            borderRadius: (d.bias_mw ?? 0) >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
          },
        })),
      },
      {
        ...line(t.textPrimary, { width: 1.5 }),
        name: 'Daily MAE',
        data: daily.map((d) => d.mae_mw),
      },
    ],
  }
}

export const MODEL_LABEL: Record<ModelScore['model'], string> = {
  raw: 'WINDFOR as published',
  debiased: 'Additive debias',
  ratio: 'Ratio-adjusted',
  persistence: 'Persistence',
}

export function modelColor(t: ChartTokens, m: ModelScore['model']): string {
  return { raw: t.forecast, debiased: t.debiased, ratio: t.adjusted, persistence: t.persistence }[m]
}

export function modelBarsOption(scores: ModelScore[], t: ChartTokens) {
  const ordered = [...scores].sort((a, b) => (b.mae_mw ?? 0) - (a.mae_mw ?? 0))
  return {
    ...baseOption(t),
    grid: { left: 8, right: 96, top: 8, bottom: 8 },
    xAxis: { type: 'value', show: false, max: (v: { max: number }) => v.max * 1.05 },
    yAxis: {
      type: 'category',
      data: ordered.map((s) => MODEL_LABEL[s.model]),
      axisLabel: { ...axisLabel(t), color: t.textSecondary, fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const s = ordered[p.dataIndex]
        if (!s) return ''
        return tooltipBox(MODEL_LABEL[s.model], [
          { color: modelColor(t, s.model), label: 'MAE', value: mw(s.mae_mw) },
          { color: 'transparent', label: 'RMSE', value: mw(s.rmse_mw) },
          { color: 'transparent', label: 'Bias', value: signedMw(s.bias_mw) },
          { color: 'transparent', label: 'Skill vs WINDFOR', value: signedPct(s.skill_vs_raw) },
        ])
      },
    },
    series: [
      {
        type: 'bar',
        barWidth: 18,
        data: ordered.map((s) => ({
          value: s.mae_mw,
          itemStyle: { color: modelColor(t, s.model), borderRadius: [0, 4, 4, 0] },
        })),
        label: {
          show: true,
          position: 'right',
          color: t.textPrimary,
          fontSize: 12,
          formatter: (p: { value: number }) => mw(p.value),
        },
      },
    ],
  }
}

export function dailyModelOption(daily: DailyModel[], t: ChartTokens) {
  return {
    ...baseOption(t),
    legend: {
      ...baseOption(t).legend,
      data: [MODEL_LABEL.raw, MODEL_LABEL.debiased, MODEL_LABEL.ratio],
    },
    grid: { ...baseOption(t).grid, right: 24 },
    xAxis: {
      ...categoryAxis(
        t,
        daily.map((d) => ukDay(d.delivery_date)),
      ),
      boundaryGap: false,
      axisLabel: { ...axisLabel(t), interval: 4 },
    },
    yAxis: mwAxis(t, 'Daily MAE'),
    tooltip: {
      ...baseOption(t).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.textMuted, width: 1 } },
      formatter: (params: { dataIndex: number }[]) => {
        const d = daily[params[0]?.dataIndex ?? -1]
        if (!d) return ''
        return tooltipBox(ukDay(d.delivery_date), [
          { color: t.forecast, label: MODEL_LABEL.raw, value: mw(d.raw_mae_mw) },
          { color: t.debiased, label: MODEL_LABEL.debiased, value: mw(d.debiased_mae_mw) },
          { color: t.adjusted, label: MODEL_LABEL.ratio, value: mw(d.ratio_mae_mw), dashed: true },
        ])
      },
    },
    series: [
      { ...line(t.forecast), name: MODEL_LABEL.raw, data: daily.map((d) => d.raw_mae_mw) },
      {
        ...line(t.debiased),
        name: MODEL_LABEL.debiased,
        data: daily.map((d) => d.debiased_mae_mw),
      },
      {
        ...line(t.adjusted, { dashed: true }),
        name: MODEL_LABEL.ratio,
        data: daily.map((d) => d.ratio_mae_mw),
      },
    ],
  }
}
