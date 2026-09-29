import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildXianyuPublishQueueItems, createXianyuPublishQueue, getXianyuPublishQueue,
  dispatchXianyuPublishTarget, getXianyuPublishTask, parseXianyuPublishDispatch,
  parseXianyuPublishQueue, parseXianyuPublishTask, prepareXianyuPublishQueue, PUBLISH_QUEUE_BOUNDARY,
  persistXianyuPublishQueue, type PublishQueueScope,
} from '@/data/xianyu-publish-goods'
import { dispatchedTarget, platformTask, product, queueResponse } from './xianyu-publish-fixtures'

const state = vi.hoisted(() => ({ configured: true, fetch: vi.fn() }))
vi.mock('@/api/control', async () => {
  const { CloudCtlApiClient } = await import('@cloudctl/api-contracts')
  return {
    get controlApiConfigured() { return state.configured },
    createControlApiClient: () => new CloudCtlApiClient({ baseUrl: 'https://control.invalid', fetch: state.fetch }),
  }
})

function request() {
  return prepareXianyuPublishQueue({
    deviceId: 'device-1', accountId: 'account-1',
    items: buildXianyuPublishQueueItems([product()], ['product-1']),
  })
}

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  sessionStorage.clear()
  state.configured = true
  state.fetch.mockReset()
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('durable same-tab retry identity', () => {
  const scope: PublishQueueScope = { tenantId: 'tenant-1', userId: 'user-1', apiEnvironment: 'https://control.invalid' }
  const input = () => ({
    deviceId: 'device-1', accountId: 'account-1',
    items: buildXianyuPublishQueueItems([product()], ['product-1']),
  })

  it('restores the exact frozen request without persisting product text or trusting stored payloads', async () => {
    const first = await persistXianyuPublishQueue(scope, input(), ['product-1'])
    const raw = sessionStorage.getItem(sessionStorage.key(0)!)!
    expect(raw).not.toContain('Catalog description')
    expect(raw).not.toContain('12.50')
    expect(raw).not.toContain('account-1')
    expect(await persistXianyuPublishQueue(scope, input(), ['product-1'])).toEqual(first)
    expect(Object.isFrozen(first)).toBe(true)
  })

  it.each(['tenantId', 'userId', 'apiEnvironment'] as const)('never reuses identities after %s changes', async (field) => {
    const first = await persistXianyuPublishQueue(scope, input(), ['product-1'])
    const next = await persistXianyuPublishQueue({ ...scope, [field]: `${scope[field]}-changed` }, input(), ['product-1'])
    expect(next.queueId).not.toBe(first.queueId)
    expect(next.items[0]!.deliveryId).not.toBe(first.items[0]!.deliveryId)
  })

  it('rejects absent session and corrupt or missing required storage', async () => {
    await expect(persistXianyuPublishQueue(null, input(), ['product-1'])).rejects.toThrow('缺少')
    const first = await persistXianyuPublishQueue(scope, input(), ['product-1'])
    const key = sessionStorage.key(0)!
    sessionStorage.setItem(key, '{broken')
    await expect(persistXianyuPublishQueue(scope, input(), ['product-1'])).rejects.toThrow('存储失败或损坏')
    sessionStorage.removeItem(key)
    await expect(persistXianyuPublishQueue(scope, input(), ['product-1'], first)).rejects.toThrow('存储失败或损坏')
  })

  it('fails closed when persistence cannot be written or verified', async () => {
    const setItem = vi.spyOn(Object.getPrototypeOf(window.sessionStorage), 'setItem').mockImplementation(() => { throw new Error('QuotaExceededError') })
    await expect(persistXianyuPublishQueue(scope, input(), ['product-1'])).rejects.toThrow('存储失败或损坏')
    setItem.mockImplementation(() => {})
    await expect(persistXianyuPublishQueue(scope, input(), ['product-1'])).rejects.toThrow('存储失败或损坏')
  })

  it('rejects a structurally valid record whose queue identity was altered', async () => {
    await persistXianyuPublishQueue(scope, input(), ['product-1'])
    const key = sessionStorage.key(0)!
    const saved = JSON.parse(sessionStorage.getItem(key)!)
    saved.queueId = crypto.randomUUID()
    sessionStorage.setItem(key, JSON.stringify(saved))
    await expect(persistXianyuPublishQueue(scope, input(), ['product-1'])).rejects.toThrow('存储失败或损坏')
  })
})

