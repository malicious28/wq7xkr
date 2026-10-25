import type { Envelope } from './types'

export type QueryParams = Record<string, string | number | boolean | null | undefined>

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function buildUrl(path: string, params: QueryParams = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${path}?${qs}` : path
}

/** FastAPI returns `detail` as a string or as a list of validation errors. */
function readDetail(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : String(d)))
        .join('; ')
    }
  }
  return 'Unexpected error'
}

export async function getJson<T>(
  path: string,
  params?: QueryParams,
  signal?: AbortSignal,
): Promise<Envelope<T>> {
  const res = await fetch(buildUrl(path, params), {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!res.ok) {
    let body: unknown = null
    try {
      body = await res.json()
    } catch {
      // non-JSON error body (proxy, gateway): fall through with a generic detail
    }
    throw new ApiError(res.status, readDetail(body))
  }
  return (await res.json()) as Envelope<T>
}
