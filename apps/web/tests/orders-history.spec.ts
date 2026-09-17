import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  dedupeMarkerLabel,
  dedupeMarkerSummary,
  hasNextPage,
  hasMissingScreens,
  normalizeHistoryResult,
  windowAnnotation,
  type FleetOrderHistoryResult,
  type FleetOrderWindow,
} from '@/features/orders/model'
import { listFleetOrderHistory, FleetOrdersApiError, type FleetOrderHistoryQuery } from '@/features/orders/api'
import { ordersHistoryRoutes, registerOrdersHistoryRoutes } from '@/features/orders/routes'
import OrdersHistoryView from '@/features/orders/OrdersHistoryView.vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

// ---------------------------------------------------------------------------
// fixtures（形状对齐 fleet_orders.py 的 _window_view / _history_item_view）
// ---------------------------------------------------------------------------

function windowFixture(overrides: Partial<FleetOrderWindow> = {}): FleetOrderWindow {
  return {
    runKey: 'run-20260917-a',
    accountKey: 'xianyu-alpha',
    deviceId: 'dev-alpha-0001',
    direction: 'SOLD',
    startedAt: '2026-09-17T10:00:05+00:00',
    endedAt: '2026-09-17T10:00:35+00:00',
    screensPresent: [1, 2],
    missingScreens: [],
    emptyScreens: [],
    partialScreens: [],
    newKeys: 3,
    updatedKeys: 0,
    overlap: 2,
    ...overrides,
  }
}

function historyFixture(overrides: Partial<FleetOrderHistoryResult> = {}): FleetOrderHistoryResult {
  return normalizeHistoryResult({
    items: [
      {
        id: '018f1a2b-0000-7000-8000-0000000000a1',
        deviceId: 'dev-alpha-0001',
        platform: 'xianyu',
        direction: 'SOLD',
        orderKey: 'SOLD|买家A|闲置键盘|2500',
        itemTitle: '闲置键盘',
        buyerName: '买家A',
        amountCents: 2500,
        statusText: '已发货',
        occurredAt: '2026-09-17T10:00:00.000Z',
        dedupeMarker: 'MISSING_ID',
        createdAt: '2026-09-17T10:00:05.000Z',
        updatedAt: '2026-09-17T10:00:35.000Z',
      },
      {
        id: '018f1a2b-0000-7000-8000-0000000000a2',
        deviceId: 'dev-alpha-0001',
        platform: 'xianyu',
        direction: 'SOLD',
        orderKey: '371234567890123456',
        itemTitle: '闲置 Kindle',
        buyerName: '买家B',
        amountCents: 12345,
        statusText: '交易成功',
        occurredAt: null,
        dedupeMarker: 'REAL_ID',
        createdAt: '2026-09-17T10:00:05.000Z',
        updatedAt: '2026-09-17T10:00:05.000Z',
      },
    ],
    total: 2,
    offset: 0,
    windows: [windowFixture()],
    dedupeMarkers: { realId: 1, missingId: 1 },
    ...overrides,
  })
}

// ---------------------------------------------------------------------------
// model：窗口标注 / 缺失页 / 去重标记
// ---------------------------------------------------------------------------

describe('orders history model', () => {
  it('annotates the collection window with missing pages', () => {
    const text = windowAnnotation(
      windowFixture({ screensPresent: [1, 3], missingScreens: [2], emptyScreens: [3] }),
    )
    expect(text).toContain('已采第 1、3 屏')
    expect(text).toContain('缺失第 2 屏')
    expect(text).toContain('第 3 屏为空页')
    expect(text).toContain('新增 3 键')
    expect(text).toContain('窗口 2026-09-17T10:00:05+00:00 ~ 2026-09-17T10:00:35+00:00')
    expect(hasMissingScreens(windowFixture({ missingScreens: [2] }))).toBe(true)
    expect(hasMissingScreens(windowFixture())).toBe(false)
  })

  it('annotates partially visible screens and status changes honestly', () => {
    const text = windowAnnotation(
      windowFixture({ partialScreens: [2], updatedKeys: 1, startedAt: null, endedAt: null }),
    )
    expect(text).toContain('第 2 屏有部分可见行')
    expect(text).toContain('状态变化 1 键')
    expect(text).toContain('窗口时间缺失')
  })

  it('summarizes dedupe markers without mixing real and degraded keys', () => {
    expect(dedupeMarkerSummary({ realId: 3, missingId: 5 })).toBe('真实订单号 3 条 · 缺 ID 降级 5 条')
    expect(dedupeMarkerLabel('REAL_ID')).toBe('真实订单号')
    expect(dedupeMarkerLabel('MISSING_ID')).toBe('缺 ID 降级')
    expect(dedupeMarkerLabel(null)).toBe('—')
  })

  it('normalizes partial backend payloads without inventing data', () => {
    const normalized = normalizeHistoryResult({ total: 7 })
    expect(normalized.items).toEqual([])
    expect(normalized.windows).toEqual([])
    expect(normalized.dedupeMarkers).toEqual({ realId: 0, missingId: 0 })
    expect(hasNextPage(normalized)).toBe(false)
    expect(hasNextPage(historyFixture({ nextCursor: 'eyJ2IjoxLCJvIjoyMH0' }))).toBe(true)
  })

  it('registers the history route once', () => {
    const router: Router = createRouter({ history: createMemoryHistory(), routes: ordersHistoryRoutes })
    expect(router.hasRoute('orders-history')).toBe(true)
    registerOrdersHistoryRoutes(router)
    expect(router.getRoutes().filter((route) => route.name === 'orders-history')).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// view：分页浏览 + 采集窗口/缺失页标注展示
// ---------------------------------------------------------------------------

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
}))

const listMock = vi.mocked(listFleetOrderHistory)
vi.mock('@/features/orders/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/orders/api')>()
  return {
    ...actual,
    listFleetOrderHistory: vi.fn(),
  }
})

