import { createContext, useContext } from 'react'

export type Theme = 'dark' | 'light'

export interface ChartTokens {
  surface: string
  textPrimary: string
  textSecondary: string
  textMuted: string
  grid: string
  axis: string
  forecast: string
  actual: string
  adjusted: string
  persistence: string
  debiased: string
  band: string
  divNeg: string
  divMid: string
  divPos: string
  seq: [string, string, string, string, string]
  good: string
  warning: string
  serious: string
  critical: string
  fontSans: string
  fontMono: string
}

export interface ThemeCtx {
  theme: Theme
  toggle: () => void
  /** CSS custom properties resolved for the current theme (charts need concrete colours). */
  tokens: ChartTokens
}

export const ThemeContext = createContext<ThemeCtx | null>(null)

export function useTheme(): ThemeCtx {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}

export function readTokens(): ChartTokens {
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim()
  return {
    surface: v('--surface-1'),
    textPrimary: v('--text-primary'),
    textSecondary: v('--text-secondary'),
    textMuted: v('--text-muted'),
    grid: v('--grid'),
    axis: v('--axis'),
    forecast: v('--series-forecast'),
    actual: v('--series-actual'),
    adjusted: v('--series-adjusted'),
    persistence: v('--series-persistence'),
    debiased: v('--series-debiased'),
    band: v('--band-fill'),
    divNeg: v('--div-neg'),
    divMid: v('--div-mid'),
    divPos: v('--div-pos'),
    seq: [v('--seq-0'), v('--seq-1'), v('--seq-2'), v('--seq-3'), v('--seq-4')],
    good: v('--status-good'),
    warning: v('--status-warning'),
    serious: v('--status-serious'),
    critical: v('--status-critical'),
    fontSans: v('--font-sans'),
    fontMono: v('--font-mono'),
  }
}
