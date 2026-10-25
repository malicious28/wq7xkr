import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DataTable } from './DataTable'
import { Callout, Segmented, StatTile } from './ui'

describe('Segmented', () => {
  it('is a labelled radio group that reports the chosen value', async () => {
    const onChange = vi.fn()
    render(
      <Segmented
        label="Scope"
        value="a"
        onChange={onChange}
        options={[
          { value: 'a', label: 'Alpha' },
          { value: 'b', label: 'Beta' },
        ]}
      />,
    )
    const group = screen.getByRole('radiogroup', { name: 'Scope' })
    expect(group).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Alpha' })).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(screen.getByRole('radio', { name: 'Beta' }))
    expect(onChange).toHaveBeenCalledWith('b')
  })
})

describe('Callout', () => {
  it('never relies on colour alone: tone comes with a text label', () => {
    render(<Callout tone="warning" />)
    expect(screen.getByRole('status')).toHaveTextContent('Warning')
  })

  it('announces critical problems as alerts', () => {
    render(<Callout tone="critical" title="Broken" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Broken')
  })
})

describe('StatTile and DataTable', () => {
  it('renders a label/value pair', () => {
    render(<StatTile label="MAE" value="1,948 MW" detail="24 h ahead" />)
    expect(screen.getByText('1,948 MW')).toBeInTheDocument()
  })

  it('renders an accessible table with a caption', () => {
    render(
      <DataTable
        caption="Errors"
        columns={[{ key: 'k', header: 'Key', cell: (r: { k: string }) => r.k }]}
        rows={[{ k: 'one' }, { k: 'two' }]}
        rowKey={(r) => r.k}
      />,
    )
    expect(screen.getByRole('table', { name: 'Errors' })).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })
})
