import { createPinia } from 'pinia'
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'
import PermissionButton from '@/components/PermissionButton.vue'
import { useSessionStore } from '@/stores/session'

describe('PermissionButton', () => {
  it('blocks a viewer and responds to a verified operator session', async () => {
    const pinia = createPinia()
    const session = useSessionStore(pinia)
    const info = { userId: 'user', tenantId: 'tenant', roles: ['viewer'], mfa: false, requestId: 'req' }
    session.applySession(info)
    const view = render(PermissionButton, {
      props: { permission: 'device:operate', label: '进入维护' },
      global: { plugins: [pinia] },
    })
    const button = screen.getByRole('button', { name: '进入维护' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    await fireEvent.click(button)
    expect(view.emitted().click).toBeUndefined()

    session.applySession({ ...info, roles: ['device_operator'] })
    await fireEvent.click(button)
    expect(button.disabled).toBe(false)
    expect(view.emitted().click).toHaveLength(1)
  })

  it('preserves the callers disabled state for authorized users', () => {
    const pinia = createPinia()
    useSessionStore(pinia).applySession({
      userId: 'user', tenantId: 'tenant', roles: ['security_admin'], mfa: true, requestId: 'req',
    })
    render(PermissionButton, {
      props: { permission: 'device:operate', label: '进入维护', disabled: true },
      global: { plugins: [pinia] },
    })
    expect((screen.getByRole('button', { name: '进入维护' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
