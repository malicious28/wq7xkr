import type { ChartTokens } from '../theme/context'

/** Fixed tokens for tests (jsdom does not compute CSS custom properties). */
export const TOKENS: ChartTokens = {
  surface: '#101827',
  textPrimary: '#eef2f7',
  textSecondary: '#b4bfcc',
  textMuted: '#7d8899',
  grid: '#1c2638',
  axis: '#2c3a50',
  forecast: '#3987e5',
  actual: '#d95926',
  adjusted: '#199e70',
  persistence: '#9085e9',
  debiased: '#c98500',
  band: 'rgba(57,135,229,0.2)',
  divNeg: '#3987e5',
  divMid: '#2a3446',
  divPos: '#e66767',
  seq: ['#13233d', '#184f95', '#2a78d6', '#6da7ec', '#cde2fb'],
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
  fontSans: 'system-ui',
  fontMono: 'monospace',
}
