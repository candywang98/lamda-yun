import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchOrder,
  fetchXianyuOrderRun,
  listOrders,
  OrdersApiError,
  startXianyuOrderCollect,
  type OrderDetail,
  type OrderRow,
  type XianyuOrderCollectResult,
  type XianyuOrderRunTask,
  type XianyuOrderRunView,
} from '@/api/orders'
import OrdersView from '@/views/OrdersView.vue'

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  operationsMockEnabled: false,
  createControlApiClient: () => ({
    devices: vi.fn(async () => [{ id: 'dev-alpha-0001', logical_name: '一加 9R', state: 'REGISTERED' }]),
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
    runId: '018f-run-0001',
    deviceId: 'dev-alpha-0001',
    direction: 'SOLD',
    maxRows: 10,
    commandType: 'xianyu.collect_orders.steps.v1',
    targetCount: 1,
    taskIds: ['task-0001'],
    tasks: [{ taskId: 'task-0001', state: 'QUEUED', createdAt: '2026-09-15T10:00:00.000Z' }],
    idempotencyReplayed: false,
    ...overrides,
  }
}

function runTaskFixture(overrides: Partial<XianyuOrderRunTask> = {}): XianyuOrderRunTask {
  return {
    taskId: 'task-0001',
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
    runId: '018f-run-0001',
    deviceId: 'dev-alpha-0001',
    direction: 'SOLD',
    maxRows: 10,
    commandType: 'xianyu.collect_orders.steps.v1',
    taskCount: tasks.length,
    summary: {},
    allTerminal: tasks.length > 0 && tasks.every((task) => task.state === 'SUCCEEDED'),
    tasks,
    ...overrides,
  }
}

describe('OrdersView', () => {
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
      .mockResolvedValueOnce(collectResultFixture())
      .mockResolvedValueOnce(collectResultFixture({ runId: '018f-run-0002' }))
    // 轮询一律返回终态 SUCCEEDED，保证第一轮采集收口、按钮恢复可用
    vi.mocked(fetchXianyuOrderRun).mockResolvedValue(runFixture([runTaskFixture()]))
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
      const button = screen.getByRole('button', { name: '开始采集' }) as HTMLButtonElement
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
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('polls the run to a terminal SUCCEEDED state and refreshes the order list', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun)
      .mockResolvedValueOnce(runFixture([runTaskFixture({ state: 'RUNNING' })], { allTerminal: false }))
      .mockResolvedValueOnce(runFixture([runTaskFixture()]))
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
      // 第二次轮询读到终态 SUCCEEDED
      await vi.advanceTimersByTimeAsync(2000)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenCalledTimes(2)
      expect(vi.mocked(fetchXianyuOrderRun)).toHaveBeenLastCalledWith('018f-run-0001')
      // 成功后自动刷新订单列表（比初始加载多一次）
      expect(vi.mocked(listOrders).mock.calls.length).toBeGreaterThan(listCallsAfterLoad)
      expect(screen.getByText(/采集完成（1 个任务全部成功）/)).toBeTruthy()
      expect(screen.getByText('SUCCEEDED', { selector: '.orders-task-state' })).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('polls to a FAILED run, surfaces the errorCode and never refreshes the list', async () => {
    vi.mocked(startXianyuOrderCollect).mockResolvedValueOnce(collectResultFixture())
    vi.mocked(fetchXianyuOrderRun).mockResolvedValueOnce(
      // 显式 allTerminal：FAILED 也终态（runFixture 默认按全 SUCCEEDED 计算）
      runFixture([runTaskFixture({ state: 'FAILED', runnerStatus: 'FAILED', errorCode: 'STEP_TIMEOUT' })], { allTerminal: true }),
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
      expect(screen.getByText(/采集未全部成功：FAILED（STEP_TIMEOUT）/)).toBeTruthy()
      expect(screen.getAllByText(/STEP_TIMEOUT/)).toHaveLength(2)
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
})
