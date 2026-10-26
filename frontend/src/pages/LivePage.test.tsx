import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import dayFixture from '../test/fixtures/live_day.json'
import summaryFixture from '../test/fixtures/live_summary.json'
import metaFixture from '../test/fixtures/meta.json'
import { renderPage } from '../test/render'
import LivePage from './LivePage'

vi.mock('../charts/EChart', () => ({
  EChart: ({ label }: { label: string }) => <div role="img" aria-label={label} />,
}))
vi.mock('lenis', () => ({
  default: class {
    raf() {}
    destroy() {}
    scrollTo() {}
    stop() {}
    start() {}
  },
}))

let requests: string[] = []

function respond(url: string): Response {
  if (url.startsWith('/api/meta')) return new Response(JSON.stringify(metaFixture))
  if (url.startsWith('/api/live/summary')) return new Response(JSON.stringify(summaryFixture))
  if (url.startsWith('/api/live/day')) return new Response(JSON.stringify(dayFixture))
  return new Response('{}', { status: 404 })
}

beforeEach(() => {
  requests = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    requests.push(String(input))
    return respond(String(input))
  })
})

afterEach(() => vi.restoreAllMocks())

describe('LivePage', () => {
  it('opens on the next open gate and shows Elexon, Windesk and the safe minimum', async () => {
    renderPage(<LivePage />, '/live')
    expect(await screen.findAllByText('Provisional · updates each run')).not.toHaveLength(0)
    expect(requests.find((u) => u.startsWith('/api/live/day'))).toContain(
      'delivery_date=2026-10-27',
    )
    expect(screen.getByText('Elexon predicted')).toBeInTheDocument()
    expect(screen.getByText('Windesk predicted')).toBeInTheDocument()
    expect(screen.getByText('Safe minimum (P10)')).toBeInTheDocument()
    expect(screen.getByText('Not yet')).toBeInTheDocument()
  })

  it('shows the scoreboard since live start', async () => {
    renderPage(<LivePage />, '/live')
    expect(await screen.findByText('Scoreboard since Thu 1 Oct')).toBeInTheDocument()
    expect(screen.getByText('2,385 MW')).toBeInTheDocument()
    expect(screen.getByText('1,302 MW')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('warns when the server is serving stale data', async () => {
    const stale = structuredClone(summaryFixture)
    stale.data.status.stale = true
    vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
      const url = String(input)
      return url.startsWith('/api/live/summary')
        ? new Response(JSON.stringify(stale))
        : respond(url)
    })
    renderPage(<LivePage />, '/live')
    expect(await screen.findByText(/showing the last good data/)).toBeInTheDocument()
  })
})
