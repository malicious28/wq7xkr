import { describe, expect, it } from 'vitest'

import {
  addDays,
  gw,
  gwh,
  minutes,
  pct,
  signedMw,
  signedPct,
  ukDay,
  ukTime,
  ukWallClockMs,
  ukZone,
} from './format'

describe('UK time handling', () => {
  it('maps winter instants to the same wall clock (GMT)', () => {
    expect(ukWallClockMs('2026-01-15T09:30:00Z')).toBe(Date.parse('2026-01-15T09:30:00Z'))
    expect(ukZone('2026-01-15T09:30:00Z')).toBe('GMT')
  })

  it('shifts summer instants by one hour (BST), independent of the browser zone', () => {
    expect(ukWallClockMs('2026-07-01T08:50:00Z')).toBe(Date.parse('2026-07-01T09:50:00Z'))
    expect(ukZone('2026-07-01T08:50:00Z')).toBe('BST')
    expect(ukTime('2026-07-01T08:50:00Z')).toBe('09:50')
  })

  it('handles the spring clock change (01:00 UTC is already 02:00 BST)', () => {
    expect(ukTime('2026-03-29T00:30:00Z')).toBe('00:30')
    expect(ukTime('2026-03-29T01:00:00Z')).toBe('02:00')
  })

  it('formats calendar days without drifting across midnight', () => {
    expect(ukDay('2026-01-15')).toBe('Thu 15 Jan')
    expect(addDays('2026-01-31', 1)).toBe('2026-02-01')
    expect(addDays('2026-03-29', -1)).toBe('2026-03-28')
  })
})

describe('number formatting', () => {
  it('uses a true minus sign and explicit plus for signed values', () => {
    expect(signedMw(1738.4)).toBe('+1,738 MW')
    expect(signedMw(-240)).toBe('−240 MW')
    expect(signedMw(0)).toBe('0 MW')
    expect(signedPct(0.3746)).toBe('+37%')
  })

  it('renders missing values as an em dash, never "NaN" or "null"', () => {
    for (const f of [signedMw, gw, gwh, pct, minutes]) expect(f(null)).toBe('—')
  })

  it('scales units', () => {
    expect(gw(1947.65, 2)).toBe('1.95 GW')
    expect(gwh(280272)).toBe('280.3 GWh')
    expect(minutes(20)).toBe('20 min')
    expect(minutes(145)).toBe('2.4 h')
  })
})