function renderView() {
  return render(OrdersHistoryView, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes: ordersHistoryRoutes })] },
  })
}

function lastQueryArgs(): FleetOrderHistoryQuery {
  const last = listMock.mock.calls.at(-1)
  if (!last || last[0] === undefined) {
    throw new Error('listFleetOrderHistory was not called with a query')
  }
  return last[0]
}

describe('OrdersHistoryView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders rows, dedupe markers and the collection window annotation', async () => {
    listMock.mockResolvedValueOnce(historyFixture())
    renderView()
    await waitFor(() => expect(screen.getByTestId('history-table')).toBeTruthy())
    expect(screen.getByTestId('history-row-SOLD|买家A|闲置键盘|2500')).toBeTruthy()
    expect(screen.getByTestId('history-row-371234567890123456').textContent).toContain('真实订单号')
    expect(screen.getByTestId('history-row-SOLD|买家A|闲置键盘|2500').textContent).toContain('缺 ID 降级')
    expect(screen.getByTestId('dedupe-markers').textContent).toContain('真实订单号 1 条')
    expect(screen.getByTestId('dedupe-markers').textContent).toContain('缺 ID 降级 1 条')

    const windowPanel = screen.getByTestId('window-run-20260917-a')
    expect(windowPanel.textContent).toContain('run-20260917-a')
    expect(windowPanel.textContent).toContain('xianyu-alpha')
    expect(windowPanel.textContent).toContain('已采第 1、2 屏')
    expect(windowPanel.textContent).toContain('新增 3 键')
    // 无缺失页时不渲染缺失徽标。
    expect(windowPanel.querySelector('[data-testid="missing-badge"]')).toBeNull()
  })

  it('shows the missing-pages badge when a run has screen gaps', async () => {
    listMock.mockResolvedValueOnce(
      historyFixture({ windows: [windowFixture({ screensPresent: [1, 3], missingScreens: [2] })] }),
    )
    renderView()
    await waitFor(() => expect(screen.getByTestId('window-run-20260917-a')).toBeTruthy())
    expect(screen.getByTestId('missing-badge').textContent).toBe('缺失页')
    expect(screen.getByTestId('window-run-20260917-a').textContent).toContain('缺失第 2 屏')
  })

  it('pages forward and back with the opaque cursor', async () => {
    const first = historyFixture({ total: 22, offset: 0, nextCursor: 'cursor-page-2' })
    const second = historyFixture({ total: 22, offset: 20, items: historyFixture().items.slice(0, 1) })
    listMock.mockResolvedValueOnce(first)
    renderView()

    await waitFor(() => expect(screen.getByTestId('history-pager').textContent).toContain('1-2 / 22'))
    expect((screen.getByTestId('pager-prev') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByTestId('pager-next') as HTMLButtonElement).disabled).toBe(false)

    listMock.mockResolvedValueOnce(second)
    await fireEvent.click(screen.getByTestId('pager-next'))
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
    expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: 'cursor-page-2' }))
    expect(screen.getByTestId('history-pager').textContent).toContain('21-21 / 22')
    expect((screen.getByTestId('pager-next') as HTMLButtonElement).disabled).toBe(true)

    listMock.mockResolvedValueOnce(first)
    await fireEvent.click(screen.getByTestId('pager-prev'))
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(3))
    // 回到第一页：进入游标为空（不带 cursor 键）。
    const prevArgs = lastQueryArgs()
    expect(prevArgs).toMatchObject({ limit: 20 })
    expect(prevArgs.cursor).toBeUndefined()
    expect((screen.getByTestId('pager-prev') as HTMLButtonElement).disabled).toBe(true)
  })

  it('applies filters as snake_case query params from page one', async () => {
    listMock.mockResolvedValue(historyFixture())
    renderView()
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1))
    await fireEvent.update(screen.getByTestId('filter-device'), 'dev-alpha-0001')
    await fireEvent.update(screen.getByTestId('filter-direction'), 'BOUGHT')
    await fireEvent.update(screen.getByTestId('filter-account'), 'xianyu-beta')
    await fireEvent.click(screen.getByTestId('apply-filters'))
    await waitFor(() => expect(listMock.mock.calls.length).toBeGreaterThanOrEqual(2))
    const filterArgs = lastQueryArgs()
    expect(filterArgs).toMatchObject({
      deviceId: 'dev-alpha-0001',
      direction: 'BOUGHT',
      accountKey: 'xianyu-beta',
      limit: 20,
    })
    // 应用过滤永远从第一页开始（不带游标）。
    expect(filterArgs.cursor).toBeUndefined()
  })

  it('fails closed on api errors and shows the empty state only when truly empty', async () => {
    listMock.mockRejectedValueOnce(new FleetOrdersApiError(422, 'cursor is malformed（HTTP 422）'))
    renderView()
    await waitFor(() => expect(screen.getByTestId('history-error').textContent).toContain('cursor is malformed'))
    expect(screen.queryByTestId('history-empty')).toBeNull()

    listMock.mockResolvedValueOnce(historyFixture({ items: [], total: 0, windows: [] }))
    await fireEvent.click(screen.getByTestId('refresh'))
    await waitFor(() => expect(screen.getByTestId('history-empty').textContent).toContain('暂无订单历史'))
  })
})

// FleetOrdersApiError is exercised above; keep the import meaningful for type
// checks in strict setups.
void FleetOrdersApiError
