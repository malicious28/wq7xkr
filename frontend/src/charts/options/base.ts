/**
 * Shared chart chrome. Every builder starts from these so all charts read as
 * one system: recessive grid and axes, ink-coloured text (never series
 * colour), 2px lines, a crosshair tooltip, and UK wall-clock time axes.
 */
import type { ChartTokens } from '../../theme/context'
import { compactMw } from '../../lib/format'

export interface TooltipRow {
  color: string
  label: string
  value: string
  dashed?: boolean
}

/**
 * Tooltip content built as DOM with textContent (never innerHTML), value first
 * and strong, series name secondary, keyed with a short line in series colour.
 */
export function tooltipBox(title: string, rows: TooltipRow[], footnote?: string): HTMLElement {
  const box = document.createElement('div')
  box.className = 'wd-tooltip'
  const head = document.createElement('div')
  head.className = 'wd-tooltip__title'
  head.textContent = title
  box.append(head)
  for (const row of rows) {
    const line = document.createElement('div')
    line.className = 'wd-tooltip__row'
    const key = document.createElement('span')
    key.className = row.dashed ? 'wd-tooltip__key wd-tooltip__key--dashed' : 'wd-tooltip__key'
    key.style.borderColor = row.color
    const value = document.createElement('strong')
    value.textContent = row.value
    const label = document.createElement('span')
    label.className = 'wd-tooltip__label'
    label.textContent = row.label
    line.append(key, value, label)
    box.append(line)
  }
  if (footnote) {
    const foot = document.createElement('div')
    foot.className = 'wd-tooltip__foot'
    foot.textContent = footnote
    box.append(foot)
  }
  return box
}

export function baseOption(t: ChartTokens) {
  return {
    useUTC: true, // timestamps are pre-shifted to UK wall clock (see ukWallClockMs)
    animationDuration: 600,
    animationEasing: 'cubicOut' as const,
    // Our container carries the accessible name and a table view backs every chart;
    // ECharts' generated description (a dump of raw values) would overwrite it.
    aria: { enabled: false },
    textStyle: { fontFamily: t.fontSans, color: t.textSecondary, fontSize: 12 },
    grid: { left: 8, right: 16, top: 52, bottom: 8 }, // room for legend + unit
    tooltip: {
      backgroundColor: 'transparent',
      borderWidth: 0,
      padding: 0,
      extraCssText: 'box-shadow:none;',
      className: 'wd-tooltip-host',
      confine: true,
    },
    legend: {
      top: 0,
      left: 0,
      icon: 'roundRect',
      itemWidth: 14,
      itemHeight: 3,
      itemGap: 18,
      textStyle: { color: t.textSecondary, fontSize: 12, fontFamily: t.fontSans },
      inactiveColor: t.textMuted,
    },
  }
}

export function axisLabel(t: ChartTokens) {
  return { color: t.textMuted, fontSize: 11, fontFamily: t.fontSans }
}

export function mwAxis(t: ChartTokens, name = 'MW') {
  return {
    type: 'value' as const,
    name,
    nameTextStyle: {
      color: t.textMuted,
      fontSize: 11,
      align: 'left' as const,
      padding: [0, 0, 0, -28],
    },
    axisLabel: { ...axisLabel(t), formatter: (v: number) => compactMw(v) },
    splitLine: { lineStyle: { color: t.grid, width: 1 } },
    axisLine: { show: false },
    axisTick: { show: false },
  }
}

export function timeAxis(t: ChartTokens) {
  return {
    type: 'time' as const,
    axisLabel: { ...axisLabel(t), hideOverlap: true },
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    splitLine: { show: false },
  }
}

export function categoryAxis(t: ChartTokens, data: (string | number)[], name?: string) {
  return {
    type: 'category' as const,
    data,
    name,
    nameLocation: 'middle' as const,
    nameGap: 28,
    nameTextStyle: { color: t.textMuted, fontSize: 11 },
    axisLabel: axisLabel(t),
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
  }
}

export function line(
  color: string,
  opts: { dashed?: boolean; width?: number; step?: boolean } = {},
) {
  return {
    type: 'line' as const,
    showSymbol: false,
    symbol: 'circle',
    symbolSize: 8,
    step: opts.step ? ('end' as const) : undefined,
    lineStyle: {
      color,
      width: opts.width ?? 2,
      type: opts.dashed ? ('dashed' as const) : ('solid' as const),
    },
    itemStyle: { color, borderColor: 'transparent', borderWidth: 2 },
    emphasis: { focus: 'none' as const, lineStyle: { width: (opts.width ?? 2) + 0.5 } },
  }
}

/** Colour a value by sign on the diverging scale (positive = forecast too high). */
export function signColor(t: ChartTokens, v: number | null | undefined): string {
  if (v == null || v === 0) return t.divMid
  return v > 0 ? t.divPos : t.divNeg
}
