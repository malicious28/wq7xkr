/**
 * Formatting. All times render in Europe/London explicitly - never the
 * browser's zone - because the desk works in UK market time wherever the
 * viewer happens to be.
 */

export const UK_TZ = 'Europe/London'

const nf0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const DASH = '—'
const MINUS = '−'

export function mw(value: number | null | undefined): string {
  return value == null ? DASH : `${nf0.format(value)} MW`
}

export function gw(value: number | null | undefined, digits: 1 | 2 = 1): string {
  if (value == null) return DASH
  return `${(digits === 1 ? nf1 : nf2).format(value / 1000)} GW`
}

/** Signed MW with a true minus sign, e.g. "+1,738 MW" / "−240 MW". */
export function signedMw(value: number | null | undefined): string {
  if (value == null) return DASH
  const sign = value > 0 ? '+' : value < 0 ? MINUS : ''
  return `${sign}${nf0.format(Math.abs(value))} MW`
}

export function gwh(mwh: number | null | undefined): string {
  return mwh == null ? DASH : `${nf1.format(mwh / 1000)} GWh`
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value == null) return DASH
  return `${(value * 100).toFixed(digits)}%`
}

export function signedPct(value: number | null | undefined, digits = 0): string {
  if (value == null) return DASH
  const v = value * 100
  const sign = v > 0 ? '+' : v < 0 ? MINUS : ''
  return `${sign}${Math.abs(v).toFixed(digits)}%`
}

/** Compact axis ticks: 0 / 5K / 10K, or GW when the axis is in GW. */
export function compactMw(value: number): string {
  if (Math.abs(value) >= 1000) return `${value / 1000}K`
  return String(value)
}

export function hours(value: number | null | undefined): string {
  if (value == null) return DASH
  return `${nf1.format(value)} h`
}

export function minutes(value: number | null | undefined): string {
  if (value == null) return DASH
  if (Math.abs(value) >= 120) return `${nf1.format(value / 60)} h`
  return `${nf0.format(value)} min`
}

const timeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})
const dayFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})
const dateTimeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

export const ukTime = (iso: string) => timeFmt.format(new Date(iso))
export const ukDateTime = (iso: string) => dateTimeFmt.format(new Date(iso))

/**
 * "GMT" or "BST" for the given instant, derived from the actual UK offset
 * (short zone names from Intl vary by browser: "GMT", "GMT+0", "UTC").
 */
export function ukZone(iso: string): string {
  return ukWallClockMs(iso) - Date.parse(iso) === 0 ? 'GMT' : 'BST'
}

/** A local calendar date "2026-01-15" rendered as "Thu 15 Jan". */
export function ukDay(isoDate: string): string {
  // Noon UTC on the date stays on the same calendar day in Europe/London all year.
  return dayFmt.format(new Date(`${isoDate}T12:00:00Z`))
}

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

const offsetFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

/**
 * Epoch ms of the UK *wall-clock* reading of an instant, expressed as if it
 * were UTC. Charts run with `useUTC: true`, so feeding them these values
 * makes every axis read in UK time regardless of the browser's zone.
 */
export function ukWallClockMs(iso: string): number {
  const parts = Object.fromEntries(
    offsetFmt.formatToParts(new Date(iso)).map((p) => [p.type, p.value]),
  )
  return Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  )
}
