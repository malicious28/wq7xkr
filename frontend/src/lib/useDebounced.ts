import { useEffect, useState } from 'react'

/** The value, settled for `ms`: lets a slider move freely while queries follow at rest. */
export function useDebounced<T>(value: T, ms = 160): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return settled
}
