import { afterEach, describe, expect, it, vi } from 'vitest'
import { collectImBody, ImApiError, listImBodyCollections } from '@/api/im'
vi.mock('@/api/control', () => ({ controlApiConfigured: true, controlApiBaseUrl: () => 'http://control.test', controlApiHeaders: () => ({ Authorization: 'Bearer fixture' }) }))
afterEach(() => vi.unstubAllGlobals())
describe('im-chat-collection/1 API', () => {
  it('uses read-only encoded GET and forwards cancellation', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ capability: { supported: false, available: false, reason: 'PROTOCOL_UNSUPPORTED' }, items: [] })))
    vi.stubGlobal('fetch', fetcher)
    const controller = new AbortController()
    await listImBodyCollections('thread/id', controller.signal)
    const [url, options] = fetcher.mock.calls[0]
    expect(url).toBe('http://control.test/api/v1/im/threads/thread%2Fid/body-collections')
    expect(options.method).toBe('GET'); expect(options.body).toBeUndefined(); expect(options.signal).toBe(controller.signal)
  })
  it('posts only an empty object with the supplied stable idempotency key', async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ taskId: 'task', threadId: 'thread/id', status: 'QUEUED' }), { status: 201 })))
    vi.stubGlobal('fetch', fetcher)
    await collectImBody('thread/id', 'stable-key'); await collectImBody('thread/id', 'stable-key')
    for (const [url, options] of fetcher.mock.calls) {
      expect(url).toBe('http://control.test/api/v1/im/threads/thread%2Fid:collect-body')
      expect(options.method).toBe('POST'); expect(options.body).toBe('{}')
      expect(options.headers.get('Idempotency-Key')).toBe('stable-key')
      expect(options.headers.get('Authorization')).toBe('Bearer fixture')
    }
  })
  it('preserves 404 for honest old-cloud fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 404 })))
    await expect(listImBodyCollections('thread')).rejects.toMatchObject({ status: 404 })
  })
  it('rejects malformed response and invalid idempotency keys', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ taskId: 'task', threadId: 'other', status: 'QUEUED' })))
    vi.stubGlobal('fetch', fetcher)
    await expect(collectImBody('thread', '')).rejects.toThrow('Invalid collection')
    await expect(collectImBody('thread', 'x'.repeat(129))).rejects.toThrow('Invalid collection')
    expect(fetcher).not.toHaveBeenCalled()
    await expect(collectImBody('thread', 'key')).rejects.toThrow('Unconfirmed collection')
  })
  it('retains server denial status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 409 })))
    await expect(collectImBody('thread', 'key')).rejects.toBeInstanceOf(ImApiError)
  })
})
