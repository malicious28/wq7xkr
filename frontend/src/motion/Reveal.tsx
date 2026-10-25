import { useEffect, useRef, useState } from 'react'
import type { ElementType, ReactNode } from 'react'

import { useMotion } from './context'
import styles from './Reveal.module.css'

interface RevealProps {
  children: ReactNode
  as?: ElementType
  delay?: number
  className?: string
}

/** Fades content up once as it scrolls into view. Static under reduced motion. */
export function Reveal({ children, as: Tag = 'div', delay = 0, className }: RevealProps) {
  const ref = useRef<HTMLElement | null>(null)
  const { reducedMotion } = useMotion()
  const [visible, setVisible] = useState(
    reducedMotion || typeof IntersectionObserver === 'undefined',
  )

  useEffect(() => {
    if (visible || !ref.current) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setVisible(true)
          io.disconnect()
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
    )
    io.observe(ref.current)
    return () => io.disconnect()
  }, [visible])

  return (
    <Tag
      ref={ref}
      className={[styles.reveal, visible ? styles.in : '', className].filter(Boolean).join(' ')}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </Tag>
  )
}
