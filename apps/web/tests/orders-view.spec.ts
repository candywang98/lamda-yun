import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listOrders, OrdersApiError, type OrderRow } from '@/api/orders'
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
  }
})

function orderFixture(overrides: Partial<OrderRow> = {}): OrderRow {
  return {
    id: '018f1a2b-0000-7000-8000-000000000001',
    tenant_id: 'tenant-1',
    device_id: 'dev-alpha-0001',
    platform: 'xianyu',
    direction: 'SOLD',
    order_key: 'XY202609141234',
    item_title: '闲置 Kindle Paperwhite',
    buyer_name: '买家小王',
    amount_cents: 12345,
    status_text: '待发货',
    occurred_at: '2026-09-14T10:00:00.000Z',
    raw: { title: '闲置 Kindle Paperwhite ¥123.45', desc: '九成新' },
    created_at: '2026-09-14T10:01:00.000Z',
    updated_at: '2026-09-14T10:01:00.000Z',
    ...overrides,
  }
}

function pageOf(count: number, startIndex = 0): OrderRow[] {
  return Array.from({ length: count }, (_, i) => orderFixture({
    id: `018f1a2b-0000-7000-8000-${String(startIndex + i).padStart(12, '0')}`,
    order_key: `XY20260914${String(1000 + startIndex + i)}`,
  }))
}

describe('OrdersView', () => {
  beforeEach(() => {
    vi.mocked(listOrders).mockReset().mockResolvedValue({ items: [orderFixture()], total: 1 })
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

  it('expands the row snapshot (raw + fields) on click and collapses on second click', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    await fireEvent.click(screen.getByText('XY202609141234'))
    expect(await screen.findByText(/行原文快照/)).toBeTruthy()
    expect(screen.getByText(/闲置 Kindle Paperwhite ¥123\.45/)).toBeTruthy()
    expect(screen.getByText('dev-alpha-0001')).toBeTruthy()
    expect(screen.getByText('待发货', { selector: '.orders-fields dd' })).toBeTruthy()
    await fireEvent.click(screen.getAllByText('买家小王')[0])
    expect(screen.queryByText(/行原文快照/)).toBeNull()
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

  it('keeps the collect entry disabled with the fail-closed locator note', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    const collect = screen.getByRole('button', { name: '采集订单' })
    expect((collect as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/待真机定位器验证后启用/)).toBeTruthy()
  })

  it('loads device options into the filter dropdown', async () => {
    render(OrdersView)
    await screen.findByText('XY202609141234')
    const deviceSelect = screen.getByLabelText('设备') as HTMLSelectElement
    const option = [...deviceSelect.querySelectorAll('option')].find((node) => node.value === 'dev-alpha-0001')
    expect(option?.textContent).toContain('一加 9R')
  })
})
