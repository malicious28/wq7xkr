import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

import { useMotion } from '../motion/context'
import { useTheme } from '../theme/context'
import s from './GlassPanel.module.css'

/**
 * A liquid-glass surface (liquidGL lens) with a CSS frost fallback.
 *
 * Outside a fixed/sticky ancestor, liquidGL draws on a canvas appended to
 * <body> at the lens's z-index. So the lens is an *empty* layer, and the
 * content is its sibling one z-step above. Nested inside the lens, the content
 * would be trapped beneath the canvas.
 */
export function GlassPanel({ children, className }: { children: ReactNode; className?: string }) {
  const lens = useRef<HTMLDivElement | null>(null)
  const { registerGlass } = useMotion()
  const { theme } = useTheme()

  useEffect(() => {
    if (!lens.current) return
    return registerGlass(lens.current, {
      refraction: 0.018,
      bevelDepth: 0.1,
      frost: 1,
      specular: true,
      tint: theme === 'dark' ? 'rgba(16,24,39,0.30)' : 'rgba(255,255,255,0.18)',
    })
  }, [registerGlass, theme])

  return (
    <div className={[s.panel, className].filter(Boolean).join(' ')}>
      <div ref={lens} className={s.lens} aria-hidden />
      {/* Excluded from the glass snapshot, or the lens would refract its own text. */}
      <div className={s.content} data-liquid-ignore>
        {children}
      </div>
    </div>
  )
}
