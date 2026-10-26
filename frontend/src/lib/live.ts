/** Pure helpers for the live ('Try now') page. */
import type { LiveDay } from '../api/types'
import type { Tone } from '../components/ui/ui'
import { addDays } from './format'

/**
 * The day a buyer is deciding on now: the first day whose gate is still open
 * (late in the evening that is the day after tomorrow); otherwise tomorrow,
 * otherwise the newest day.
 */
export function defaultLiveDay(days: LiveDay[], today: string): string | undefined {
  const tomorrow = addDays(today, 1)
  return (
    days.find((d) => !d.gate_passed)?.delivery_date ??
    days.find((d) => d.delivery_date === tomorrow)?.delivery_date ??
    days.at(-1)?.delivery_date
  )
}

export function dayState(d: LiveDay): { tone: Tone; label: string } {
  if (!d.gate_passed) return { tone: 'warning', label: 'Provisional · updates each run' }
  if (d.status === 'final') return { tone: 'good', label: 'Final' }
  if (d.status === 'in_progress') return { tone: 'info', label: 'Outturn coming in' }
  return { tone: 'info', label: 'Locked at the gate' }
}
