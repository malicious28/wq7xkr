import { addDays, ukDay } from '../lib/format'
import { Icon } from './ui/Icon'
import s from './DayStepper.module.css'

interface DayStepperProps {
  label: string
  value: string
  min: string
  max: string
  onChange: (isoDate: string) => void
}

/** Delivery-day picker: step buttons for the common case, native date input for jumps. */
export function DayStepper({ label, value, min, max, onChange }: DayStepperProps) {
  const clamp = (d: string) => (d < min ? min : d > max ? max : d)
  return (
    <div className={s.root}>
      <label className={s.label} htmlFor="delivery-day">
        {label}
      </label>
      <div className={s.control}>
        <button
          type="button"
          className={s.step}
          onClick={() => onChange(clamp(addDays(value, -1)))}
          disabled={value <= min}
          aria-label="Previous day"
        >
          <Icon name="chevronLeft" size={16} />
        </button>
        <div className={s.display}>
          <span className={s.day} aria-hidden>
            {ukDay(value)}
          </span>
          <input
            id="delivery-day"
            className={s.input}
            type="date"
            value={value}
            min={min}
            max={max}
            onChange={(e) => e.target.value && onChange(clamp(e.target.value))}
          />
        </div>
        <button
          type="button"
          className={s.step}
          onClick={() => onChange(clamp(addDays(value, 1)))}
          disabled={value >= max}
          aria-label="Next day"
        >
          <Icon name="chevronRight" size={16} />
        </button>
      </div>
    </div>
  )
}
