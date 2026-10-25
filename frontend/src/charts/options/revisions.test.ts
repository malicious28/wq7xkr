import { describe, expect, it } from 'vitest'

import revisionsFixture from '../../test/fixtures/revisions.json'
import type { Revisions } from '../../api/types'
import { TOKENS } from '../../test/tokens'
import { ACTUAL, USED_RUN, revisionSummary, revisionsOption, runOpacity } from './revisions'

const rev = revisionsFixture.data as unknown as Revisions

type Series = {
  name: string
  z: number
  lineStyle: { type: string; color: string; opacity: number }
}

describe('revisionsOption', () => {
  const option = revisionsOption(
    rev.runs,
    rev.actual,
    rev.used_publish_time,
    TOKENS,
    true,
  ) as unknown as {
    series: Series[]
  }

  it('draws every run plus the outturn, with the used run on top in the forecast colour', () => {
    expect(option.series).toHaveLength(rev.runs.length + 1)
    const used = option.series.filter((s) => s.name === USED_RUN)
    expect(used).toHaveLength(1)
    expect(used[0]!.lineStyle.color).toBe(TOKENS.forecast)
    expect(used[0]!.z).toBeGreaterThan(
      Math.max(
        ...option.series.filter((s) => s.name !== USED_RUN && s.name !== ACTUAL).map((s) => s.z),
      ),
    )
  })

  it('dashes runs published after the gate, so they read as unusable', () => {
    const after = rev.runs.filter((r) => !r.available).length
    expect(option.series.filter((s) => s.lineStyle.type === 'dashed')).toHaveLength(after)
  })

  it('hides the outturn when viewing as at the gate', () => {
    const asAtGate = revisionsOption(
      rev.runs,
      rev.actual,
      rev.used_publish_time,
      TOKENS,
      false,
    ) as unknown as {
      series: Series[]
    }
    expect(asAtGate.series.some((s) => s.name === ACTUAL)).toBe(false)
  })
})

describe('run ordering helpers', () => {
  it('fades older runs but keeps every run visible', () => {
    expect(runOpacity(0, 10)).toBeCloseTo(0.18)
    expect(runOpacity(9, 10)).toBeCloseTo(0.8)
    expect(runOpacity(0, 1)).toBe(1)
  })

  it('compares runs only over the hours both cover (regression)', () => {
    const runs = [
      {
        publish_time: 'a',
        available: true,
        points: [
          { start_time: 'h1', forecast_mw: 100 },
          { start_time: 'h2', forecast_mw: 100 },
        ],
      },
      { publish_time: 'b', available: true, points: [{ start_time: 'h2', forecast_mw: 160 }] },
    ]
    const s = revisionSummary(runs, 'b')
    expect(s.firstToUsedMw).toBe(60) // not (160 - 100) over unequal hour sets
    expect(s.commonHours).toBe(1)
  })

  it('summarises the run count and span', () => {
    const s = revisionSummary(rev.runs, rev.used_publish_time)
    expect(s.runs).toBe(24)
    expect(s.leadSpanH).toBeCloseTo(68)
    // compared over shared hours only: never more hours than the day has
    expect(s.commonHours).toBeGreaterThan(0)
    expect(s.commonHours).toBeLessThanOrEqual(24)
  })
})
