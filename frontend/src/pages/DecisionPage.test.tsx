import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import decisionFixture from '../test/fixtures/decision.json'
import metaFixture from '../test/fixtures/meta.json'
import revisionsFixture from '../test/fixtures/revisions.json'
import { renderPage } from '../test/render'
import DecisionPage from './DecisionPage'

// Rendering and motion are covered elsewhere; here we test the page's logic.
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

beforeEach(() => {
  requests = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    requests.push(url)
    const body = url.startsWith('/api/meta')
      ? metaFixture
      : url.startsWith('/api/revisions')
        ? revisionsFixture
        : decisionFixture
    return new Response(JSON.stringify(body), { status: 200 })
  })
})

afterEach(() => vi.restoreAllMocks())

describe('DecisionPage', () => {
  it('shows the run that was available at the gate and how old it was', async () => {
    renderPage(<DecisionPage />, '/decision')
    expect(await screen.findByText('09:30 GMT')).toBeInTheDocument()
    expect(screen.getByText('Wed 14 Jan · 20 min before the cutoff')).toBeInTheDocument()
    expect(screen.getByText('Run arrived on schedule')).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: /Forecast and range for Thu 15 Jan/ }),
    ).toBeInTheDocument()
  })

  it('requests the decision for the default day and auction', async () => {
    renderPage(<DecisionPage />, '/decision')
    await screen.findByText('09:30 GMT')
    const call = requests.find((u) => u.startsWith('/api/decision'))
    expect(call).toContain('delivery_date=2026-01-15')
    expect(call).toContain('auction=n2ex_da')
  })

  it('hides the outturn when viewing as at the gate', async () => {
    const user = userEvent.setup()
    renderPage(<DecisionPage />, '/decision')
    await screen.findByText('09:30 GMT')
    expect(screen.getByText('253.6 GWh')).toBeInTheDocument()
    const outturn = screen.getByRole('radiogroup', { name: 'Outturn' })
    await user.click(within(outturn).getByRole('radio', { name: 'As at gate' }))
    expect(screen.queryByText('253.6 GWh')).not.toBeInTheDocument()
    expect(screen.getByText('Actual outturn (hidden)')).toBeInTheDocument()
  })

  it('switching to a custom gate sends a gate time instead of an auction', async () => {
    const user = userEvent.setup()
    renderPage(<DecisionPage />, '/decision')
    await screen.findByText('09:30 GMT')
    const auction = screen.getByRole('radiogroup', { name: /Auction/ })
    await user.click(within(auction).getByRole('radio', { name: 'Custom' }))
    const last = requests.filter((u) => u.startsWith('/api/decision')).at(-1)
    expect(last).toContain('gate_local=12%3A00')
    expect(last).not.toContain('auction=')
  })

  it('shows every forecast run for the day and how many beat the gate', async () => {
    renderPage(<DecisionPage />, '/decision')
    expect(
      await screen.findByText(/24 runs covered Thu 15 Jan; 12 were published before the gate/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: /All 24 forecast runs for Thu 15 Jan/ }),
    ).toBeInTheDocument()
  })

  it('offers the CSV only when it reproduces the chart (preset gate, no margin)', async () => {
    const user = userEvent.setup()
    renderPage(<DecisionPage />, '/decision')
    await screen.findByText('09:30 GMT')
    expect(screen.getByRole('link', { name: 'CSV' })).toHaveAttribute(
      'href',
      expect.stringContaining('auction=n2ex_da'),
    )
    const auction = screen.getByRole('radiogroup', { name: /Auction/ })
    await user.click(within(auction).getByRole('radio', { name: 'Custom' }))
    expect(screen.queryByRole('link', { name: 'CSV' })).not.toBeInTheDocument()
  })
})
