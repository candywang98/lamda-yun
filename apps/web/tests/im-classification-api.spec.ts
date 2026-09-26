import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  classifyImMessage, reclassifyImMessage, listImThreads, listImMessages, ImApiError,
  type ImBucket, type ImClassification,
} from '@/api/im'
import { categoryLabel, classificationSource, classificationVersion } from '@/features/im/classification'

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({ Authorization: 'Bearer test-session' }),
}))

describe('im-notify/20260926.1 API contract', () => {
  const fetchMock = vi.fn()
  const respond = (payload: unknown, status = 200) => fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify(payload), { status }),
  )
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it.each<ImBucket>(['all', 'user', 'notice', 'review'])('queries bucket %s server-side on both reads', async (bucket) => {
    const bucketCounts = { all: 120, user: 84, notice: 67, review: 20 }
    respond({ items: [{ id: 'mixed-thread', lastMessageText: '服务端分类摘要' }], count: 1, bucketCounts })
    const page = await listImThreads('device / one', true, bucket)
    const url = new URL(fetchMock.mock.calls[0]![0] as string)
    expect(url.pathname).toBe('/api/v1/im/threads')
    expect(Object.fromEntries(url.searchParams)).toEqual({ deviceId: 'device / one', unread: 'true', bucket })
    expect(page.bucketCounts).toEqual(bucketCounts)
    expect(page.items[0]!.lastMessageText).toBe('服务端分类摘要')
    expect(page.count).toBe(1)
    respond({ items: [{ id: 'message-without-classification' }] })
    const messages = await listImMessages('thread / one', bucket)
    expect(fetchMock.mock.calls[1]![0]).toBe(
      `http://control.test/api/v1/im/threads/thread%20%2F%20one/messages?limit=200&latest=true&bucket=${bucket}`,
    )
    expect(messages).toEqual([{ id: 'message-without-classification' }])
  })

  it('keeps legacy DTOs and defaults callers to all without guessing bucket counts', async () => {
    respond({ items: [{ id: 'legacy', lastMessageText: ' ' }], count: 1 })
    expect(await listImThreads()).toEqual({
      items: [{ id: 'legacy', lastMessageText: null }], count: 1, bucketCounts: null,
    })
    expect(fetchMock.mock.calls[0]![0]).toBe('http://control.test/api/v1/im/threads?bucket=all')
    respond({ items: [] })
    await listImMessages('legacy')
    expect(fetchMock.mock.calls[1]![0]).toContain('bucket=all')
    expect(categoryLabel()).toBe('待确认')
    expect(classificationSource()).toBe('未分类')
    expect(classificationVersion()).toBe(0)
  })

  it.each(['HUMAN_MESSAGE', 'SYSTEM_NOTICE', 'PROMOTION', 'UNKNOWN', null] as const)(
    'POSTs only category %s and expectedVersion to the correction endpoint',
    async (category) => {
      const updated = { id: 'm / 1', classification: { category: category ?? 'UNKNOWN', version: 5 } }
      respond(updated)
      expect(await classifyImMessage('m / 1', category, 4)).toEqual(updated)
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('http://control.test/api/v1/im/messages/m%20%2F%201:classify')
      expect(init.method).toBe('POST')
      expect(init.credentials).toBe('same-origin')
      expect(new Headers(init.headers).get('Authorization')).toBe('Bearer test-session')
      expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
      expect(JSON.parse(String(init.body))).toEqual({ category, expectedVersion: 4 })
      expect(fetchMock).toHaveBeenCalledTimes(1)
    },
  )

  it('reclassifies a single message without resetting a manual override or sending private text', async () => {
    const updated = { id: 'm-1', text: 'private', classification: { source: 'MANUAL', modelStatus: 'PENDING', version: 10 } }
    respond(updated)
    expect(await reclassifyImMessage('m-1', 9)).toEqual(updated)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/im/messages/m-1:reclassify')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ expectedVersion: 9 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([403, 404, 409, 503])('preserves HTTP %s for visible failure/conflict handling', async (status) => {
    respond({ detail: 'classification failed' }, status)
    await expect(classifyImMessage('m-1', null, 1)).rejects.toMatchObject({
      status, message: `classification failed（HTTP ${status}）`,
    })
    respond({ detail: 'reclassification failed' }, status)
    await expect(reclassifyImMessage('m-1', 1)).rejects.toBeInstanceOf(ImApiError)
  })

  it.each([-1, 1.5, Number.NaN, undefined])('does not guess a concurrency version from malformed value %s', (version) => {
    expect(classificationVersion({ version } as ImClassification)).toBeNull()
  })
})
