import { createPinia } from 'pinia'
import { render, screen, waitFor } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
  api: {
    operationCatalog: vi.fn().mockRejectedValue(new Error('control plane offline')),
    operationTasks: vi.fn().mockRejectedValue(new Error('control plane offline')),
    operationFeatureConfigDraft: vi.fn().mockRejectedValue(new Error('control plane offline')),
    devices: vi.fn().mockRejectedValue(new Error('control plane offline')),
  },
}))

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  operationsMockEnabled: true,
  createControlApiClient: () => api,
}))

import OperationsView from '@/views/OperationsView.vue'

describe('OperationsView production failure boundary', () => {
  it('fails closed instead of falling back to Mock when a configured API fails', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/operations', component: { template: '<div>目录</div>' } },
        { path: '/operations/:moduleId/:operationId', component: OperationsView },
      ],
    })
    await router.push('/operations/assets/assets-02')
    await router.isReady()
    render(OperationsView, { global: { plugins: [createPinia(), router] } })

    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Control API 初始化失败'))
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.queryByText('Mock 请求已接收')).toBeNull()
    expect(screen.queryByText('图片素材 · 01')).toBeNull()
    expect((screen.getAllByRole('button', { name: 'Control API 不可用' })[0] as HTMLButtonElement).disabled).toBe(true)
  })
})
