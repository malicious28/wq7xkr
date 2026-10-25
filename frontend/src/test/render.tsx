import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'

import { MotionProvider } from '../motion/MotionProvider'
import { ThemeProvider } from '../theme/ThemeProvider'

/** Render a page inside the real providers, at a given URL. */
export function renderPage(element: ReactElement, url = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '*', element }], { initialEntries: [url] })
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MotionProvider>
          <RouterProvider router={router} />
        </MotionProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}
