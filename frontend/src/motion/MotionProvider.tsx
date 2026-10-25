/**
 * Smooth scrolling (Lenis) and liquid glass (liquidGL) on one frame loop.
 *
 * liquidGL's `syncWith({ lenis })` drives `lenis.raf()` from inside its own
 * render loop, so glass refraction and scroll position update in the same
 * frame (no lag between the content and the glass above it). Until a glass
 * surface exists, or if WebGL is unavailable, Lenis runs its own loop.
 *
 * Both libraries step aside for `prefers-reduced-motion`: Lenis disables
 * smoothing itself, and glass drops its animated highlights.
 *
 * Lenis is an external, imperative instance, so it lives in a ref (not React
 * state) and is exposed through a stable getter.
 */
import Lenis from 'lenis'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'

import { MotionContext } from './context'
import { createGlass, type GlassHandle, type GlassOptions } from './glass'

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function glassDisabled(): boolean {
  return new URLSearchParams(window.location.search).get('glass') === 'off'
}

export function MotionProvider({ children }: { children: ReactNode }) {
  const lenisRef = useRef<Lenis | null>(null)
  const ownLoop = useRef<number | null>(null)
  const reducedMotion = useMemo(() => prefersReducedMotion(), [])

  useEffect(() => {
    const instance = new Lenis({ autoRaf: false, lerp: 0.12 })
    const loop = (time: number) => {
      instance.raf(time)
      ownLoop.current = requestAnimationFrame(loop)
    }
    ownLoop.current = requestAnimationFrame(loop)
    lenisRef.current = instance
    return () => {
      if (ownLoop.current !== null) cancelAnimationFrame(ownLoop.current)
      instance.destroy()
      lenisRef.current = null
    }
  }, [])

  // liquidGL sizes its full-viewport canvas from the visible width, but only
  // re-measures on window `resize`. A scrollbar appearing after data loads
  // narrows the visible width without a resize, leaving the canvas one
  // scrollbar too wide (a horizontal overflow). Re-announce width changes.
  useEffect(() => {
    let width = document.documentElement.clientWidth
    const ro = new ResizeObserver(() => {
      const next = document.documentElement.clientWidth
      if (next !== width) {
        width = next
        window.dispatchEvent(new Event('resize'))
      }
    })
    ro.observe(document.documentElement)
    return () => ro.disconnect()
  }, [])

  const getLenis = useCallback(() => lenisRef.current, [])

  const registerGlass = useCallback(
    (el: HTMLElement, options?: GlassOptions) => {
      if (glassDisabled()) {
        el.classList.add('glass-fallback')
        return () => el.classList.remove('glass-fallback')
      }
      let handle: GlassHandle | null = null
      let cancelled = false
      void createGlass(el, { reducedMotion, ...options }).then((h) => {
        if (cancelled) {
          h?.destroy()
          return
        }
        handle = h
        // Hand the frame loop to liquidGL on every new lens. When its last lens is
        // destroyed (e.g. a theme toggle re-creates them all) liquidGL stops driving
        // Lenis, so a one-time hand-off would leave scrolling frozen.
        const lenis = lenisRef.current
        if (h?.sync && lenis) {
          if (ownLoop.current !== null) cancelAnimationFrame(ownLoop.current)
          ownLoop.current = null
          h.sync(lenis) // syncWith() stops the previous sync itself
        }
      })
      return () => {
        cancelled = true
        handle?.destroy()
      }
    },
    [reducedMotion],
  )

  const value = useMemo(
    () => ({ getLenis, reducedMotion, registerGlass }),
    [getLenis, reducedMotion, registerGlass],
  )
  return <MotionContext.Provider value={value}>{children}</MotionContext.Provider>
}
