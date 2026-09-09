import { createPinia, setActivePinia } from 'pinia'
import { render, screen } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import OperationsShell from '@/components/OperationsShell.vue'
import { operationModules, operationsCatalog } from '@/data/operations-catalog'
import { useOperationsWorkspace } from '@/stores/operations-workspace'

describe('OperationsShell', () => {
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
})
