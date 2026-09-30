import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { useDisplaySettings } from '@/stores/display-settings'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import OperationsCatalogView from '@/views/OperationsCatalogView.vue'
import { isRetiredOperation, operationsCatalog } from '@/data/operations-catalog'
import { quickPaths } from '@/data/operation-page-availability'

describe('catalog starting paths', () => {
  it('counts the displayed directory, filters status and searches accessible fields', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
    await router.push('/operations')
    render(OperationsCatalogView, { global: { plugins: [createPinia(), router] } })
    const count = operationsCatalog.filter((item) => !isRetiredOperation(item.id)).length
    expect(screen.getByRole('status').textContent).toBe(count + ' / ' + count + ' 项')
    expect(document.querySelectorAll('.operation-link-list a')).toHaveLength(count)
    expect(screen.queryByText('可模拟')).toBeNull()
    await fireEvent.update(screen.getByRole('combobox', { name: '筛选页面接入状态' }), 'unavailable')
    expect(document.querySelectorAll('.status-dedicated')).toHaveLength(0)
    await fireEvent.update(screen.getByRole('textbox', { name: '搜索运营功能' }), '不存在的功能')
    expect(screen.getByText('没有符合当前筛选的功能')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '清除筛选' }))
    expect(document.querySelectorAll('.operation-link-list a')).toHaveLength(count)
    for (const item of quickPaths) {
      const link = screen.getByRole('link', { name: new RegExp(item.title.replace(' / ', ' \\/ ')) })
      await fireEvent.click(link)
      await waitFor(() => expect(router.currentRoute.value.fullPath).toBe(item.to))
    }
  })
  it('reacts to hidden modules and operations in counts, listings and search', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
    await router.push('/operations')
    const pinia = createPinia()
    const display = useDisplaySettings(pinia)
    display.showAllModules()
    display.setModuleVisible('creative', false)
    display.setOperationVisible('product-management-02', 'product-management', false)
    render(OperationsCatalogView, { global: { plugins: [pinia, router] } })
    const expectedCount = operationsCatalog.filter((item) => !isRetiredOperation(item.id) && item.moduleId !== 'creative' && item.id !== 'product-management-02').length
    expect(screen.getByRole('status').textContent).toBe(expectedCount + ' / ' + expectedCount + ' 项')
    expect(screen.queryByRole('heading', { name: '创意中心' })).toBeNull()
    expect(document.querySelector('.operation-link-list a[href$="product-management-02"]')).toBeNull()
    await fireEvent.update(screen.getByRole('textbox', { name: '搜索运营功能' }), '商品导入')
    expect(screen.getByText('没有符合当前筛选的功能')).toBeTruthy()
    display.setOperationVisible('product-management-02', 'product-management', true)
    await waitFor(() => expect(screen.getByRole('link', { name: /商品导入/ })).toBeTruthy())
    await fireEvent.update(screen.getByRole('textbox', { name: '搜索运营功能' }), '')
    display.setModuleVisible('creative', true)
    await waitFor(() => expect(screen.getByRole('heading', { name: '创意中心' })).toBeTruthy())
    const allCount = operationsCatalog.filter((item) => !isRetiredOperation(item.id)).length
    expect(screen.getByRole('status').textContent).toBe(allCount + ' / ' + allCount + ' 项')
  })

})
