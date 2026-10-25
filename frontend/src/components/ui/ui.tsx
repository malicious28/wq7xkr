import { useId } from 'react'
import type { ReactNode } from 'react'

import { Icon, type IconName } from './Icon'
import s from './ui.module.css'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

/* ---------------------------------------------------------------- Card */

interface CardProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
  className?: string
  id?: string
}

export function Card({ title, subtitle, actions, children, footer, className, id }: CardProps) {
  const headingId = useId()
  return (
    <section
      className={cx(s.card, className)}
      aria-labelledby={title ? headingId : undefined}
      id={id}
    >
      {(title || actions) && (
        <header className={s.cardHead}>
          <div>
            {title && (
              <h2 id={headingId} className={s.cardTitle}>
                {title}
              </h2>
            )}
            {subtitle && <p className={s.cardSubtitle}>{subtitle}</p>}
          </div>
          {actions && <div className={s.cardActions}>{actions}</div>}
        </header>
      )}
      <div className={s.cardBody}>{children}</div>
      {footer && <footer className={s.cardFoot}>{footer}</footer>}
    </section>
  )
}

/* ---------------------------------------------------------------- StatTile */

interface StatProps {
  label: string
  value: ReactNode
  detail?: ReactNode
  accent?: string
  size?: 'm' | 'l'
}

/** Label (sentence case), proportional-figure value, optional context line. */
export function StatTile({ label, value, detail, accent, size = 'm' }: StatProps) {
  return (
    <div className={cx(s.stat, size === 'l' && s.statLarge)}>
      <span className={s.statLabel}>
        {accent && <span className={s.statKey} style={{ background: accent }} aria-hidden />}
        {label}
      </span>
      <span className={s.statValue}>{value}</span>
      {detail && <span className={s.statDetail}>{detail}</span>}
    </div>
  )
}

/* ---------------------------------------------------------------- Segmented */

interface SegmentedProps<T extends string | number> {
  label: string
  options: { value: T; label: ReactNode; title?: string }[]
  value: T
  onChange: (value: T) => void
  hideLabel?: boolean
}

export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  hideLabel,
}: SegmentedProps<T>) {
  const id = useId()
  return (
    <div className={s.field}>
      <span id={id} className={cx(s.fieldLabel, hideLabel && 'visually-hidden')}>
        {label}
      </span>
      <div role="radiogroup" aria-labelledby={id} className={s.segmented}>
        {options.map((o) => (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={o.value === value}
            title={o.title}
            className={cx(s.segment, o.value === value && s.segmentOn)}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- Field */

export function Field({
  label,
  children,
  hint,
}: {
  label: string
  children: (id: string) => ReactNode
  hint?: string
}) {
  const id = useId()
  return (
    <div className={s.field}>
      <label htmlFor={id} className={s.fieldLabel}>
        {label}
      </label>
      {children(id)}
      {hint && <span className={s.fieldHint}>{hint}</span>}
    </div>
  )
}

export function Select<T extends string>({
  id,
  value,
  options,
  onChange,
}: {
  id?: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <select
      id={id}
      className={s.input}
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

/* ---------------------------------------------------------------- Range slider */

interface SliderProps {
  id?: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  format?: (value: number) => string
  marks?: number[]
}

export function Slider({
  id,
  value,
  min,
  max,
  step = 1,
  onChange,
  format = String,
  marks,
}: SliderProps) {
  const pctPos = ((value - min) / (max - min)) * 100
  return (
    <div className={s.slider}>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={format(value)}
        style={{ ['--pos' as string]: `${pctPos}%` }}
      />
      <output className={s.sliderValue} htmlFor={id}>
        {format(value)}
      </output>
      {marks && (
        <div className={s.sliderMarks} aria-hidden>
          {marks.map((m) => (
            <span key={m} style={{ left: `${((m - min) / (max - min)) * 100}%` }}>
              {format(m)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- Callout */

export type Tone = 'info' | 'good' | 'warning' | 'critical'

const TONE_ICON: Record<Tone, IconName> = {
  info: 'info',
  good: 'check',
  warning: 'alert',
  critical: 'alert',
}
const TONE_LABEL: Record<Tone, string> = {
  info: 'Note',
  good: 'OK',
  warning: 'Warning',
  critical: 'Problem',
}

/** Status colour never travels alone: always an icon and a text label. */
export function Callout({
  tone = 'info',
  title,
  children,
}: {
  tone?: Tone
  title?: ReactNode
  children?: ReactNode
}) {
  return (
    <div
      className={cx(s.callout, s[`tone_${tone}`])}
      role={tone === 'critical' ? 'alert' : 'status'}
    >
      <span className={s.calloutIcon}>
        <Icon name={TONE_ICON[tone]} size={16} />
      </span>
      <div>
        <strong className={s.calloutTitle}>{title ?? TONE_LABEL[tone]}</strong>
        {children && <div className={s.calloutBody}>{children}</div>}
      </div>
    </div>
  )
}

export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={cx(s.pill, s[`tone_${tone}`])}>
      <Icon name={TONE_ICON[tone]} size={13} />
      {children}
    </span>
  )
}

/* ---------------------------------------------------------------- Layout bits */

export function PageHeader({
  eyebrow,
  title,
  lede,
  children,
}: {
  eyebrow?: string
  title: ReactNode
  lede?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className={s.pageHeader}>
      {eyebrow && <p className={s.eyebrow}>{eyebrow}</p>}
      <h1 className={s.pageTitle}>{title}</h1>
      {lede && <p className={s.lede}>{lede}</p>}
      {children}
    </header>
  )
}

/** The single row of filters above the content they scope. */
export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className={s.filterBar} role="group" aria-label="Filters">
      {children}
    </div>
  )
}

export function Grid({
  children,
  cols = 2,
  className,
}: {
  children: ReactNode
  cols?: 2 | 3 | 4
  className?: string
}) {
  return <div className={cx(s.grid, s[`grid${cols}`], className)}>{children}</div>
}

export function Button({
  children,
  onClick,
  href,
  variant = 'ghost',
  icon,
  download,
}: {
  children: ReactNode
  onClick?: () => void
  href?: string
  variant?: 'ghost' | 'solid'
  icon?: IconName
  download?: boolean
}) {
  const content = (
    <>
      {icon && <Icon name={icon} size={16} />}
      <span>{children}</span>
    </>
  )
  const cls = cx(s.button, variant === 'solid' && s.buttonSolid)
  if (href)
    return (
      <a className={cls} href={href} download={download || undefined}>
        {content}
      </a>
    )
  return (
    <button type="button" className={cls} onClick={onClick}>
      {content}
    </button>
  )
}

/* ---------------------------------------------------------------- Async states */

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className={s.loading} role="status" aria-live="polite">
      <span className={s.spinner} aria-hidden />
      {label}…
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong'
  return (
    <Callout tone="critical" title="Could not load this view">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className={s.linkButton} onClick={onRetry}>
          Try again
        </button>
      )}
    </Callout>
  )
}
