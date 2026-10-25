import type Lenis from 'lenis'
import { createContext, useContext } from 'react'

import type { GlassOptions } from './glass'

export interface MotionCtx {
  /** The Lenis instance, once mounted. Read it in effects and handlers, not during render. */
  getLenis: () => Lenis | null
  reducedMotion: boolean
  registerGlass: (el: HTMLElement, options?: GlassOptions) => () => void
}

export const MotionContext = createContext<MotionCtx | null>(null)

export function useMotion(): MotionCtx {
  const ctx = useContext(MotionContext)
  if (!ctx) throw new Error('useMotion must be used inside <MotionProvider>')
  return ctx
}
