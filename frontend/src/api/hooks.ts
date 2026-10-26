/**
 * One hook per endpoint. Query keys include every parameter, so cached
 * results are exact. `placeholderData: keepPreviousData` holds the previous
 * render while a new slice loads (no skeleton flash, no layout jump).
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { getJson, type QueryParams } from './client'
import type {
  Accuracy,
  AuctionId,
  Decision,
  Horizon,
  LiveDayDetail,
  LiveSummary,
  MatchingRule,
  Meta,
  Models,
  Quality,
  Ramps,
  Revisions,
} from './types'

function useEndpoint<T>(path: string, params: QueryParams, enabled = true) {
  return useQuery({
    queryKey: [path, params],
    queryFn: ({ signal }) => getJson<T>(path, params, signal),
    placeholderData: keepPreviousData,
    // Range queries wait until the scope (from /api/meta) has resolved.
    enabled: enabled && !('first' in params && !params.first),
  })
}

export interface RangeParams {
  first: string
  last: string
  matching: MatchingRule
}

export const useMeta = () =>
  useQuery({
    queryKey: ['/api/meta'],
    queryFn: ({ signal }) => getJson<Meta>('/api/meta', {}, signal),
    staleTime: Infinity,
  })

export interface DecisionParams {
  delivery_date: string
  auction?: AuctionId | undefined
  gate_local?: string | undefined
  margin_min: number
  matching: MatchingRule
}

export const useDecision = (p: DecisionParams, enabled = true) =>
  useEndpoint<Decision>('/api/decision', { ...p }, enabled)

export const useRevisions = (p: DecisionParams) =>
  useEndpoint<Revisions>('/api/revisions', {
    delivery_date: p.delivery_date,
    auction: p.auction,
    gate_local: p.gate_local,
    margin_min: p.margin_min,
    matching: p.matching,
  })

export const useHorizon = (p: RangeParams & { horizon_h: number }) =>
  useEndpoint<Horizon>('/api/horizon', { ...p })

export const useAccuracy = (p: RangeParams & { horizon_h: number }) =>
  useEndpoint<Accuracy>('/api/accuracy', { ...p })

export const useModels = (p: RangeParams & { auction: AuctionId }) =>
  useEndpoint<Models>('/api/models', { ...p })

export const useRamps = (
  p: RangeParams & {
    horizon_h: number
    threshold_mw: number
    window_h: number
    tolerance_h: number
  },
) => useEndpoint<Ramps>('/api/ramps', { ...p })

export const useQuality = (p: { first: string; last: string }) =>
  useEndpoint<Quality>('/api/quality', { ...p })

/**
 * Live mode polls: the server re-fetches Elexon when a new run is due, so
 * checking every five minutes keeps the page within minutes of a new run.
 */
const LIVE_POLL_MS = 5 * 60_000

export const useLiveSummary = (auction: AuctionId) =>
  useQuery({
    queryKey: ['/api/live/summary', auction],
    queryFn: ({ signal }) => getJson<LiveSummary>('/api/live/summary', { auction }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: LIVE_POLL_MS,
  })

export const useLiveDay = (delivery_date: string | undefined, auction: AuctionId) =>
  useQuery({
    queryKey: ['/api/live/day', delivery_date, auction],
    queryFn: ({ signal }) =>
      getJson<LiveDayDetail>('/api/live/day', { delivery_date, auction }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: LIVE_POLL_MS,
    enabled: Boolean(delivery_date),
  })
