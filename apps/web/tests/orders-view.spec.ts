import { fireEvent, render as renderView, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { useSessionStore } from '@/stores/session'
import { ORDER_DELIVERY_PROTOCOL, type OrderDelivery } from '@/features/orders/delivery'
import {
  fetchOrder,
  fetchXianyuOrderRun,
  listOrders,
  OrdersApiError,
  OrdersProtocolError,
  startXianyuOrderCollect,
  type OrderDetail,
  type OrderRow,
  type XianyuOrderCollectResult,
  type XianyuOrderRunTask,
  type XianyuOrderRunView,
} from '@/api/orders'
import OrdersView from '@/views/OrdersView.vue'

const runId = '018f1a2b-0000-7000-8000-000000000010'
const taskId = '018f1a2b-0000-7000-8000-000000000020'
const runId2 = '018f1a2b-0000-7000-8000-000000000011'
const taskId2 = '018f1a2b-0000-7000-8000-000000000021'

function render(component: typeof OrdersView, roles = ['device_operator']) {
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.applySession({ userId: 'operator', tenantId: 'tenant', roles, mfa: true, requestId: 'fixture' })
  return { ...renderView(component, { global: { plugins: [pinia] } }), session }
}

function deliveryFixture(overrides: Partial<OrderDelivery> = {}): OrderDelivery {
  return { protocolVersion: ORDER_DELIVERY_PROTOCOL, state: 'PENDING', receivedScreens: [],
    expectedScreens: null, collectionComplete: false, stopReason: null, ...overrides }
}

function syncedDelivery(): OrderDelivery {
  return deliveryFixture({ state: 'SYNCED', receivedScreens: [1], expectedScreens: 1,
    collectionComplete: true, stopReason: 'PLAN_FINISHED' })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  operationsMockEnabled: false,
  createControlApiClient: () => ({
    devices: vi.fn(async () => [
      { id: 'dev-alpha-0001', logical_name: '一加 9R', state: 'REGISTERED' },
      { id: 'dev-beta-0002', logical_name: 'Phone B', state: 'REGISTERED' },
    ]),
  }),
}))

vi.mock('@/api/runtime-mode', () => ({
  controlApiConfigured: true,
  operationsMockEnabled: false,
  runtimeDataMode: 'api',
  localBusinessDataAllowed: () => false,
  requireApiMode: () => undefined,
  requireWritableApi: () => undefined,
}))

vi.mock('@/api/orders', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/orders')>()
  return {
    ...actual,
    listOrders: vi.fn(),
    fetchOrder: vi.fn(),
    startXianyuOrderCollect: vi.fn(),
    fetchXianyuOrderRun: vi.fn(),
  }
})

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

/** 详情视图 = 列表行 + raw（GET /api/v1/orders/{id}）。 */
function orderDetailFixture(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    ...orderFixture(),
    raw: { title: '闲置 Kindle Paperwhite ¥123.45', desc: '九成新' },
    ...overrides,
  }
}

function pageOf(count: number, startIndex = 0): OrderRow[] {
  return Array.from({ length: count }, (_, i) => orderFixture({
    id: `018f1a2b-0000-7000-8000-${String(startIndex + i).padStart(12, '0')}`,
    orderKey: `XY20260914${String(1000 + startIndex + i)}`,
  }))
}

/** W1 实测 collect 响应（契约 §6，201 新建形状）。 */
function collectResultFixture(overrides: Partial<XianyuOrderCollectResult> = {}): XianyuOrderCollectResult {
  return {
    runId,
    deviceId: 'dev-alpha-0001',
    direction: 'SOLD',
    maxRows: 10,
    commandType: 'xianyu.collect_orders.steps.v1',
    targetCount: 1,
    taskIds: [taskId],
    tasks: [{ taskId, state: 'QUEUED', createdAt: '2026-09-15T10:00:00.000Z' }],
    delivery: deliveryFixture(),
    idempotencyReplayed: false,
    ...overrides,
  }
}

function runTaskFixture(overrides: Partial<XianyuOrderRunTask> = {}): XianyuOrderRunTask {
  return {
    taskId,
    state: 'SUCCEEDED',
    runnerStatus: 'SUCCEEDED',
    errorCode: null,
    stallReason: null,
    createdAt: '2026-09-15T10:00:00.000Z',
    completedAt: '2026-09-15T10:02:00.000Z',
    ...overrides,
  }
}

