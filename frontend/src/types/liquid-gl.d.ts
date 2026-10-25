// Minimal typings for liquid-gl 3.x (the package ships none).
declare module 'liquid-gl' {
  import type Lenis from 'lenis'

  export interface LiquidGLLens {
    destroy(): void
    setTint(color: string | null): void
    setDraggable(enabled: boolean): void
  }

  export interface LiquidGLOptions {
    target: string
    snapshot?: string
    resolution?: number
    engine?: 'auto' | 'webgpu' | 'webgl2' | 'webgl' | 'css'
    zIndex?: number
    content?: string | false
    refraction?: number
    aberration?: number
    bevelDepth?: number
    bevelWidth?: number
    frost?: number
    shadow?: boolean
    specular?: boolean
    reveal?: 'none' | 'fade'
    tilt?: boolean
    tiltFactor?: number
    tiltEase?: number
    magnify?: number
    tint?: string | null
    helper?: boolean
    on?: { init?: (lens: LiquidGLLens) => void }
  }

  export interface LiquidGL {
    (options: LiquidGLOptions): LiquidGLLens | LiquidGLLens[] | undefined
    registerDynamic(elements: string | Element | Element[]): void
    syncWith(config?: {
      lenis?: Lenis | false
      gsap?: unknown | false
      locomotiveScroll?: unknown | false
    }): { lenis?: Lenis } | undefined
  }

  const liquidGL: LiquidGL | undefined
  export default liquidGL
}
