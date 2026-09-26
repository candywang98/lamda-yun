import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchOrder,
  fetchXianyuOrderRun,
  formatOrderAmount,
  formatOrderTime,
  isOrderDirection,
  isXianyuOrderRunTerminal,
  listOrders,
  orderDirectionLabel,
  OrdersApiError,
  OrdersProtocolError,
  startXianyuOrderCollect,
  type OrderDetail,
  type OrderRow,
  type XianyuOrderRunTask,
} from '@/api/orders'
import { ORDER_DELIVERY_PROTOCOL, deliveryLabel, validOrderDelivery, type OrderDelivery } from '@/features/orders/delivery'

const config = vi.hoisted(() => ({ configured: true }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return config.configured },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({ 'X-Tenant-Id': 'test-tenant', 'X-User-Id': 'test-operator' }),
  operationsMockEnabled: false,
  createControlApiClient: () => ({}),
}))

const fetcher = vi.fn()
const runId = '018f1a2b-0000-7000-8000-000000000010'
const taskId = '018f1a2b-0000-7000-8000-000000000020'
const durableInput = { deviceId: 'dev-alpha-0001', direction: 'SOLD' as const, maxRows: 10, orderDeliveryProtocol: ORDER_DELIVERY_PROTOCOL }
const identity = { runId, deviceId: durableInput.deviceId, direction: durableInput.direction, maxRows: 10, taskIds: [taskId] }

function deliveryFixture(overrides: Partial<OrderDelivery> = {}): OrderDelivery {
  return { protocolVersion: ORDER_DELIVERY_PROTOCOL, state: 'PENDING', receivedScreens: [],
    expectedScreens: null, collectionComplete: false, stopReason: null, ...overrides }
}

function acceptedFixture(overrides: Record<string, unknown> = {}) {
  return { ...identity, targetCount: 1, tasks: [{ taskId, state: 'QUEUED', createdAt: null }],
    delivery: deliveryFixture(), ...overrides }
}

function durableRun(overrides: Record<string, unknown> = {}) {
  return { ...identity, taskCount: 1, summary: { SUCCEEDED: 1 }, allTerminal: true,
    tasks: [{ taskId, state: 'SUCCEEDED' }], delivery: deliveryFixture(), ...overrides }
}

beforeEach(() => {
  config.configured = true
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const respond = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers }))

/** W1 实测列表行视图（camelCase，无 raw）。 */
function orderFixture(overrides: Partial<OrderRow> = {}): OrderRow {
  return {
    id: '018f1a2b-0000-7000-8000-000000000001',
    deviceId: 'dev-alpha-0001',
    platform: 'xianyu',
    direction: 'SOLD',
    orderKey: 'XY202609141234',
    itemTitle: '闲置 Kindle Paperwhite',
    buyerName: '买家小王',
    amountCents: 12345,
    statusText: '待发货',
    occurredAt: '2026-09-14T10:00:00.000Z',
    createdAt: '2026-09-14T10:01:00.000Z',
    updatedAt: '2026-09-14T10:01:00.000Z',
    ...overrides,
  }
}

/** W1 实测详情视图：列表行 + raw。 */
function orderDetailFixture(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    ...orderFixture(),
    raw: { title: '闲置 Kindle Paperwhite ¥123.45', desc: '九成新' },
    ...overrides,
  }
}

describe('orders helpers', () => {
  it('converts integer cents to yuan display without float drift', () => {
    expect(formatOrderAmount(12345)).toBe('¥123.45')
    expect(formatOrderAmount(5)).toBe('¥0.05')
    expect(formatOrderAmount(0)).toBe('¥0.00')
    expect(formatOrderAmount(100)).toBe('¥1.00')
    expect(formatOrderAmount(-150)).toBe('-¥1.50')
    expect(formatOrderAmount(null)).toBe('—')
    expect(formatOrderAmount(undefined)).toBe('—')
  })

  it('localizes occurred_at and keeps unknown or missing times as placeholders', () => {
    expect(formatOrderTime(null)).toBe('—')
    expect(formatOrderTime(undefined)).toBe('—')
    expect(formatOrderTime('not-a-date')).toBe('—')
    const label = formatOrderTime('2026-09-14T10:00:00.000Z')
    expect(label).not.toBe('—')
    expect(label).toMatch(/2026/)
  })

  it('labels and validates the two frozen directions', () => {
    expect(isOrderDirection('SOLD')).toBe(true)
    expect(isOrderDirection('BOUGHT')).toBe(true)
    expect(isOrderDirection('REFUND')).toBe(false)
    expect(orderDirectionLabel('SOLD')).toBe('我卖出的')
    expect(orderDirectionLabel('BOUGHT')).toBe('我买到的')
    expect(orderDirectionLabel('other')).toBe('other')
  })
})

