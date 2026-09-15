import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchOrder,
  fetchXianyuOrderRun,
  formatOrderAmount,
  formatOrderTime,
  isOrderDirection,
  listOrders,
  orderDirectionLabel,
  OrdersApiError,
  startXianyuOrderCollect,
  type OrderDetail,
  type OrderRow,
} from '@/api/orders'

const config = vi.hoisted(() => ({ configured: true }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return config.configured },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({ 'X-Tenant-Id': 'test-tenant', 'X-User-Id': 'test-operator' }),
  operationsMockEnabled: false,
  createControlApiClient: () => ({}),
}))

const fetcher = vi.fn()

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
        runId: '018f-run-0001',
        deviceId: 'dev-alpha-0001',
        direction: 'SOLD',
        maxRows: 10,
        commandType: 'xianyu.collect_orders.steps.v1',
        targetCount: 1,
        taskIds: ['task-0001'],
        tasks: [{ taskId: 'task-0001', state: 'QUEUED', createdAt: '2026-09-15T10:00:00.000Z' }],
      },
      201,
      { 'Idempotency-Replayed': 'false' },
    )
    const result = await startXianyuOrderCollect(
      { deviceId: 'dev-alpha-0001', direction: 'SOLD', maxRows: 10 },
      'idem-key-1',
    )
    expect(result.runId).toBe('018f-run-0001')
    expect(result.taskIds).toEqual(['task-0001'])
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
        runId: '018f-run-0001',
        deviceId: 'dev-alpha-0001',
        direction: 'SOLD',
        maxRows: 10,
        commandType: 'xianyu.collect_orders.steps.v1',
        targetCount: 1,
        taskIds: ['task-0001'],
        tasks: [{ taskId: 'task-0001', state: 'RUNNING', createdAt: '2026-09-15T10:00:00.000Z' }],
      },
      200,
      { 'Idempotency-Replayed': 'true' },
    )
    const result = await startXianyuOrderCollect(
      { deviceId: 'dev-alpha-0001', direction: 'SOLD', maxRows: 10 },
      'idem-key-1',
    )
    expect(result.idempotencyReplayed).toBe(true)
    expect(result.runId).toBe('018f-run-0001')
  })

  it('reads the aggregated run state by run_id (camelCase view with tasks)', async () => {
    respond({
      runId: '018f-run-0001',
      deviceId: 'dev-alpha-0001',
      direction: 'SOLD',
      maxRows: 10,
      commandType: 'xianyu.collect_orders.steps.v1',
      taskCount: 1,
      summary: { SUCCEEDED: 1 },
      allTerminal: true,
      tasks: [{
        taskId: 'task-0001',
        state: 'SUCCEEDED',
        runnerStatus: 'SUCCEEDED',
        errorCode: null,
        stallReason: null,
        createdAt: '2026-09-15T10:00:00.000Z',
        completedAt: '2026-09-15T10:02:00.000Z',
      }],
    })
    const run = await fetchXianyuOrderRun('018f-run-0001')
    expect(run.runId).toBe('018f-run-0001')
    expect(run.taskCount).toBe(1)
    expect(run.allTerminal).toBe(true)
    expect(run.tasks[0]?.state).toBe('SUCCEEDED')
    expect(run.tasks[0]?.runnerStatus).toBe('SUCCEEDED')
    expect(fetcher.mock.calls[0][0]).toBe('http://control.test/api/v1/xianyu/orders/runs/018f-run-0001')
    expect((fetcher.mock.calls[0][1] as RequestInit).method).toBe('GET')
  })
})
