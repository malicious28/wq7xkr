import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { readTokens, ThemeContext, type Theme } from './context'

const STORAGE_KEY = 'windesk.theme'

function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'dark' || stored === 'light') return stored
  } catch {
    // storage blocked (private mode): fall back to the OS preference
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function apply(theme: Theme): Theme {
  document.documentElement.dataset.theme = theme
  return theme
}

/**
 * The theme is applied to <html> *before* React re-renders, so tokens can be
 * read from computed CSS during render - no effect, no second render.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => apply(initialTheme()))

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = apply(current === 'dark' ? 'light' : 'dark')
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        // ignore: the choice just won't persist
      }
      return next
    })
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps -- tokens depend on the applied theme
  const tokens = useMemo(() => readTokens(), [theme])
  const value = useMemo(() => ({ theme, toggle, tokens }), [theme, toggle, tokens])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
