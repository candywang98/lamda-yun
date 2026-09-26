import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  dispatchListingCollectTask, listFleetListings, FleetListingsApiError,
} from '@/features/fleet/listings-api'

const config = vi.hoisted(() => ({ configured: true }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return config.configured },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({ Authorization: 'Bearer fixture-only' }),
}))

const taskId = '018f1a2b-0000-7000-8000-000000000001'
const fetchMock = vi.fn()

beforeEach(() => {
  config.configured = true
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status }))
}

describe('listing-sync/20260926.1 collection API', () => {
  it('uses the existing collect-only task and explicit caller key, with no scheduler or destructive steps', async () => {
    respond({ taskId }, 201)
    expect(await dispatchListingCollectTask({ deviceId: 'device-a', idempotencyKey: 'same-key-1' })).toEqual({ taskId })
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/mobile/tasks')
    expect(options.method).toBe('POST')
    expect(options.credentials).toBe('same-origin')
    expect(new Headers(options.headers).get('Idempotency-Key')).toBe('same-key-1')
    expect(new Headers(options.headers).get('Authorization')).toBe('Bearer fixture-only')
    expect(JSON.parse(String(options.body))).toEqual({
      deviceId: 'device-a',
      targetPackage: 'com.taobao.idlefish',
      commandType: 'xianyu.collect_listings',
      totalTimeoutMs: 900000,
      steps: [
        { stepId: 'open-profile', timeoutMs: 30000, action: 'ui.tap', locatorRef: 'xianyu_profile_tab' },
        { stepId: 'open-published', timeoutMs: 30000, action: 'ui.tap', locatorRef: 'xianyu_my_published' },
        { stepId: 'wait-onsale-tab', timeoutMs: 30000, action: 'ui.wait', locatorRef: 'xianyu_pub_tab_onsale', condition: 'EXISTS', pollMs: 500 },
        { stepId: 'collect-all', timeoutMs: 600000, action: 'ui.collectListings', tab: 'onsale', maxScreens: 40 },
      ],
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([
    null, {}, [], { id: taskId }, { taskId: null }, { taskId: '' }, { taskId: ' ' },
    { taskId: 42 }, { taskId: {} }, { taskId: 'not-a-task-id' }, { taskId: `${taskId} ` },
  ].map((payload) => ({ payload })))('rejects missing or malformed task identity: $payload', async ({ payload }) => {
    respond(payload, 201)
    await expect(dispatchListingCollectTask({ deviceId: 'device-a', idempotencyKey: 'keep-this-key' }))
      .rejects.toMatchObject({ status: 201, message: '派发响应缺少有效 taskId，结果未确认' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('rejects a successful non-JSON response as ambiguous instead of accepting an empty ID', async () => {
    fetchMock.mockResolvedValueOnce(new Response('not json', { status: 200 }))
    await expect(dispatchListingCollectTask({ deviceId: 'device-a', idempotencyKey: 'keep-this-key' }))
      .rejects.toBeInstanceOf(FleetListingsApiError)
  })

  it('keeps the caller key and body identical after an ambiguous transport failure', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network failed after acceptance'))
    const input = { deviceId: 'device-a', idempotencyKey: 'batch-device-key' }
    await expect(dispatchListingCollectTask(input)).rejects.toThrow('network failed')
    respond({ taskId })
    expect(await dispatchListingCollectTask(input)).toEqual({ taskId })
    const calls = fetchMock.mock.calls as [string, RequestInit][]
    expect(calls[0]![1].body).toEqual(calls[1]![1].body)
    expect(new Headers(calls[0]![1].headers).get('Idempotency-Key')).toBe('batch-device-key')
    expect(new Headers(calls[1]![1].headers).get('Idempotency-Key')).toBe('batch-device-key')
  })

  it.each([403, 409, 503])('surfaces HTTP %s without automatic retry', async (status) => {
    respond({ detail: 'fixture rejection' }, status)
    await expect(dispatchListingCollectTask({ deviceId: 'device-a', idempotencyKey: 'batch-key' }))
      .rejects.toMatchObject({ status, message: `fixture rejection（HTTP ${status}）` })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('refuses both reads and dispatch when the API is not configured', async () => {
    config.configured = false
    await expect(listFleetListings()).rejects.toMatchObject({ status: 0 })
    await expect(dispatchListingCollectTask({ deviceId: 'device-a', idempotencyKey: 'batch-key' }))
      .rejects.toMatchObject({ status: 0 })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('listing-sync/20260926.1 history API', () => {
  it('preserves additive source fields, order and duplicate itemKeys, and forwards the opaque cursor', async () => {
    const items = [
      { id: 'row-a', deviceId: 'device-a', platform: 'xianyu', itemKey: 'same-item' },
      { id: 'row-b', deviceId: 'device-b', platform: 'xianyu', itemKey: 'same-item' },
    ]
    respond({ items, total: 24, nextCursor: 'next+page==' })
    expect(await listFleetListings({ deviceId: 'device / a', limit: 50, cursor: 'opaque+/==' }))
      .toEqual({ items, total: 24, nextCursor: 'next+page==' })
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(Object.fromEntries(new URL(url).searchParams)).toEqual({
      device_id: 'device / a', limit: '50', cursor: 'opaque+/==',
    })
    expect(options.method).toBe('GET')
    expect(options.credentials).toBe('same-origin')
  })

  it('preserves legacy rows without inventing a device, platform or row identity', async () => {
    const items = [{ itemKey: 'legacy' }, { itemKey: 'legacy' }]
    respond({ items, total: 2, nextCursor: null })
    expect(await listFleetListings()).toEqual({ items, total: 2, nextCursor: null })
    expect(fetchMock.mock.calls[0]![0]).toBe('http://control.test/api/v1/fleet/listings/history')
  })

  it.each([
    {}, { items: null, total: 0 }, { items: [], total: '0' }, { items: [], total: -1 },
    { items: [null], total: 1 }, { items: [{}], total: 1 },
    { items: [], total: 0, nextCursor: 10 }, { items: [], total: 0, nextCursor: '' },
  ])('surfaces malformed history as an error, never as successful empty state: %j', async (payload) => {
    respond(payload)
    await expect(listFleetListings()).rejects.toMatchObject({ message: '宝贝历史响应格式无效' })
  })

  it('surfaces read failures', async () => {
    respond({ detail: 'cursor mismatch' }, 422)
    await expect(listFleetListings({ cursor: 'stale-cursor' }))
      .rejects.toMatchObject({ status: 422, message: 'cursor mismatch（HTTP 422）' })
  })
})