describe('publish queue payload and staging identity', () => {
  it('uses ordered API media IDs without requiring custom attributes or inventing delivery proof', () => {
    const input = request()
    expect(input.items[0]).toMatchObject({
      description: 'Catalog description', price: '12.50', mediaAssetIds: ['asset-1', 'asset-2'],
      completionBoundary: PUBLISH_QUEUE_BOUNDARY, deliveryId: expect.any(String),
    })
    expect(input.items[0]!.deliveryId).not.toBe(input.queueId)
    expect(Object.isFrozen(input.items[0]!.mediaAssetIds)).toBe(true)
    expect(Object.isFrozen(input)).toBe(true)
  })

  it('omits media and deliveryId for a text-only product', () => {
    const items = buildXianyuPublishQueueItems([product({ mediaAssetIds: [], media: [] })], ['product-1'])
    expect(items[0]).not.toHaveProperty('mediaAssetIds')
    expect(prepareXianyuPublishQueue({ deviceId: 'device-1', accountId: 'account-1', items }).items[0]).not.toHaveProperty('deliveryId')
  })

  it.each([
    { description: '' }, { description: 'x'.repeat(1025) }, { description: 'nul\0text' },
    { price: '1.234' }, { price: '-1' }, { status: 'ARCHIVED' },
    { mediaAssetIds: Array.from({ length: 50 }, (_, i) => `asset-${i}`) },
    { mediaAssetIds: ['asset-1', 'asset-1'] }, { mediaAssetIds: [''] },
  ])('rejects invalid catalog fields %j', (overrides) => {
    expect(() => buildXianyuPublishQueueItems([product(overrides)], ['product-1'])).toThrow()
  })

  it('counts Unicode characters as the Python backend does and accepts 49 assets', () => {
    const items = buildXianyuPublishQueueItems([product({
      description: String.fromCodePoint(0x1f600).repeat(1024),
      mediaAssetIds: Array.from({ length: 49 }, (_, i) => `asset-${i}`),
    })], ['product-1'])
    expect(items).toHaveLength(1)
  })

  it('enforces 1..50 unique selected API products', () => {
    const products = Array.from({ length: 51 }, (_, i) => product({ id: `product-${i}` }))
    expect(() => buildXianyuPublishQueueItems(products, [])).toThrow()
    expect(() => buildXianyuPublishQueueItems(products, ['unknown'])).toThrow()
    expect(() => buildXianyuPublishQueueItems(products, ['product-1', 'product-1'])).toThrow()
    expect(() => buildXianyuPublishQueueItems(products, products.map((p) => p.id))).toThrow()
    expect(buildXianyuPublishQueueItems(products, products.slice(0, 50).map((p) => p.id))).toHaveLength(50)
  })
})