describe('orders list api wiring', () => {
  it('assembles snake_case query params and omits empty filters', async () => {
    respond({ items: [orderFixture()], total: 1 })
    const result = await listOrders()
    expect(result.items).toHaveLength(1)
    expect(result.total).toBe(1)
    expect(fetcher.mock.calls[0][0]).toBe('http://control.test/api/v1/orders')

    respond({ items: [], total: 42 })
    await listOrders({
      deviceId: 'dev-alpha-0001',
      direction: 'SOLD',
      statusText: '待发货',
      limit: 20,
      offset: 40,
    })
    expect(fetcher.mock.calls[1][0]).toBe(
      'http://control.test/api/v1/orders?device_id=dev-alpha-0001&direction=SOLD&status_text=%E5%BE%85%E5%8F%91%E8%B4%A7&limit=20&offset=40',
    )
    const init = fetcher.mock.calls[1][1] as RequestInit
    expect(init.method).toBe('GET')
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).get('X-Tenant-Id')).toBe('test-tenant')
    expect(init.body).toBeUndefined()
  })

  it('falls back to the item count when total is missing', async () => {
    respond({ items: [orderFixture()] })
    const result = await listOrders()
    expect(result.total).toBe(1)
    expect(result.items[0]?.orderKey).toBe('XY202609141234')
  })

  it('fails closed with the error message when the backend is unreachable or errors', async () => {
    respond({ detail: 'device not visible' }, 500)
    const error = await listOrders({ deviceId: 'dev-alpha-0001' }).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(OrdersApiError)
    expect((error as OrdersApiError).status).toBe(500)
    expect((error as OrdersApiError).message).toContain('device not visible')
    expect((error as OrdersApiError).message).toContain('HTTP 500')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('fails closed before any request when Control API is unconfigured', async () => {
    config.configured = false
    await expect(listOrders()).rejects.toThrow('未配置 Control API')
    expect(fetcher).not.toHaveBeenCalled()
  })
})

describe('order detail api wiring', () => {
  it('fetches a single order by id with the raw snapshot', async () => {
    const detail = orderDetailFixture()
    respond(detail)
    const result = await fetchOrder(detail.id)
    expect(result.orderKey).toBe('XY202609141234')
    expect(result.raw).toEqual({ title: '闲置 Kindle Paperwhite ¥123.45', desc: '九成新' })
    expect(fetcher.mock.calls[0][0]).toBe(`http://control.test/api/v1/orders/${detail.id}`)
    expect((fetcher.mock.calls[0][1] as RequestInit).method).toBe('GET')
  })

  it('maps 404 to the not-found semantics', async () => {
    respond({ detail: 'order was not found' }, 404)
    const error = await fetchOrder('018f1a2b-0000-7000-8000-00000000dead').catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(OrdersApiError)
    expect((error as OrdersApiError).status).toBe(404)
    expect((error as OrdersApiError).message).toContain('订单不存在或已被删除')
  })

  it('flattens FastAPI 422 field problems into a readable message', async () => {
    respond({ detail: [{ type: 'greater_than', loc: ['query', 'limit'], msg: 'Input should be greater than 0' }] }, 422)
    const error = await listOrders({ limit: 0 }).catch((cause: unknown) => cause)
    expect((error as OrdersApiError).status).toBe(422)
    expect((error as OrdersApiError).message).toContain('Input should be greater than 0')
    expect((error as OrdersApiError).message).toContain('HTTP 422')
  })
})

