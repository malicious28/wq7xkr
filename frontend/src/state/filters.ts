/**
 * Filter state lives in the URL, so every view is a shareable, reproducible
 * link ("look at 15 Jan at the EPEX half-hourly gate"). Components read and
 * write through these hooks only; defaults come from the API's meta.
 */
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { useMeta } from '../api/hooks'
import type { MatchingRule, ScopePreset } from '../api/types'

type Updates = Record<string, string | number | null | undefined>

export function useParam(): [URLSearchParams, (updates: Updates) => void] {
  const [params, setParams] = useSearchParams()
  const update = useCallback(
    (updates: Updates) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(updates)) {
            if (v === null || v === undefined || v === '') next.delete(k)
            else next.set(k, String(v))
          }
          return next
        },
        { replace: true, preventScrollReset: true },
      )
    },
    [setParams],
  )
  return [params, update]
}

export interface Scope {
  preset: ScopePreset | undefined
  presets: ScopePreset[]
  first: string
  last: string
  matching: MatchingRule
  setScope: (id: string) => void
  setMatching: (rule: MatchingRule) => void
}

const MATCHING: readonly MatchingRule[] = ['hour_mean', 'on_the_hour']

export function useScope(): Scope {
  const meta = useMeta().data?.data
  const [params, update] = useParam()
  const presets = useMemo(() => meta?.scopes ?? [], [meta])
  const requested = params.get('scope') ?? meta?.default_scope
  const preset = presets.find((p) => p.id === requested) ?? presets[0]
  const rawMatching = params.get('matching')
  const matching: MatchingRule = MATCHING.includes(rawMatching as MatchingRule)
    ? (rawMatching as MatchingRule)
    : 'hour_mean'

  return {
    preset,
    presets,
    first: preset?.delivery_first ?? '',
    last: preset?.delivery_last ?? '',
    matching,
    setScope: (id) => update({ scope: id === meta?.default_scope ? null : id }),
    setMatching: (rule) => update({ matching: rule === 'hour_mean' ? null : rule }),
  }
}

export function useNumberParam(
  key: string,
  fallback: number,
  min: number,
  max: number,
): [number, (v: number) => void] {
  const [params, update] = useParam()
  const raw = Number(params.get(key))
  const value =
    params.has(key) && Number.isFinite(raw) ? Math.min(max, Math.max(min, raw)) : fallback
  return [value, (v: number) => update({ [key]: v === fallback ? null : v })]
}
