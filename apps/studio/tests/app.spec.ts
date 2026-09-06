import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeAll, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/MonacoWorkspace.vue', () => ({
  default: { template: '<div data-testid="monaco-workspace">Monaco test double</div>' },
}))

describe('Studio workspace', () => {
  let App: typeof import('@/App.vue').default

  beforeAll(async () => {
    App = (await import('@/App.vue')).default
  })

  it('labels the device stream as simulated and creates a short session', async () => {
    render(App)
    expect(screen.getAllByText(/模拟设备流/).length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByRole('button', { name: /创建 15 分钟会话/ }))
    expect(screen.getByText('模拟会话已连接')).toBeTruthy()
    expect(screen.getByText(/debug_session.created/)).toBeTruthy()
    expect(screen.getByText(/view.frame\/view.layout\/input.tap\/evidence.capture/)).toBeTruthy()
  })

  it('generates a semantic locator from the UI tree', async () => {
    render(App)
    expect(screen.getByText('locator(resource_id="com.target:id/publish")')).toBeTruthy()
  })

  it('shows the real Python SDK and lifecycle names', () => {
    render(App)
    expect(screen.getByText('publish.py')).toBeTruthy()
    expect(screen.getByText(/Python 3.12 · cloudctl_automation_sdk/)).toBeTruthy()
  })
})