describe('xianyu order collect api wiring (contract §6, W1 afca8c2 wire format)', () => {
  it('posts the collect intent with an Idempotency-Key header and snake_case body', async () => {
    respond(
      {
        runId,
        deviceId: 'dev-alpha-0001',
        direction: 'SOLD',
        maxRows: 10,
        commandType: 'xianyu.collect_orders.steps.v1',
        targetCount: 1,
        taskIds: [taskId],
        tasks: [{ taskId, state: 'QUEUED', createdAt: '2026-09-15T10:00:00.000Z' }],
      },
      201,
      { 'Idempotency-Replayed': 'false' },
    )
    const result = await startXianyuOrderCollect(
      { deviceId: 'dev-alpha-0001', direction: 'SOLD', maxRows: 10 },
      'idem-key-1',
    )
    expect(result.runId).toBe(runId)
    expect(result.taskIds).toEqual([taskId])
    expect(result.tasks[0]?.state).toBe('QUEUED')
    expect(result.idempotencyReplayed).toBe(false)
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/xianyu/orders:collect')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Idempotency-Key')).toBe('idem-key-1')
    expect(JSON.parse(String(init.body))).toEqual({ device_id: 'dev-alpha-0001', direction: 'SOLD', max_rows: 10 })
  })

  it('reports idempotent replays via the Idempotency-Replayed header', async () => {
    respond(
      {
        runId,
        deviceId: 'dev-alpha-0001',
        direction: 'SOLD',
        maxRows: 10,
        commandType: 'xianyu.collect_orders.steps.v1',
        targetCount: 1,
        taskIds: [taskId],
        tasks: [{ taskId, state: 'RUNNING', createdAt: '2026-09-15T10:00:00.000Z' }],
      },
      200,
      { 'Idempotency-Replayed': 'true' },
    )
    const result = await startXianyuOrderCollect(
      { deviceId: 'dev-alpha-0001', direction: 'SOLD', maxRows: 10 },
      'idem-key-1',
    )
    expect(result.idempotencyReplayed).toBe(true)
    expect(result.runId).toBe(runId)
  })

  it('reads the aggregated run state by run_id (camelCase view with tasks)', async () => {
    respond({
      runId,
      deviceId: 'dev-alpha-0001',
      direction: 'SOLD',
      maxRows: 10,
      commandType: 'xianyu.collect_orders.steps.v1',
      taskCount: 1,
      summary: { SUCCEEDED: 1 },
      allTerminal: true,
      tasks: [{
        taskId,
        state: 'SUCCEEDED',
        runnerStatus: 'SUCCEEDED',
        errorCode: null,
        stallReason: null,
        createdAt: '2026-09-15T10:00:00.000Z',
        completedAt: '2026-09-15T10:02:00.000Z',
      }],
    })
    const run = await fetchXianyuOrderRun(runId)
    expect(run.runId).toBe(runId)
    expect(run.taskCount).toBe(1)
    expect(run.allTerminal).toBe(true)
    expect(run.tasks[0]?.state).toBe('SUCCEEDED')
    expect(run.tasks[0]?.runnerStatus).toBe('SUCCEEDED')
    expect(fetcher.mock.calls[0][0]).toBe(`http://control.test/api/v1/xianyu/orders/runs/${runId}`)
    expect((fetcher.mock.calls[0][1] as RequestInit).method).toBe('GET')
  })

  it('sends screens only when provided (slice2 §2: omitted = backend default 1 / v1 compatible)', async () => {
    respond(
      {
        runId,
        deviceId: 'dev-alpha-0001',
        direction: 'SOLD',
        maxRows: 10,
        commandType: 'xianyu.collect_orders.steps.v2',
        targetCount: 1,
        taskIds: [taskId],
        tasks: [{ taskId, state: 'QUEUED', createdAt: '2026-09-15T10:00:00.000Z' }],
      },
      201,
      { 'Idempotency-Replayed': 'false' },
    )
    await startXianyuOrderCollect(
      { deviceId: 'dev-alpha-0001', direction: 'SOLD', maxRows: 10, screens: 3 },
      'idem-key-2',
    )
    expect(JSON.parse(String((fetcher.mock.calls[0][1] as RequestInit).body))).toEqual({
      device_id: 'dev-alpha-0001',
      direction: 'SOLD',
      max_rows: 10,
      screens: 3,
    })

    respond(
      {
        runId,
        deviceId: 'dev-alpha-0001',
        direction: 'SOLD',
        maxRows: 10,
        commandType: 'xianyu.collect_orders.steps.v1',
        targetCount: 1,
        taskIds: [taskId],
        tasks: [{ taskId, state: 'QUEUED', createdAt: '2026-09-15T10:00:00.000Z' }],
      },
      201,
      { 'Idempotency-Replayed': 'false' },
    )
    await startXianyuOrderCollect(
      { deviceId: 'dev-alpha-0001', direction: 'SOLD', maxRows: 10 },
      'idem-key-3',
    )
    // 缺省不携带 screens 字段（等价后端默认 1）
    expect(JSON.parse(String((fetcher.mock.calls[1][1] as RequestInit).body))).toEqual({
      device_id: 'dev-alpha-0001',
      direction: 'SOLD',
      max_rows: 10,
    })
  })

  it('classifies run terminality against the backend TERMINAL_BUSINESS vocabulary', () => {
    const task = (state: string | null): XianyuOrderRunTask => ({
      taskId: `task-${state ?? 'null'}`,
      state,
      runnerStatus: null,
      errorCode: null,
      stallReason: null,
      createdAt: null,
      completedAt: null,
    })
    const run = (states: (string | null)[], allTerminal?: boolean) => ({
      ...(allTerminal === undefined ? {} : { allTerminal }),
      tasks: states.map(task),
    })
    // 后端 xianyu_orders.py TERMINAL_BUSINESS：SUCCEEDED/FAILED/CANCELLED/EXPIRED
    expect(isXianyuOrderRunTerminal(run(['SUCCEEDED'], true))).toBe(true)
    expect(isXianyuOrderRunTerminal(run(['FAILED'], true))).toBe(true)
    expect(isXianyuOrderRunTerminal(run(['CANCELLED'], true))).toBe(true)
    expect(isXianyuOrderRunTerminal(run(['EXPIRED'], true))).toBe(true)
    // 非终态词汇
    expect(isXianyuOrderRunTerminal(run(['QUEUED'], false))).toBe(false)
    expect(isXianyuOrderRunTerminal(run(['RUNNING'], false))).toBe(false)
    expect(isXianyuOrderRunTerminal(run([null], false))).toBe(false)
    expect(isXianyuOrderRunTerminal(run(['SUCCEEDED', 'RUNNING'], false))).toBe(false)
    // allTerminal 缺失时按 tasks 词汇兜底
    expect(isXianyuOrderRunTerminal(run(['SUCCEEDED', 'FAILED']))).toBe(true)
    expect(isXianyuOrderRunTerminal(run(['RUNNING']))).toBe(false)
    expect(isXianyuOrderRunTerminal(run([]))).toBe(false)
  })
})

