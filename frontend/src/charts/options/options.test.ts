/**
 * Chart builders are pure (data + tokens -> option), so their rules are
 * tested without rendering anything.
 */
import { describe, expect, it } from 'vitest'

import decisionFixture from '../../test/fixtures/decision.json'
import { TOKENS } from '../../test/tokens'
import type { Decision, GroupStat, HeatCell } from '../../api/types'
import { groupBiasOption, heatmapOption, modelBarsOption } from './accuracy'
import { tooltipBox } from './base'
import { decisionOption, SERIES } from './series'

const decision = decisionFixture.data as unknown as Decision

type AnyOption = Record<string, unknown> & {
  series: { name?: string; type?: string; label?: { show?: boolean } }[]
}

const group = (key: string, bias: number): GroupStat =>
  ({
    key,
    n: 10,
    bias_mw: bias,
    mae_mw: Math.abs(bias),
    rmse_mw: null,
    wape: null,
    nmae: null,
    err_p10_mw: null,
    err_p50_mw: null,
    err_p90_mw: null,
    abs_err_p90_mw: null,
    mean_actual_mw: null,
    mean_forecast_mw: null,
  }) as GroupStat

describe('decisionOption', () => {
  it('only draws the series the user asked for', () => {
    const all = decisionOption(decision.points, decision.actuals_half_hourly, TOKENS, {
      showActual: true,
      showAdjusted: true,
      showBand: true,
    }) as unknown as AnyOption
    const bare = decisionOption(decision.points, decision.actuals_half_hourly, TOKENS, {
      showActual: false,
      showAdjusted: false,
      showBand: false,
    }) as unknown as AnyOption
    const names = (o: AnyOption) => o.series.map((s) => s.name)
    expect(names(all)).toEqual(
      expect.arrayContaining([SERIES.forecast, SERIES.adjusted, SERIES.actual, SERIES.band]),
    )
    expect(names(bare)).toEqual([SERIES.forecast])
  })

  it('hides outturn when viewing "as at gate"', () => {
    const o = decisionOption(decision.points, decision.actuals_half_hourly, TOKENS, {
      showActual: false,
      showAdjusted: true,
      showBand: true,
    }) as unknown as AnyOption
    expect(o.series.some((s) => s.name === SERIES.actual)).toBe(false)
  })

  it('runs every axis in UTC so pre-shifted UK wall-clock values read correctly', () => {
    const o = decisionOption(decision.points, decision.actuals_half_hourly, TOKENS, {
      showActual: true,
      showAdjusted: true,
      showBand: true,
    })
    expect(o.useUTC).toBe(true)
  })
})

describe('heatmapOption', () => {
  const cells: HeatCell[] = [
    { hour_local: 0, horizon_h: 0, n: 31, mae_mw: 1000, bias_mw: -300 },
    { hour_local: 1, horizon_h: 0, n: 31, mae_mw: 2000, bias_mw: 900 },
  ]

  it('maps colour to the metric, not the sample count (regression)', () => {
    const o = heatmapOption(cells, [0], 'mae', TOKENS) as unknown as {
      visualMap: { dimension: number }
    }
    expect(o.visualMap.dimension).toBe(2)
  })

  it('uses a symmetric diverging range for bias, so zero sits on the neutral midpoint', () => {
    const o = heatmapOption(cells, [0], 'bias', TOKENS) as unknown as {
      visualMap: { min: number; max: number; inRange: { color: string[] } }
    }
    expect(o.visualMap.min).toBe(-900)
    expect(o.visualMap.max).toBe(900)
    expect(o.visualMap.inRange.color).toEqual([TOKENS.divNeg, TOKENS.divMid, TOKENS.divPos])
  })
})

describe('groupBiasOption', () => {
  it('labels a few bars directly but never every one of many', () => {
    const few = groupBiasOption(
      [group('a', 100), group('b', -50)],
      TOKENS,
      'x',
    ) as unknown as AnyOption
    const many = groupBiasOption(
      Array.from({ length: 24 }, (_, i) => group(String(i), i * 10)),
      TOKENS,
      'x',
    ) as unknown as AnyOption
    expect(few.series[0]?.label?.show).toBe(true)
    expect(many.series[0]?.label?.show).toBe(false)
  })
})

describe('modelBarsOption', () => {
  it('colours each model by its fixed entity colour regardless of rank', () => {
    const o = modelBarsOption(
      [
        {
          model: 'raw',
          n: 1,
          bias_mw: 0,
          mae_mw: 2000,
          rmse_mw: 0,
          skill_vs_raw: 0,
          skill_vs_persistence: 0,
        },
        {
          model: 'ratio',
          n: 1,
          bias_mw: 0,
          mae_mw: 1000,
          rmse_mw: 0,
          skill_vs_raw: 0.5,
          skill_vs_persistence: 0,
        },
      ],
      TOKENS,
    ) as unknown as { series: { data: { itemStyle: { color: string } }[] }[] }
    const colours = o.series[0]!.data.map((d) => d.itemStyle.color)
    expect(colours).toEqual([TOKENS.forecast, TOKENS.adjusted]) // sorted worst-first, colour follows entity
  })
})

describe('tooltipBox', () => {
  it('inserts labels as text, never as HTML', () => {
    const el = tooltipBox('<img src=x onerror=alert(1)>', [
      { color: '#000', label: '<b>evil</b>', value: '1 MW' },
    ])
    expect(el.querySelector('img')).toBeNull()
    expect(el.querySelector('b')).toBeNull()
    expect(el.textContent).toContain('<b>evil</b>')
  })
})
