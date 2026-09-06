import { createPinia, setActivePinia } from 'pinia'
import { fireEvent, render, screen } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'
import DisplaySettingsView from '@/views/DisplaySettingsView.vue'
import { displaySettingsStorageKey, navigationVisibilityStorageKey } from '@/data/display-settings'
import { useDisplaySettings } from '@/stores/display-settings'

describe('display settings', () => {
  beforeEach(() => {
    window.localStorage.clear()
    setActivePinia(createPinia())
  })

  it('lists extra panels and persists hidden items', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/operations/settings/display', component: DisplaySettingsView }],
    })
    await router.push('/operations/settings/display')
    await router.isReady()
    render(DisplaySettingsView, { global: { plugins: [createPinia(), router] } })

    expect(screen.getByText('执行策略提示')).toBeTruthy()
    expect(screen.getByText('Control API 错误提示')).toBeTruthy()
    await fireEvent.click(screen.getByLabelText('Control API 错误提示'))
    const saved = JSON.parse(window.localStorage.getItem(displaySettingsStorageKey) ?? '{}') as { apiErrorBanner?: boolean }
    expect(saved.apiErrorBanner).toBe(false)
    expect(useDisplaySettings().visible('apiErrorBanner')).toBe(false)
  })

  it('can hide a whole module or a single entry for debugging', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/operations/settings/display', component: DisplaySettingsView }],
    })
    await router.push('/operations/settings/display')
    await router.isReady()
    render(DisplaySettingsView, { global: { plugins: [createPinia(), router] } })

    expect(screen.getByLabelText('系统主页')).toBeTruthy()
    expect(screen.getByLabelText('系统主页 / 设备列表')).toBeTruthy()
    await fireEvent.click(screen.getByLabelText('采集管理'))
    await fireEvent.click(screen.getByLabelText('系统主页 / 超级擦亮'))
    const saved = JSON.parse(window.localStorage.getItem(navigationVisibilityStorageKey) ?? '{}') as { hiddenModules?: string[]; hiddenOperations?: string[] }
    expect(saved.hiddenModules).toContain('collection')
    expect(saved.hiddenOperations).toContain('system-home-07')
    const display = useDisplaySettings()
    expect(display.moduleVisible('collection')).toBe(false)
    expect(display.operationVisible('system-home-07', 'system-home')).toBe(false)
    expect(display.visibleModules().some((module) => module.id === 'collection')).toBe(false)
  })
})
