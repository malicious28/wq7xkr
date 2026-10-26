import { describe, expect, it } from 'vitest'

import type { LiveDay } from '../api/types'
import summary from '../test/fixtures/live_summary.json'
import { dayState, defaultLiveDay } from './live'

const days = summary.data.days as LiveDay[]
const day = (date: string, patch: Partial<LiveDay> = {}): LiveDay => ({
  ...days.find((d) => d.delivery_date === date)!,
  ...patch,
})

describe('defaultLiveDay', () => {
  it('opens on the first day whose gate is still open', () => {
    // Late on 25 Oct the 26th is already locked, so the decision at hand is the 27th.
    expect(defaultLiveDay(days, '2026-10-25')).toBe('2026-10-27')
  })

  it('falls back to tomorrow, then to the newest day', () => {
    const locked = days.map((d) => ({ ...d, gate_passed: true }))
    expect(defaultLiveDay(locked, '2026-10-25')).toBe('2026-10-26')
    expect(defaultLiveDay(locked, '2026-12-01')).toBe('2026-10-27')
    expect(defaultLiveDay([], '2026-10-25')).toBeUndefined()
  })
})

describe('dayState', () => {
  it('marks open days provisional and finished days final', () => {
    expect(dayState(day('2026-10-27')).label).toMatch(/Provisional/)
    expect(dayState(day('2026-10-24'))).toEqual({ tone: 'good', label: 'Final' })
    expect(dayState(day('2026-10-25')).label).toBe('Outturn coming in')
    expect(dayState(day('2026-10-26')).label).toBe('Locked at the gate')
  })
})
