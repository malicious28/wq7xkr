import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, buildUrl, getJson } from './client'

afterEach(() => vi.restoreAllMocks())

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('buildUrl', () => {
  it('drops empty parameters and encodes the rest', () => {
    expect(buildUrl('/api/x', { a: 1, b: '', c: undefined, d: null, e: 'x y' })).toBe(
      '/api/x?a=1&e=x+y',
    )
    expect(buildUrl('/api/x')).toBe('/api/x')
  })
})

describe('getJson', () => {
  it('returns the envelope on success', async () => {
    mockFetch(200, { data: { ok: true }, meta: { data_version: 'abc' } })
    const res = await getJson<{ ok: boolean }>('/api/x')
    expect(res.data.ok).toBe(true)
  })

  it('surfaces a string detail from FastAPI', async () => {
    mockFetch(422, { detail: 'Data covers delivery days 2025-12-01 to 2026-02-01' })
    await expect(getJson('/api/x')).rejects.toMatchObject({
      status: 422,
      detail: 'Data covers delivery days 2025-12-01 to 2026-02-01',
    })
  })

  it('flattens validation error lists', async () => {
    mockFetch(422, { detail: [{ msg: 'too big' }, { msg: 'too small' }] })
    await expect(getJson('/api/x')).rejects.toThrow('too big; too small')
  })

  it('copes with a non-JSON error body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('Bad gateway', { status: 502 }))
    const err = await getJson('/api/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(502)
  })
})
