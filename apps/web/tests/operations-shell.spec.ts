import { createPinia, setActivePinia } from 'pinia'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OperationsShell from '@/components/OperationsShell.vue'
import { operationModules, operationsCatalog } from '@/data/operations-catalog'
import { useOperationsWorkspace } from '@/stores/operations-workspace'
import { useSessionStore } from '@/stores/session'

const { fetchSession } = vi.hoisted(() => ({ fetchSession: vi.fn() }))
vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  createControlApiClient: () => ({ session: fetchSession }),
}))
vi.mock('@/api/runtime-mode', () => ({ operationsMockEnabled: false }))

describe('OperationsShell', () => {
  beforeEach(() => {
    fetchSession.mockReset().mockResolvedValue({
      userId: 'operator', tenantId: 'tenant', roles: ['device_operator'], mfa: true, requestId: 'req',
    })
  })

  it('renders the 15 competitor modules as the operations workspace navigation', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/recipes', name: 'recipe-versions', component: { template: '<div>版本管理</div>' } },
        { path: '/operations', name: 'operations-catalog', component: { template: '<div>目录</div>' } },
        { path: '/operations/:moduleId/:operationId', name: 'operation-detail', component: { template: '<div>功能</div>' } },
      ],
    })
    await router.push('/operations')
    await router.isReady()
    render(OperationsShell, { global: { plugins: [createPinia(), router] } })

    expect(screen.getByText('云控工作台')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Recipe 版本管理' }).getAttribute('href')).toBe('/recipes')
    expect(document.querySelectorAll('.operation-module-nav')).toHaveLength(15)
    expect(operationModules.map((module) => module.label)).toEqual([
      '系统主页', '任务队列', '产品编辑', '采集管理', '商品管理', '帖子管理', '订单管理', '统计分析',
      '闲鱼授权任务', '转转授权任务', '小红书授权任务', '创意中心', '聊天管理', '系统素材', '个人中心',
    ])
    expect(screen.getByText('个人中心')).toBeTruthy()
    expect(screen.getAllByText('全部功能').length).toBeGreaterThan(0)
  })

  it('keeps at most five function tabs and closes the earliest one', () => {
    setActivePinia(createPinia())
    const workspace = useOperationsWorkspace()
    const pages = operationsCatalog.slice(0, 6)
    for (const page of pages) workspace.openTab(page)
    expect(workspace.tabs).toHaveLength(5)
    expect(workspace.tabs.map((tab) => tab.id)).toEqual(pages.slice(1).map((page) => page.id))
    expect(workspace.tabs.some((tab) => tab.id === pages[0]?.id)).toBe(false)
  })

  it('initializes permissions on a direct orders visit and allows retry after an authentication failure', async () => {
    fetchSession.mockRejectedValueOnce(new Error('Authentication required'))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div>Content</div>' } }],
    })
    await router.push('/orders')
    const pinia = createPinia()
    const session = useSessionStore(pinia)
    render(OperationsShell, { global: { plugins: [pinia, router] } })

    await waitFor(() => expect(fetchSession).toHaveBeenCalledTimes(1))
    expect((await screen.findByRole('alert')).textContent).toContain('Authentication required')
    expect(session.can('device.control')).toBe(false)
    expect(screen.queryByText('Control API 已连接')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '重新验证登录' }))

    await waitFor(() => expect(session.can('device.control')).toBe(true))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