describe('runtime response correlation', () => {
  it('accepts the frozen backend queue and target shape', () => {
    const input = request()
    expect(parseXianyuPublishQueue(queueResponse(input), input).targets[0]).toMatchObject({ state: 'PENDING', item: input.items[0] })
  })

  it.each([
    ['queueId', 'other'], ['deviceId', 'other'], ['accountId', 'other'],
    ['targets', []], ['targets', null], ['replayed', 'false'], ['serialAdvanceBlocked', true],
  ])('rejects malformed or mismatched queue %s', (field, value) => {
    const input = request()
    expect(() => parseXianyuPublishQueue({ ...queueResponse(input), [field]: value }, input)).toThrow('响应不完整')
  })

  it.each([
    ['targetId', ''], ['queueId', 'other'], ['deviceId', 'other'], ['accountId', 'other'],
    ['position', 1], ['position', 0.5], ['state', 'MAGIC_SUCCESS'], ['taskIds', null],
    ['externalItemId', undefined], ['claimedBoundary', 'FULL_AUTO'], ['judgment', null],
  ])('rejects malformed or mismatched target %s', (field, value) => {
    const input = request()
    const raw = queueResponse(input)
    const changed = { ...raw.targets[0], [field]: value }
    expect(() => parseXianyuPublishQueue({ ...raw, targets: [changed] }, input)).toThrow()
  })

  it.each([
    ['description', 'changed'], ['price', '13.00'], ['mediaAssetIds', ['asset-2', 'asset-1']],
    ['deliveryId', 'other'], ['completionBoundary', 'FULL_AUTO'], ['unexpected', true],
  ])('rejects target item mismatch %s', (field, value) => {
    const input = request()
    const raw = queueResponse(input)
    const target = raw.targets[0]!
    expect(() => parseXianyuPublishQueue({
      ...raw, targets: [{ ...target, item: { ...target.item, [field]: value } }],
    }, input)).toThrow()
  })

  it('checks every position and refuses duplicate target IDs', () => {
    const input = prepareXianyuPublishQueue({
      deviceId: 'device-1', accountId: 'account-1',
      items: buildXianyuPublishQueueItems([product(), product({ id: 'product-2', price: '20' })], ['product-1', 'product-2']),
    })
    const raw = queueResponse(input)
    expect(parseXianyuPublishQueue({ ...raw, targets: [...raw.targets].reverse() }, input).targets.map((t) => t.position)).toEqual([0, 1])
    raw.targets[1]!.targetId = raw.targets[0]!.targetId
    expect(() => parseXianyuPublishQueue(raw, input)).toThrow()
  })

  it('accepts only an IN_FLIGHT dispatch response for the requested target and task', () => {
    const input = request()
    expect(parseXianyuPublishDispatch(dispatchedTarget(input), input, 'target-0')).toMatchObject({
      taskId: 'task-1', target: { targetId: 'target-0', state: 'IN_FLIGHT', taskIds: ['task-1'] },
    })
    expect(() => parseXianyuPublishDispatch({ ...dispatchedTarget(input), targetId: 'target-other' }, input, 'target-0'))
      .toThrow('身份不匹配')
    expect(() => parseXianyuPublishDispatch({ ...dispatchedTarget(input), taskId: 'task-other' }, input, 'target-0'))
      .toThrow('身份不匹配')
  })

  it('requires platform task identity and retains only raw events belonging to that task', () => {
    const input = request()
    const target = parseXianyuPublishDispatch(dispatchedTarget(input), input, 'target-0').target
    const raw = platformTask(input, {
      state: 'PAUSED_WAITING_USER', runnerStatus: 'PAUSED',
      events: [{ taskId: 'task-1', sequence: 1, eventType: 'STEP', stepId: 'open-form' }],
    })
    expect(parseXianyuPublishTask(raw, input, target, 'task-1')).toMatchObject({
      taskId: 'task-1', state: 'PAUSED_WAITING_USER', rawEvents: [{ stepId: 'open-form' }],
    })
    expect(() => parseXianyuPublishTask({ ...raw, batchId: 'other-queue' }, input, target, 'task-1')).toThrow('身份不匹配')
    expect(() => parseXianyuPublishTask({ ...raw, commandPayload: { ...raw.commandPayload, publishTargetId: 'other-target' } }, input, target, 'task-1'))
      .toThrow('身份不匹配')
    expect(() => parseXianyuPublishTask({ ...raw, events: [{ taskId: 'task-other' }] }, input, target, 'task-1'))
      .toThrow('身份不匹配')
  })

  it('keeps a recovered older task readable when completionBoundary is absent, but rejects a present mismatch', () => {
    const input = request()
    const target = parseXianyuPublishDispatch(dispatchedTarget(input), input, 'target-0').target
    const raw = platformTask(input)
    const legacyPayload: Record<string, unknown> = { ...raw.commandPayload }
    delete legacyPayload.completionBoundary
    expect(parseXianyuPublishTask({ ...raw, commandPayload: legacyPayload }, input, target, 'task-1'))
      .toMatchObject({ taskId: 'task-1', publishTargetId: 'target-0' })
    expect(() => parseXianyuPublishTask({
      ...raw, commandPayload: { ...raw.commandPayload, completionBoundary: 'FULL_AUTO' },
    }, input, target, 'task-1')).toThrow('身份不匹配')
  })
})

describe('create/get API surface', () => {
  it('retries the same frozen queue and delivery identities after an uncertain response', async () => {
    const input = request()
    state.fetch.mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(new Response(JSON.stringify(queueResponse(input)), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(queueResponse(input))))
    await expect(createXianyuPublishQueue(input)).rejects.toThrow('timeout')
    await createXianyuPublishQueue(input)
    await getXianyuPublishQueue(input)
    expect(state.fetch.mock.calls[0]![1].body).toBe(state.fetch.mock.calls[1]![1].body)
    expect(state.fetch.mock.calls.map(([url, init]) => [url, init.method])).toEqual([
      ['https://control.invalid/api/v1/xianyu/publish/queues', 'POST'],
      ['https://control.invalid/api/v1/xianyu/publish/queues', 'POST'],
      [`https://control.invalid/api/v1/xianyu/publish/queues/${input.queueId}`, 'GET'],
    ])
  })

  it('fails closed without API configuration, with no HTTP calls', async () => {
    state.configured = false
    await expect(createXianyuPublishQueue(request())).rejects.toThrow('未连接')
    await expect(getXianyuPublishQueue(request())).rejects.toThrow('未连接')
    expect(state.fetch).not.toHaveBeenCalled()
  })

  it('dispatches with no body and reads the exact platform task endpoint', async () => {
    const input = request()
    const target = dispatchedTarget(input)
    state.fetch.mockResolvedValueOnce(new Response(JSON.stringify(target)))
      .mockResolvedValueOnce(new Response(JSON.stringify(platformTask(input))))
    const dispatched = await dispatchXianyuPublishTarget(input, 'target-0')
    await getXianyuPublishTask(input, dispatched.target, dispatched.taskId)
    expect(state.fetch.mock.calls.map(([url, init]) => [url, init.method, init.body])).toEqual([
      [`https://control.invalid/api/v1/xianyu/publish/queues/${input.queueId}/targets/target-0/dispatch`, 'POST', undefined],
      ['https://control.invalid/api/v1/platform-tasks/task-1', 'GET', undefined],
    ])
  })
})
