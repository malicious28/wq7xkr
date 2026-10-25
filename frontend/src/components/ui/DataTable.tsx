import type { ReactNode } from 'react'

import { Icon } from './Icon'
import s from './DataTable.module.css'

export interface Column<T> {
  key: string
  header: string
  cell: (row: T) => ReactNode
  align?: 'left' | 'right'
}

interface DataTableProps<T> {
  caption: string
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  /** Render collapsed behind a disclosure: the accessible table view of a chart. */
  collapsible?: boolean
  maxHeight?: number
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  collapsible = false,
  maxHeight = 360,
}: DataTableProps<T>) {
  const table = (
    <div className={s.scroll} style={{ maxHeight }} data-lenis-prevent>
      <table className={s.table}>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={c.align === 'right' ? s.right : undefined}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => (
                <td key={c.key} className={c.align === 'right' ? s.right : undefined}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
  if (!collapsible) return table
  return (
    <details className={s.details}>
      <summary>
        <Icon name="table" size={15} />
        Table view <span className={s.count}>{rows.length} rows</span>
      </summary>
      {table}
    </details>
  )
}
