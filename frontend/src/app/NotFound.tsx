import { Link } from 'react-router-dom'

import { PageHeader } from '../components/ui/ui'

export function NotFound() {
  return (
    <PageHeader eyebrow="404" title="Nothing at this address" lede="The page may have moved.">
      <p style={{ marginTop: 20 }}>
        <Link to="/">Back to the overview</Link>
      </p>
    </PageHeader>
  )
}
