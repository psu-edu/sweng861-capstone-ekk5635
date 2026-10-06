import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { collectFinancials, generateSummary, getSummary } from '@/api/summaries'
import { signIn, signOut } from '@/auth/session'

// As in api/coverages: what matters is the verb and the path each wrapper sends.
describe('api/summaries', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))
    signIn('header.payload.signature')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    signOut()
  })

  function lastCall(): { path: string; init: RequestInit } {
    const [path, init] = fetchMock.mock.lastCall as [string, RequestInit]
    return { path, init }
  }

  it('reads the stored summary with GET, URL-encoding the id', async () => {
    await getSummary('a/b')
    expect(lastCall()).toMatchObject({ path: '/api/coverages/a%2Fb/summary', init: { method: 'GET' } })
  })

  it('generates with POST and no body', async () => {
    await generateSummary('7')
    const { path, init } = lastCall()
    expect(path).toBe('/api/coverages/7/summary')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })

  it('collects financial figures with POST and no body', async () => {
    await collectFinancials('7')
    const { path, init } = lastCall()
    expect(path).toBe('/api/coverages/7/financials')
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
  })
})