/** W1 实测 run 聚合视图（GET /api/v1/xianyu/orders/runs/{run_id}）。 */
function runFixture(tasks: XianyuOrderRunTask[], overrides: Partial<XianyuOrderRunView> = {}): XianyuOrderRunView {
  return {
    runId,
    deviceId: 'dev-alpha-0001',
    direction: 'SOLD',
    maxRows: 10,
    commandType: 'xianyu.collect_orders.steps.v1',
    taskCount: tasks.length,
    summary: {},
    allTerminal: tasks.length > 0 && tasks.every((task) => task.state === 'SUCCEEDED'),
    tasks,
    delivery: deliveryFixture(),
    ...overrides,
  }
}

async function readyToCollect(roles = ['device_operator']) {
  const view = render(OrdersView, roles)
  await flushPromises()
  await fireEvent.update(screen.getByLabelText('设备'), 'dev-alpha-0001')
  await flushPromises()
  vi.useFakeTimers()
  return view
}

async function clickCollect() {
  await fireEvent.click(screen.getByRole('button', { name: '开始采集' }))
  await vi.advanceTimersByTimeAsync(0)
}

describe('OrdersView', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })
  beforeEach(() => {
    vi.mocked(listOrders).mockReset().mockResolvedValue({ items: [orderFixture()], total: 1 })
    vi.mocked(fetchOrder).mockReset().mockImplementation(async (id: string) => orderDetailFixture({ id }))
    vi.mocked(startXianyuOrderCollect).mockReset()
    vi.mocked(fetchXianyuOrderRun).mockReset()
  })

  it('renders order rows with formatted amounts, direction chips and status text', async () => {
    render(OrdersView)
    expect(await screen.findByText('XY202609141234')).toBeTruthy()
    expect(screen.getByText('闲置 Kindle Paperwhite')).toBeTruthy()
    expect(screen.getByText('买家小王')).toBeTruthy()
    expect(screen.getByText('¥123.45')).toBeTruthy()
    expect(screen.getByText('待发货')).toBeTruthy()
    expect(screen.getByText('我卖出的', { selector: '.orders-direction' })).toBeTruthy()
    expect(screen.queryByText(/暂无订单/)).toBeNull()
    expect(screen.queryByText(/加载失败/)).toBeNull()
  })

  it('fails closed on backend errors: shows the error and never fake data or the empty state', async () => {
    vi.mocked(listOrders).mockRejectedValueOnce(new OrdersApiError(503, '订单服务不可达（HTTP 503）'))
    render(OrdersView)
    await waitFor(() => expect(screen.getByText(/订单服务不可达/)).toBeTruthy())
    expect(screen.queryByText('XY202609141234')).toBeNull()
    expect(screen.queryByText(/暂无订单/)).toBeNull()
    expect(screen.queryByText('¥123.45')).toBeNull()
    // 错误态不渲染「已加载 / 共」分页统计
    expect(screen.queryByText(/已加载/)).toBeNull()
  })

  it('shows the honest empty state only after a successful empty load', async () => {
    vi.mocked(listOrders).mockResolvedValueOnce({ items: [], total: 0 })
    render(OrdersView)
    await waitFor(() => expect(screen.getByText(/暂无订单。手机采集任务上报后会出现在这里。/)).toBeTruthy())
    expect(screen.queryByText(/加载失败/)).toBeNull()
  })

  it('expands the fetched detail snapshot (raw via the detail endpoint) on click and collapses on second click', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.click(screen.getByText('XY202609141234'))
    expect(await screen.findByText(/行原文快照/)).toBeTruthy()
    expect(screen.getByText(/闲置 Kindle Paperwhite ¥123\.45/)).toBeTruthy()
    expect(screen.getByText('dev-alpha-0001')).toBeTruthy()
    expect(screen.getByText('待发货', { selector: '.orders-fields dd' })).toBeTruthy()
    expect(vi.mocked(fetchOrder)).toHaveBeenCalledWith('018f1a2b-0000-7000-8000-000000000001')
    await fireEvent.click(screen.getAllByText('买家小王')[0])
    expect(screen.queryByText(/行原文快照/)).toBeNull()
  })

  it('fails closed inside the expanded detail when the detail fetch errors', async () => {
    vi.mocked(fetchOrder).mockRejectedValueOnce(new OrdersApiError(500, '订单详情加载失败（HTTP 500）'))
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.click(screen.getByText('XY202609141234'))
    await waitFor(() => expect(screen.getByText(/订单详情加载失败/)).toBeTruthy())
    expect(screen.queryByText(/行原文快照/)).toBeNull()
    // 行主体仍在，但 raw 区不渲染占位假数据
    expect(screen.getByText('买家小王')).toBeTruthy()
  })

  it('loads the next page with offset pagination when more rows exist', async () => {
    vi.mocked(listOrders)
      .mockResolvedValueOnce({ items: pageOf(20), total: 25 })
      .mockResolvedValueOnce({ items: pageOf(5, 20), total: 25 })
    render(OrdersView)
    await screen.findByText('XY202609141000')
    expect(screen.getByRole('button', { name: '加载更多' })).toBeTruthy()
    expect(screen.getByText(/已加载 20 \/ 共 25 条/)).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(screen.getByText(/已加载 25 \/ 共 25 条/)).toBeTruthy())
    expect(vi.mocked(listOrders)).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 20, offset: 20 }))
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('reloads from the first page when the direction filter changes', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.update(screen.getByLabelText('方向'), 'BOUGHT')
    await waitFor(() =>
      expect(vi.mocked(listOrders)).toHaveBeenLastCalledWith(expect.objectContaining({ direction: 'BOUGHT', offset: 0 })),
    )
  })

  it('disables the collect button with a hint until a concrete device is selected', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    const collect = screen.getByRole('button', { name: '开始采集' }) as HTMLButtonElement
    expect(collect.disabled).toBe(true)
    expect(screen.getByText(/请先在上方「设备」下拉选择具体设备/)).toBeTruthy()
    // 旧的禁用态说明已随入口启用移除
    expect(screen.queryByText(/待真机定位器验证后启用/)).toBeNull()
    expect(vi.mocked(startXianyuOrderCollect)).not.toHaveBeenCalled()
  })

  it('starts a collect run carrying the chosen direction and screens (screens=1 omitted)', async () => {
    vi.mocked(startXianyuOrderCollect)
      .mockResolvedValueOnce(collectResultFixture({ direction: 'BOUGHT' }))
      .mockResolvedValueOnce(collectResultFixture({ runId: runId2, taskIds: [taskId2],
        tasks: [{ taskId: taskId2, state: 'QUEUED', createdAt: null }], direction: 'BOUGHT' }))
    vi.mocked(fetchXianyuOrderRun).mockResolvedValue(runFixture([runTaskFixture()], { direction: 'BOUGHT', delivery: syncedDelivery() }))
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.update(screen.getByLabelText('设备'), 'dev-alpha-0001')
    await fireEvent.update(screen.getByLabelText('采集方向'), 'BOUGHT')
    await fireEvent.update(screen.getByLabelText('屏数'), '3')
    vi.useFakeTimers()
    try {
      await fireEvent.click(screen.getByRole('button', { name: '开始采集' }))
      await vi.advanceTimersByTimeAsync(0)
      expect(vi.mocked(startXianyuOrderCollect)).toHaveBeenCalledTimes(1)
      expect(vi.mocked(startXianyuOrderCollect)).toHaveBeenCalledWith(
        expect.objectContaining({ deviceId: 'dev-alpha-0001', direction: 'BOUGHT', maxRows: 10, screens: 3 }),
        expect.any(String),
      )
      // 第一轮轮询到终态收口，busy 解除
      await vi.advanceTimersByTimeAsync(2000)
      const button = screen.getByRole('button', { name: '新建采集' }) as HTMLButtonElement
      expect(button.disabled).toBe(false)
      // 屏数回到缺省 1：不发送 screens 字段（slice1 v1 入参兼容）
      await fireEvent.update(screen.getByLabelText('屏数'), '1')
      await fireEvent.click(button)
      await vi.advanceTimersByTimeAsync(0)
      expect(vi.mocked(startXianyuOrderCollect)).toHaveBeenCalledTimes(2)
      expect(vi.mocked(startXianyuOrderCollect).mock.calls[1][0]).toEqual({
        deviceId: 'dev-alpha-0001',
        direction: 'BOUGHT',
        maxRows: 10,
        orderDeliveryProtocol: ORDER_DELIVERY_PROTOCOL,
      })
      expect(vi.mocked(startXianyuOrderCollect).mock.calls[0]![1]).not.toBe(vi.mocked(startXianyuOrderCollect).mock.calls[1]![1])
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps polling after SUCCEEDED while PENDING, then refreshes the list only after SYNCED', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun)
      .mockResolvedValueOnce(runFixture([runTaskFixture()]))
      .mockResolvedValueOnce(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.update(screen.getByLabelText('设备'), 'dev-alpha-0001')
    const listCallsAfterLoad = vi.mocked(listOrders).mock.calls.length
    vi.useFakeTimers()
    try {
      await fireEvent.click(screen.getByRole('button', { name: '开始采集' }))
      // 提交 promise 落定后挂上第一个 2s 轮询
      await vi.advanceTimersByTimeAsync(0)
      await vi.advanceTimersByTimeAsync(2000)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenCalledTimes(1)
      expect(screen.getByText('采集步骤完成')).toBeTruthy()
      expect(screen.getByText('同步待确认')).toBeTruthy()
      expect(screen.getByText('已入库 0 屏 / 实际总屏数 待确认')).toBeTruthy()
      expect(vi.mocked(listOrders).mock.calls.length).toBe(listCallsAfterLoad)
      expect((screen.getByRole('button', { name: '新建采集' }) as HTMLButtonElement).disabled).toBe(true)
      await vi.advanceTimersByTimeAsync(4000)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenCalledTimes(2)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenLastCalledWith(runId, expect.objectContaining({ durable: true }))
      // 成功后自动刷新订单列表（比初始加载多一次）
      expect(vi.mocked(listOrders).mock.calls.length).toBeGreaterThan(listCallsAfterLoad)
      expect(screen.getByText('同步完成')).toBeTruthy()
      expect(screen.getByText('已入库 1 屏 / 实际总屏数 1')).toBeTruthy()
      expect(screen.getByText('SUCCEEDED', { selector: '.orders-task-state' })).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('polls to a FAILED run, surfaces the errorCode and never refreshes the list', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockResolvedValueOnce(
      // 显式 allTerminal：FAILED 也终态（runFixture 默认按全 SUCCEEDED 计算）
      runFixture([runTaskFixture({ state: 'FAILED', runnerStatus: 'FAILED', errorCode: 'STEP_TIMEOUT' })], {
        allTerminal: true, delivery: deliveryFixture({ state: 'BLOCKED', stopReason: 'TASK_FAILED' }),
      }),
    )
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.update(screen.getByLabelText('设备'), 'dev-alpha-0001')
    const listCallsAfterLoad = vi.mocked(listOrders).mock.calls.length
    vi.useFakeTimers()
    try {
      await fireEvent.click(screen.getByRole('button', { name: '开始采集' }))
      await vi.advanceTimersByTimeAsync(0)
      await vi.advanceTimersByTimeAsync(2000)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenCalledTimes(1)
      // fail-closed：错误段落与任务状态 chip 都如实展示错误码，不自动刷新列表
      expect(screen.getByText('采集未全部成功')).toBeTruthy()
      expect(screen.getByText('同步受阻')).toBeTruthy()
      expect(screen.getByText('采集任务失败（TASK_FAILED）')).toBeTruthy()
      expect(screen.getAllByText(/STEP_TIMEOUT/)).toHaveLength(1)
      expect(screen.getByText(/FAILED（STEP_TIMEOUT）/, { selector: '.orders-task-state' })).toBeTruthy()
      expect(vi.mocked(listOrders).mock.calls.length).toBe(listCallsAfterLoad)
      // 终态后不再继续轮询
      await vi.advanceTimersByTimeAsync(60000)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops polling when the view unmounts', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockResolvedValue(
      runFixture([runTaskFixture({ state: 'RUNNING' })], { allTerminal: false }),
    )
    const { unmount } = render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.update(screen.getByLabelText('设备'), 'dev-alpha-0001')
    vi.useFakeTimers()
    try {
      await fireEvent.click(screen.getByRole('button', { name: '开始采集' }))
      await vi.advanceTimersByTimeAsync(0)
      unmount()
      await vi.advanceTimersByTimeAsync(60000)
      expect(vi.mocked(fetchXianyuOrderRun)).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('loads device options into the filter dropdown', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    const deviceSelect = screen.getByLabelText('设备') as HTMLSelectElement
    const option = [...deviceSelect.querySelectorAll('option')].find((node) => node.value === 'dev-alpha-0001')
    expect(option?.textContent).toContain('一加 9R')
  })

  it('guards actual submit handlers from double clicks and never POSTs an accepted pending task again', async () => {
    const pending = deferred<XianyuOrderCollectResult>()
    vi.mocked(startXianyuOrderCollect).mockReturnValueOnce(pending.promise)
    await readyToCollect()
    const button = screen.getByRole('button', { name: '开始采集' })
    await Promise.all([fireEvent.click(button), fireEvent.click(button)])
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
    expect((screen.getByLabelText('屏数') as HTMLSelectElement).disabled).toBe(true)
    const retry = screen.getByRole('button', { name: '重试提交' }) as HTMLButtonElement
    retry.disabled = false
    await fireEvent.click(retry)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
    pending.resolve(collectResultFixture())
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.queryByRole('button', { name: '重试提交' })).toBeNull()
    const newRun = screen.getByRole('button', { name: '新建采集' }) as HTMLButtonElement
    newRun.disabled = false
    await fireEvent.click(newRun)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
  })

  it.each(['network', 'malformed'])('retries %s ambiguity with the SAME key and original selection snapshot', async (kind) => {
    vi.mocked(startXianyuOrderCollect)
      .mockRejectedValueOnce(kind === 'network' ? new TypeError('lost reply') : new OrdersProtocolError('task identity missing'))
      .mockResolvedValueOnce(collectResultFixture())
    await readyToCollect()
    await clickCollect()
    const first = vi.mocked(startXianyuOrderCollect).mock.calls[0]!
    expect(first[0].orderDeliveryProtocol).toBe(ORDER_DELIVERY_PROTOCOL)
    expect((screen.getByRole('button', { name: '开始采集' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.update(screen.getByLabelText('设备'), 'dev-beta-0002')
    // Programmatic changes cannot alter the request already snapshotted by the handler.
    await fireEvent.update(screen.getByLabelText('采集方向'), 'BOUGHT')
    await fireEvent.update(screen.getByLabelText('屏数'), '3')
    await fireEvent.click(screen.getByRole('button', { name: '重试提交' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(2)
    expect(vi.mocked(startXianyuOrderCollect).mock.calls[1]).toEqual(first)
    expect(screen.getByText('设备 dev-alpha-0001 · 我卖出的')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '重试提交' })).toBeNull()
  })

  it.each(['ORDER_DELIVERY_CAPABILITY_REQUIRED', 'ACCOUNT_BINDING_REQUIRED', 'ACCOUNT_BINDING_AMBIGUOUS'])(
    'shows explicit precreation 409 %s without legacy fallback',
    async (reason) => {
      vi.mocked(startXianyuOrderCollect).mockRejectedValueOnce(new OrdersApiError(409, reason))
      await readyToCollect()
      await clickCollect()
      expect(screen.getByRole('alert').textContent).toContain(reason)
      expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
      expect(vi.mocked(startXianyuOrderCollect).mock.calls[0]![0].orderDeliveryProtocol).toBe(ORDER_DELIVERY_PROTOCOL)
      expect(screen.queryByRole('button', { name: '重试提交' })).toBeNull()
      expect(screen.queryByText('同步完成')).toBeNull()
      expect((screen.getByRole('button', { name: '开始采集' }) as HTMLButtonElement).disabled).toBe(false)
      await vi.advanceTimersByTimeAsync(120000)
      expect(fetchXianyuOrderRun).not.toHaveBeenCalled()
      expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
    },
  )

  it('does not discard an ambiguous key when a later retry receives 409', async () => {
    vi.mocked(startXianyuOrderCollect).mockRejectedValueOnce(new TypeError('unknown'))
      .mockRejectedValueOnce(new OrdersApiError(409, 'conflict'))
      .mockResolvedValueOnce(collectResultFixture())
    await readyToCollect()
    await clickCollect()
    for (let retry = 0; retry < 2; retry++) {
      await fireEvent.click(screen.getByRole('button', { name: '重试提交' }))
      await vi.advanceTimersByTimeAsync(0)
    }
    const calls = vi.mocked(startXianyuOrderCollect).mock.calls
    expect(calls).toHaveLength(3)
    expect(calls[0]).toEqual(calls[1])
    expect(calls[1]).toEqual(calls[2])
  })

  it('keeps accepted IDs after invalid creation delivery and recovers only through manual GET', async () => {
    const acceptedIdentity = { runId, deviceId: 'dev-alpha-0001', direction: 'SOLD' as const, maxRows: 10, taskIds: [taskId] }
    vi.mocked(startXianyuOrderCollect).mockRejectedValueOnce(new OrdersProtocolError('采集已受理，但同步协议响应无效', acceptedIdentity))
    vi.mocked(fetchXianyuOrderRun).mockResolvedValueOnce(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    await readyToCollect()
    await clickCollect()
    expect(screen.getByText('同步状态未确认')).toBeTruthy()
    expect(screen.getByText(`run ${runId} · task ${taskId}`)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '重试提交' })).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '刷新同步状态' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchXianyuOrderRun).toHaveBeenCalledWith(runId, expect.objectContaining({
      expected: acceptedIdentity, durable: true, maxScreens: 1,
    }))
    expect(screen.getByText('同步完成')).toBeTruthy()
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
  })

  it('bounds pending polling with backoff independently of allTerminal and resumes with a manual GET', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockResolvedValue(runFixture([runTaskFixture()]))
    await readyToCollect()
    await clickCollect()
    await vi.advanceTimersByTimeAsync(1999)
    expect(fetchXianyuOrderRun).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3999)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(54000)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(7)
    expect(screen.getByText('自动查询已暂停，同步状态以上次查询为准。')).toBeTruthy()
    expect(screen.getByText('同步待确认')).toBeTruthy()
    expect(screen.getByText('采集步骤完成')).toBeTruthy()
    expect((screen.getByRole('button', { name: '新建采集' }) as HTMLButtonElement).disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(120000)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(7)
    vi.mocked(fetchXianyuOrderRun).mockResolvedValueOnce(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    await fireEvent.click(screen.getByRole('button', { name: '刷新同步状态' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(8)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
    expect(screen.getByText('同步完成')).toBeTruthy()
  })

  it('retries transient GET errors only within the same budget and clears the error after recovery', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun)
      .mockRejectedValueOnce(new OrdersApiError(503, 'temporarily unavailable'))
      .mockRejectedValueOnce(new OrdersApiError(429, 'rate limited'))
      .mockResolvedValueOnce(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    await readyToCollect()
    await clickCollect()
    await vi.advanceTimersByTimeAsync(2000)
    expect(screen.getByRole('alert').textContent).toBe('temporarily unavailable')
    expect(screen.queryByText('同步受阻')).toBeNull()
    await vi.advanceTimersByTimeAsync(4000)
    expect(screen.getByRole('alert').textContent).toBe('rate limited')
    await vi.advanceTimersByTimeAsync(8000)
    expect(screen.getByText('同步完成')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
  })

  it.each([new OrdersApiError(403, 'read denied'), new OrdersProtocolError('incompatible delivery')])(
    'stops automatic reads on permanent/protocol error without inventing BLOCKED or success',
    async (error) => {
      vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
      vi.mocked(fetchXianyuOrderRun).mockRejectedValueOnce(error)
      await readyToCollect()
      await clickCollect()
      await vi.advanceTimersByTimeAsync(60000)
      expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(1)
      expect(screen.getByRole('alert').textContent).toBe(error.message)
      expect(screen.queryByText('同步受阻')).toBeNull()
      expect(screen.queryByText('同步完成')).toBeNull()
      expect(screen.getByRole('button', { name: '刷新同步状态' })).toBeTruthy()
      expect(screen.queryByRole('button', { name: '重试提交' })).toBeNull()
    },
  )

  it('aborts a hung GET at the deadline and ignores its late success', async () => {
    const pending = deferred<XianyuOrderRunView>()
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockReturnValueOnce(pending.promise)
    await readyToCollect()
    await clickCollect()
    await vi.advanceTimersByTimeAsync(2000)
    const signal = vi.mocked(fetchXianyuOrderRun).mock.calls[0]![1]!.signal!
    expect(signal.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(58000)
    expect(signal.aborted).toBe(true)
    pending.resolve(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.queryByText('同步完成')).toBeNull()
    expect(screen.getByText('自动查询已暂停，同步状态以上次查询为准。')).toBeTruthy()
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(1)
  })

  it.each(['success', 'failure'])('ignores stale %s after manual GET supersedes an in-flight poll', async (outcome) => {
    const pending = deferred<XianyuOrderRunView>()
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(runFixture([runTaskFixture()], {
        delivery: deliveryFixture({ state: 'BLOCKED', stopReason: 'ACCOUNT_BINDING_CHANGED' }),
      }))
    await readyToCollect()
    await clickCollect()
    await vi.advanceTimersByTimeAsync(2000)
    const oldSignal = vi.mocked(fetchXianyuOrderRun).mock.calls[0]![1]!.signal!
    await fireEvent.click(screen.getByRole('button', { name: '刷新同步状态' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(oldSignal.aborted).toBe(true)
    expect(screen.getByText('账号绑定已变更（ACCOUNT_BINDING_CHANGED）')).toBeTruthy()
    if (outcome === 'success') pending.resolve(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    else pending.reject(new OrdersApiError(500, 'stale failure'))
    await vi.advanceTimersByTimeAsync(60000)
    expect(screen.getByText('同步受阻')).toBeTruthy()
    expect(screen.queryByText('同步完成')).toBeNull()
    expect(screen.queryByText('stale failure')).toBeNull()
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(2)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
  })

  it.each(['post', 'get'])('ignores an in-flight %s after unmount without starting more requests', async (kind) => {
    const post = deferred<XianyuOrderCollectResult>()
    const get = deferred<XianyuOrderRunView>()
    vi.mocked(startXianyuOrderCollect).mockImplementationOnce(() => kind === 'post' ? post.promise : Promise.resolve(collectResultFixture()))
    vi.mocked(fetchXianyuOrderRun).mockReturnValueOnce(get.promise)
    const view = await readyToCollect()
    await clickCollect()
    if (kind === 'get') await vi.advanceTimersByTimeAsync(2000)
    const priorListCalls = vi.mocked(listOrders).mock.calls.length
    view.unmount()
    post.resolve(collectResultFixture())
    get.resolve(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    await vi.advanceTimersByTimeAsync(120000)
    expect(fetchXianyuOrderRun).toHaveBeenCalledTimes(kind === 'get' ? 1 : 0)
    expect(listOrders).toHaveBeenCalledTimes(priorListCalls)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
  })

  it('enforces permission in submit and same-key retry handlers, while read-only GET remains available', async () => {
    const view = await readyToCollect(['viewer'])
    const create = screen.getByRole('button', { name: '开始采集' }) as HTMLButtonElement
    expect(create.disabled).toBe(true)
    create.disabled = false
    await fireEvent.click(create)
    expect(startXianyuOrderCollect).not.toHaveBeenCalled()
    view.session.applySession({ userId: 'operator', tenantId: 'tenant', roles: ['device_operator'], mfa: true, requestId: 'fixture' })
    vi.mocked(startXianyuOrderCollect).mockRejectedValueOnce(new TypeError('unknown'))
    await vi.advanceTimersByTimeAsync(0)
    await fireEvent.click(create)
    await vi.advanceTimersByTimeAsync(0)
    view.session.applySession({ userId: 'operator', tenantId: 'tenant', roles: ['viewer'], mfa: true, requestId: 'fixture' })
    await vi.advanceTimersByTimeAsync(0)
    const retry = screen.getByRole('button', { name: '重试提交' }) as HTMLButtonElement
    expect(retry.disabled).toBe(true)
    retry.disabled = false
    await fireEvent.click(retry)
    expect(startXianyuOrderCollect).toHaveBeenCalledTimes(1)
  })

  it('keeps delivery proof separate from a failed order-list refresh', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockResolvedValueOnce(runFixture([runTaskFixture()], { delivery: syncedDelivery() }))
    await readyToCollect()
    vi.mocked(listOrders).mockRejectedValueOnce(new OrdersApiError(503, 'list refresh unavailable'))
    await clickCollect()
    await vi.advanceTimersByTimeAsync(2000)
    expect(screen.getByText('同步完成')).toBeTruthy()
    expect(screen.getByText('list refresh unavailable')).toBeTruthy()
    expect(screen.queryByText(/已刷新订单列表/)).toBeNull()
  })

  it('fails closed when UUID generation is unavailable', async () => {
    await readyToCollect()
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => { throw new Error('unavailable') })
    await clickCollect()
    expect(screen.getByRole('alert').textContent).toBe('无法生成采集请求标识，未提交任务')
    expect(startXianyuOrderCollect).not.toHaveBeenCalled()
  })
})
