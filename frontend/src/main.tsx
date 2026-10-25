import '@fontsource-variable/inter-tight'
import '@fontsource-variable/jetbrains-mono'
import './styles/tokens.css'
import './styles/base.css'
import './styles/app.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { AppRouter } from './app/router'
import { MotionProvider } from './motion/MotionProvider'
import { ThemeProvider } from './theme/ThemeProvider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The dataset is an immutable snapshot: results never go stale in a session.
      staleTime: Infinity,
      gcTime: 30 * 60_000,
      retry: (count, error) =>
        count < 2 && !(error instanceof Error && /API 4\d\d/.test(error.message)),
      refetchOnWindowFocus: false,
    },
  },
})

const root = document.getElementById('root')
if (!root) throw new Error('#root missing from index.html')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MotionProvider>
          <AppRouter />
        </MotionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
