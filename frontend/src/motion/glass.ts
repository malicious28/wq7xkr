/**
 * Adapter over liquidGL (https://github.com/naughtyduk/liquidGL).
 *
 * liquidGL is a selector-based, imperative library with no React bindings.
 * This adapter gives React a handle-based API: create a lens for one element,
 * destroy it on unmount. The library is imported lazily (its own chunk), so
 * the WebGL code never blocks first paint.
 */
import type Lenis from 'lenis'

export interface GlassOptions {
  refraction?: number
  bevelDepth?: number
  bevelWidth?: number
  frost?: number
  tint?: string | null
  specular?: boolean
  tilt?: boolean
  reducedMotion?: boolean
}

export interface GlassHandle {
  destroy: () => void
  /** Present on the first lens: hands the shared frame loop to liquidGL. */
  sync?: (lenis: Lenis) => void
}

let counter = 0

async function settled(): Promise<void> {
  // Snapshot after fonts and layout settle, or the glass refracts a stale page.
  await document.fonts?.ready
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
}

export async function createGlass(
  el: HTMLElement,
  options: GlassOptions = {},
): Promise<GlassHandle | null> {
  const id = `g${++counter}`
  el.dataset.glassId = id
  try {
    const [{ default: liquidGL }] = await Promise.all([import('liquid-gl'), settled()])
    // Re-registered meanwhile (StrictMode remount, theme change): this attempt is stale.
    if (!liquidGL || !el.isConnected || el.dataset.glassId !== id) return null
    const { reducedMotion = false, ...rest } = options
    const result = liquidGL({
      target: `[data-glass-id="${id}"]`,
      snapshot: 'body',
      resolution: 1.5,
      refraction: 0.012,
      bevelDepth: 0.07,
      bevelWidth: 0.16,
      frost: 2,
      shadow: true,
      specular: !reducedMotion,
      tilt: false,
      reveal: reducedMotion ? 'none' : 'fade',
      ...rest,
    })
    const lens = Array.isArray(result) ? result[0] : result
    if (!lens) return null
    return {
      destroy: () => {
        try {
          lens.destroy()
        } finally {
          delete el.dataset.glassId
        }
      },
      sync: (lenis) => liquidGL.syncWith({ lenis, gsap: false, locomotiveScroll: false }),
    }
  } catch (err) {
    // WebGL failure must never break the app: fall back to CSS frost.
    console.warn('liquidGL unavailable, using CSS fallback', err)
    el.classList.add('glass-fallback')
    return { destroy: () => el.classList.remove('glass-fallback') }
  }
}