describe('order-delivery/1 API gates', () => {
  it('opts in explicitly while retaining the existing one-screen request shape', async () => {
    respond(acceptedFixture(), 201)
    const result = await startXianyuOrderCollect(durableInput, 'durable-key')
    expect(result.delivery).toEqual(deliveryFixture())
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/xianyu/orders:collect')
    expect(JSON.parse(String(init.body))).toEqual({
      device_id: durableInput.deviceId, direction: 'SOLD', max_rows: 10,
      orderDeliveryProtocol: ORDER_DELIVERY_PROTOCOL,
    })
    expect(new Headers(init.headers).get('Idempotency-Key')).toBe('durable-key')
    expect(new Headers(init.headers).get('Accept')).toBe('application/json')
    expect(init.credentials).toBe('same-origin')
  })

  it.each([409, 403, 422, 429, 503])('surfaces HTTP %s without legacy fallback or automatic POST retry', async (status) => {
    respond({ detail: 'ACCOUNT_BINDING_REQUIRED' }, status)
    await expect(startXianyuOrderCollect(durableInput, 'retained-key'))
      .rejects.toMatchObject({ status, message: `ACCOUNT_BINDING_REQUIRED（HTTP ${status}）` })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('keeps exact body/key on an explicit retry after transport ambiguity', async () => {
    fetcher.mockRejectedValueOnce(new TypeError('connection lost'))
    await expect(startXianyuOrderCollect(durableInput, 'retained-key')).rejects.toThrow('connection lost')
    respond(acceptedFixture(), 200, { 'Idempotency-Replayed': 'true' })
    const result = await startXianyuOrderCollect(durableInput, 'retained-key')
    expect(result.idempotencyReplayed).toBe(true)
    const first = fetcher.mock.calls[0]![1] as RequestInit
    const second = fetcher.mock.calls[1]![1] as RequestInit
    expect(first.body).toBe(second.body)
    expect(new Headers(first.headers).get('Idempotency-Key')).toBe(new Headers(second.headers).get('Idempotency-Key'))
  })

  it.each([
    { runId: '' }, { runId: 'bad' }, { runId: 123 }, { runId: `${runId} ` },
    { tasks: [] }, { tasks: [{ taskId: '', state: 'QUEUED' }], taskIds: [''] },
    { taskIds: [] }, { taskIds: [runId] }, { targetCount: 0 },
    { tasks: [{ taskId, state: 'QUEUED' }, { taskId, state: 'QUEUED' }], taskIds: [taskId, taskId], targetCount: 2 },
    { deviceId: 'different-device' }, { direction: 'BOUGHT' }, { maxRows: 5 }, { screens: 3 },
  ])('rejects malformed or mismatched creation identity: %j', async (overrides) => {
    respond(acceptedFixture(overrides), 201)
    await expect(startXianyuOrderCollect(durableInput, 'retained-key'))
      .rejects.toMatchObject({ acceptedIdentity: undefined, message: expect.stringContaining('runId/taskId') })
  })

  it.each([null, [], 'not-an-object'].map((payload) => ({ payload })))('rejects malformed successful body: $payload', async ({ payload }) => {
    respond(payload, 200)
    await expect(startXianyuOrderCollect(durableInput, 'retained-key')).rejects.toBeInstanceOf(OrdersProtocolError)
  })

  it.each([
    undefined, null, {}, deliveryFixture({ protocolVersion: null, state: 'LEGACY_UNVERIFIED' }),
    { ...deliveryFixture(), protocolVersion: 'order-delivery/2' },
    deliveryFixture({ state: 'SYNCED' }),
  ].map((delivery) => ({ delivery })))('retains accepted identity but rejects incompatible delivery: $delivery', async ({ delivery }) => {
    respond(acceptedFixture({ delivery }), 201)
    await expect(startXianyuOrderCollect(durableInput, 'retained-key')).rejects.toMatchObject({
      acceptedIdentity: identity, message: '采集已受理，但同步协议响应无效',
    })
  })

  it('accepts terminal task success with delivery still pending', async () => {
    respond(durableRun())
    const result = await fetchXianyuOrderRun(runId, { expected: identity, durable: true, maxScreens: 1 })
    expect(result.allTerminal).toBe(true)
    expect(result.delivery?.state).toBe('PENDING')
  })

  it('accepts actual early-stop total instead of requiring the requested maximum', async () => {
    respond(durableRun({ delivery: deliveryFixture({
      state: 'SYNCED', collectionComplete: true, receivedScreens: [1], expectedScreens: 1, stopReason: 'STOP_EMPTY_PAGE',
    }) }))
    const result = await fetchXianyuOrderRun(runId, { expected: identity, durable: true, maxScreens: 3 })
    expect(result.delivery?.expectedScreens).toBe(1)
    expect(result.delivery?.state).toBe('SYNCED')
  })

  it.each([
    { collectionComplete: false }, { expectedScreens: null }, { expectedScreens: 0 },
    { receivedScreens: [] }, { receivedScreens: [2] }, { receivedScreens: [1, 1] },
    { expectedScreens: 3, receivedScreens: [1, 3] }, { expectedScreens: 4, receivedScreens: [1, 2, 3, 4] },
  ])('rejects SYNCED without valid completion and contiguous receipt proof: %j', async (delta) => {
    respond(durableRun({ delivery: { ...deliveryFixture({
      state: 'SYNCED', receivedScreens: [1], expectedScreens: 1, collectionComplete: true, stopReason: 'PLAN_FINISHED',
    }), ...delta } }))
    await expect(fetchXianyuOrderRun(runId, { durable: true })).rejects.toBeInstanceOf(OrdersProtocolError)
  })

  it.each(['FAILED', 'CANCELLED', 'EXPIRED', 'RECONCILING', 'RUNNING'])('rejects SYNCED for task %s', async (state) => {
    respond(durableRun({ tasks: [{ taskId, state }], delivery: deliveryFixture({
      state: 'SYNCED', receivedScreens: [1], expectedScreens: 1, collectionComplete: true, stopReason: 'PLAN_FINISHED',
    }) }))
    await expect(fetchXianyuOrderRun(runId, { durable: true })).rejects.toBeInstanceOf(OrdersProtocolError)
  })

  it.each([
    'TASK_FAILED', 'TASK_CANCELLED', 'TASK_EXPIRED', 'COLLECTION_RECONCILING',
    'MOBILE_BINDING_CHANGED', 'ACCOUNT_BINDING_CHANGED', 'PAYLOAD_CONFLICT',
  ])('preserves explicit BLOCKED reason %s independently of task success', async (stopReason) => {
    respond(durableRun({ delivery: deliveryFixture({ state: 'BLOCKED', stopReason }) }))
    const result = await fetchXianyuOrderRun(runId, { durable: true })
    expect(result.delivery?.state).toBe('BLOCKED')
    expect(result.delivery?.stopReason).toBe(stopReason)
  })

  it.each([
    { runId: taskId }, { deviceId: 'device-other' }, { direction: 'BOUGHT' }, { maxRows: 5 },
    { tasks: [{ taskId: runId, state: 'SUCCEEDED' }] }, { tasks: [], taskCount: 0 }, { taskCount: 2 },
  ])('rejects a run response for another accepted identity: %j', async (overrides) => {
    respond(durableRun(overrides))
    await expect(fetchXianyuOrderRun(runId, { expected: identity, durable: true })).rejects.toBeInstanceOf(OrdersProtocolError)
  })

  it('never upgrades legacy success into delivery success and rejects downgrade for negotiated runs', async () => {
    const legacy = deliveryFixture({ protocolVersion: null, state: 'LEGACY_UNVERIFIED' })
    respond(durableRun({ delivery: legacy }))
    const result = await fetchXianyuOrderRun(runId)
    expect(deliveryLabel(result.delivery)).toBe('旧任务：同步未核验')
    respond(durableRun({ delivery: legacy }))
    await expect(fetchXianyuOrderRun(runId, { durable: true })).rejects.toBeInstanceOf(OrdersProtocolError)
    respond(durableRun({ delivery: undefined }))
    await expect(fetchXianyuOrderRun(runId, { durable: true })).rejects.toBeInstanceOf(OrdersProtocolError)
    expect(deliveryLabel(undefined)).toBe('同步状态未确认')
  })

  it('passes a read AbortSignal without creating or retrying a task', async () => {
    const controller = new AbortController()
    respond(durableRun())
    await fetchXianyuOrderRun(runId, { expected: identity, durable: true, signal: controller.signal })
    const init = fetcher.mock.calls[0]![1] as RequestInit
    expect(init.method).toBe('GET')
    expect(init.signal).toBe(controller.signal)
    expect(init.body).toBeUndefined()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('rejects delivery with invalid field types or a missing blocked reason', () => {
    for (const delta of [
      { collectionComplete: 'true' }, { expectedScreens: '1' }, { receivedScreens: null },
      { state: 'BLOCKED', stopReason: null }, { state: 'UNKNOWN' }, { stopReason: {} },
    ]) {
      expect(validOrderDelivery({ ...deliveryFixture(), ...delta }, [{ state: 'SUCCEEDED' }], true)).toBe(false)
    }
  })
})
