/**
 * Friendly aliases over the generated OpenAPI types. Never hand-write an API
 * shape: regenerate with `npm run gen:api` after changing the backend schemas.
 */
import type { components } from './schema'

type S = components['schemas']

export type Summary = S['Summary']
export type GroupStat = S['GroupStat']
export type Meta = S['MetaOut']
export type Auction = S['AuctionOut']
export type AuctionId = S['AuctionId']
export type ScopePreset = S['ScopePreset']
export type MatchingRule = S['MatchingRule']
export type Decision = S['DecisionOut']
export type DecisionPoint = S['DecisionPoint']
export type RunInfo = S['RunInfo']
export type Revisions = S['RevisionsOut']
export type Horizon = S['HorizonOut']
export type HorizonPoint = S['HorizonPoint']
export type Accuracy = S['AccuracyOut']
export type CurvePoint = S['CurvePoint']
export type HeatCell = S['HeatCell']
export type Models = S['ModelsOut']
export type ModelScore = S['ModelScore']
export type Ramps = S['RampsOut']
export type RampEvent = S['RampEvent']
export type Quality = S['QualityOut']

export interface ResponseMeta {
  data_version: string
  generated_at: string
  params: Record<string, string | number | boolean | null>
}

export interface Envelope<T> {
  data: T
  meta: ResponseMeta
}
