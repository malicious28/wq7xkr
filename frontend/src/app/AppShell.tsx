import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useMeta } from '../api/hooks'
import { Icon } from '../components/ui/Icon'
import { useMotion } from '../motion/context'
import { useTheme } from '../theme/context'
import s from './AppShell.module.css'
import { MethodologyDrawer } from './MethodologyDrawer'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/decision', label: 'Decision' },
  { to: '/explorer', label: 'Horizon' },
  { to: '/accuracy', label: 'Accuracy' },
  { to: '/models', label: 'Models' },
  { to: '/ramps', label: 'Ramps' },
  { to: '/quality', label: 'Data quality' },
  { to: '/live', label: 'Try now', live: true },
]

/**
 * The tab strip scrolls sideways when it is narrower than the tabs. Its
 * scrollbar is hidden, so: a vertical wheel scrolls it, the edges fade where
 * tabs are hidden, and the active tab is always brought into view.
 */
function useTabStrip(pathname: string) {
  const strip = useRef<HTMLUListElement | null>(null)

  useEffect(() => {
    const ul = strip.current
    if (!ul) return
    const mark = () => {
      const max = ul.scrollWidth - ul.clientWidth
      ul.dataset.fadeStart = String(ul.scrollLeft > 1)
      ul.dataset.fadeEnd = String(ul.scrollLeft < max - 1)
    }
    const onWheel = (e: WheelEvent) => {
      if (ul.scrollWidth <= ul.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
      e.preventDefault()
      ul.scrollLeft += e.deltaY
    }
    const resize = new ResizeObserver(mark)
    resize.observe(ul)
    ul.addEventListener('scroll', mark, { passive: true })
    ul.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      resize.disconnect()
      ul.removeEventListener('scroll', mark)
      ul.removeEventListener('wheel', onWheel)
    }
  }, [])

  useEffect(() => {
    const ul = strip.current
    const active = ul?.querySelector<HTMLElement>('[aria-current="page"]')
    if (!ul || !active) return
    const left = active.offsetLeft - ul.offsetLeft
    if (left < ul.scrollLeft || left + active.offsetWidth > ul.scrollLeft + ul.clientWidth) {
      ul.scrollTo({ left: left - (ul.clientWidth - active.offsetWidth) / 2, behavior: 'smooth' })
    }
  }, [pathname])

  return strip
}

function GlassNav({ onMethodology }: { onMethodology: () => void }) {
  const glass = useRef<HTMLDivElement | null>(null)
  const strip = useTabStrip(useLocation().pathname)
  const { registerGlass } = useMotion()
  const { theme, toggle } = useTheme()

  useEffect(() => {
    if (!glass.current) return
    return registerGlass(glass.current, {
      tint: theme === 'dark' ? 'rgba(16,24,39,0.35)' : 'rgba(255,255,255,0.35)',
    })
  }, [registerGlass, theme])

  return (
    <div className={s.navWrap}>
      <div ref={glass} className={s.navGlass}>
        <nav className={s.nav} aria-label="Primary">
          <NavLink to="/" className={s.brand} aria-label="Wind Forecast Desk, overview">
            <span className={s.brandMark} aria-hidden>
              <svg
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h7" />
              </svg>
            </span>
            <span className={s.brandText}>Windesk</span>
          </NavLink>
          <ul ref={strip} className={s.links} data-lenis-prevent>
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.end}
                  className={({ isActive }) => (isActive ? `${s.link} ${s.linkActive}` : s.link)}
                >
                  {'live' in n && <span className={s.liveDot} aria-hidden />}
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className={s.actions}>
            <button
              type="button"
              className={s.iconButton}
              onClick={onMethodology}
              aria-label="Open methodology"
            >
              <Icon name="book" size={17} />
              <span className={s.actionText}>Method</span>
            </button>
            <button
              type="button"
              className={s.iconButton}
              onClick={toggle}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={17} />
            </button>
          </div>
        </nav>
      </div>
    </div>
  )
}

export function AppShell() {
  const [drawer, setDrawer] = useState(false)
  const { pathname } = useLocation()
  const { getLenis } = useMotion()
  const meta = useMeta().data?.data

  // New page: start at the top (Lenis owns the scroll position).
  useEffect(() => {
    getLenis()?.scrollTo(0, { immediate: true })
  }, [pathname, getLenis])

  return (
    <div className={s.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className={s.backdrop} aria-hidden>
        <div className={s.aurora} />
        <div className={s.grain} />
      </div>
      <GlassNav onMethodology={() => setDrawer(true)} />
      <main id="main" className={s.main} tabIndex={-1}>
        <Outlet context={{ openMethodology: () => setDrawer(true) }} />
      </main>
      <footer className={s.footer}>
        <div>
          Data: Elexon BMRS <code>FUELHH</code> (wind outturn) and <code>WINDFOR</code> (wind
          forecast), national level. All times UK local.
        </div>
        {meta && (
          <div className={s.version}>
            data_version <code>{meta.data_version}</code> · fetched {meta.fetched_at.slice(0, 10)}
          </div>
        )}
      </footer>
      <MethodologyDrawer open={drawer} onClose={() => setDrawer(false)} />
    </div>
  )
}
