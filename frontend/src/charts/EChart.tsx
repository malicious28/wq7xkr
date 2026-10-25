import { useEffect, useRef } from 'react'
import type { ECharts } from 'echarts/core'

import type { Option } from './echarts'
import styles from './EChart.module.css'

interface EChartProps {
  option: Option
  /** Accessible name; the visible title lives outside the chart. */
  label: string
  height?: number
  /** Dim while a new slice loads, keeping the previous frame (no skeleton flash). */
  stale?: boolean
  onClick?: (params: { dataIndex: number; seriesName?: string; data?: unknown }) => void
}

/**
 * Thin lifecycle wrapper: init once, apply options as they change, resize with
 * the container, dispose on unmount. Options are built by pure functions in
 * ./options, so this component holds no chart logic.
 *
 * ECharts (~225 kB gzipped) is imported on first use rather than with the page,
 * so text and figures paint at once and charts fill in as the library arrives.
 */
export function EChart({ option, label, height = 320, stale = false, onClick }: EChartProps) {
  const host = useRef<HTMLDivElement | null>(null)
  const chart = useRef<ECharts | null>(null)
  const latest = useRef(option)
  const clickRef = useRef(onClick)
  useEffect(() => {
    clickRef.current = onClick
  }, [onClick])

  useEffect(() => {
    let disposed = false
    let ro: ResizeObserver | null = null
    void import('./echarts').then(({ echarts }) => {
      if (disposed || !host.current) return
      const instance = echarts.init(host.current, null, { renderer: 'svg' })
      chart.current = instance
      instance.on('click', (p) =>
        clickRef.current?.(p as Parameters<NonNullable<typeof onClick>>[0]),
      )
      instance.setOption(latest.current, { notMerge: true })
      ro = new ResizeObserver(() => instance.resize())
      ro.observe(host.current)
    })
    return () => {
      disposed = true
      ro?.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    latest.current = option // applied on init if the library is still loading
    chart.current?.setOption(option, { notMerge: true, lazyUpdate: true })
  }, [option])

  return (
    <div
      ref={host}
      role="img"
      aria-label={label}
      className={styles.chart}
      data-stale={stale || undefined}
      style={{ height }}
    />
  )
}
