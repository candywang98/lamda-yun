import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { operationRoutes } from '@/router'
import { useSessionStore } from '@/stores/session'

const mocks = vi.hoisted(() => ({
  products: vi.fn(), orders: vi.fn(), create: vi.fn(), run: vi.fn(),
  devices: vi.fn(), operationCatalog: vi.fn(), operationTasks: vi.fn(),
}))
vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  operationsMockEnabled: false,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  createControlApiClient: () => ({ devices: mocks.devices,
    operationCatalog: mocks.operationCatalog, operationTasks: mocks.operationTasks }),
}))
vi.mock('@/api/orders', async (original) => ({
  ...await original<typeof import('@/api/orders')>(),
  listOrders: mocks.orders, startXianyuOrderCollect: mocks.create, fetchXianyuOrderRun: mocks.run,
}))
vi.mock('@/api/product-catalog', () => ({ createProductCatalog: () => ({ list: mocks.products }) }))

async function open(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: operationRoutes })
  const pinia = createPinia()
  useSessionStore(pinia).applySession({ userId: 'operator', tenantId: 'tenant', roles: ['device_operator'], mfa: true, requestId: 'fixture' })
  await router.push(path)
  const view = render({ template: '<RouterView />' }, { global: { plugins: [router, pinia] } })
  await flushPromises()
  return { ...view, router }
}

describe('UI-ORDERS-FLOW/20260930.1', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.products.mockResolvedValue([])
    mocks.orders.mockResolvedValue({ items: [], total: 0 })
    mocks.devices.mockResolvedValue([{ id: 'device-1', logical_name: '订单设备', state: 'REGISTERED' }])
  })

  it('renders the real sync-only task at the catalog operation without generic workbench reads', async () => {
    await open('/operations/orders/orders-01')
    expect(screen.getByRole('heading', { name: '同步闲鱼订单' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '创建同步任务' })).toBeTruthy()
    expect(screen.getByLabelText('设备').textContent).toContain('订单设备')
    expect(screen.queryByRole('region', { name: '订单列表' })).toBeNull()
    expect(mocks.orders).not.toHaveBeenCalled()
    expect(mocks.products).not.toHaveBeenCalled()
    expect(mocks.operationCatalog).not.toHaveBeenCalled()
    expect(mocks.operationTasks).not.toHaveBeenCalled()
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('shows device loading failures and retries without submitting a task', async () => {
    mocks.devices.mockRejectedValueOnce(new Error('device service unavailable'))
    await open('/operations/orders/orders-01')
    expect(screen.getByRole('alert').textContent).toContain('设备加载失败')
    expect((screen.getByRole('button', { name: '创建同步任务' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(screen.getByRole('button', { name: '重新加载设备' }))
    await flushPromises()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByLabelText('设备').textContent).toContain('订单设备')
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('opens saved orders directly under product management without fetching products or submitting tasks', async () => {
    const { router } = await open('/operations/product-management/product-management-01?tab=orders')
    expect(screen.getByRole('heading', { name: '已同步订单' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '订单列表' })).toBeTruthy()
    const tabs = within(screen.getByRole('navigation', { name: '商品管理视图' }))
    expect(tabs.getByRole('link', { name: '已同步订单' }).getAttribute('aria-current')).toBe('page')
    expect(router.currentRoute.value.params.moduleId).toBe('product-management')
    expect(mocks.orders).toHaveBeenCalledOnce()
    expect(mocks.products).not.toHaveBeenCalled()
    expect(mocks.create).not.toHaveBeenCalled()
    expect(mocks.run).not.toHaveBeenCalled()
    expect(mocks.operationCatalog).not.toHaveBeenCalled()
    expect(mocks.operationTasks).not.toHaveBeenCalled()
  })

  it('keeps default products intact and follows tab changes and browser back', async () => {
    const { router } = await open('/operations/product-management/product-management-01')
    expect(mocks.products).toHaveBeenCalledOnce()
    expect(mocks.orders).not.toHaveBeenCalled()
    expect(screen.getByPlaceholderText('搜索ID、标题或内容')).toBeTruthy()
    await fireEvent.click(screen.getByRole('link', { name: '已同步订单' }))
    await flushPromises()
    expect(router.currentRoute.value.query.tab).toBe('orders')
    expect(screen.queryByPlaceholderText('搜索ID、标题或内容')).toBeNull()
    expect(mocks.products).toHaveBeenCalledOnce()
    expect(mocks.orders).toHaveBeenCalledOnce()
    router.back()
    await waitFor(() => expect(router.currentRoute.value.query.tab).toBeUndefined())
    await flushPromises()
    expect(screen.getByPlaceholderText('搜索ID、标题或内容')).toBeTruthy()
    expect(mocks.products).toHaveBeenCalledTimes(2)
    expect(mocks.create).not.toHaveBeenCalled()
  })
})
