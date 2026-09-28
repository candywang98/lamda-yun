import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/stores/session'

const { fetchSession } = vi.hoisted(() => ({ fetchSession: vi.fn() }))

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  createControlApiClient: () => ({ session: fetchSession }),
}))

vi.mock('@/api/runtime-mode', () => ({ operationsMockEnabled: false }))

describe('personal session', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    fetchSession.mockReset()
  })

  it('denies privileged actions until a real session is loaded', () => {
    const session = useSessionStore()
    expect(session.can('publish:approve')).toBe(false)
    expect(session.can('device:operate')).toBe(false)
    expect(session.can('content:write')).toBe(false)
  })

  it('grants permissions from a loaded security_admin session', () => {
    const session = useSessionStore()
    session.applySession({
      tenantId: 'tenant-1',
      userId: 'user-1',
      roles: ['security_admin'],
      mfa: true,
      requestId: 'req-1',
    })
    expect(session.can('publish:approve')).toBe(true)
    expect(session.can('device.control')).toBe(true)
    expect(session.can('recipe.publish')).toBe(true)
  })

  it('clears previously granted permissions when session verification fails', async () => {
    const session = useSessionStore()
    session.applySession({
      tenantId: 'tenant-1', userId: 'user-1', roles: ['security_admin'], mfa: true, requestId: 'req-1',
    })
    fetchSession.mockRejectedValue(new Error('Session expired'))

    await expect(session.loadSession()).rejects.toThrow('Session expired')

    expect(session.can('device.control')).toBe(false)
    expect(session.session).toBeNull()
    expect(session.user.id).toBe('')
    expect(session.loadError).toBe('Session expired')
    expect(session.loaded).toBe(true)
  })

  it('shares concurrent session requests and restores permissions on retry', async () => {
    const session = useSessionStore()
    fetchSession.mockRejectedValueOnce(new Error('offline'))
    await expect(session.loadSession()).rejects.toThrow('offline')
    fetchSession.mockResolvedValue({
      tenantId: 'tenant-1', userId: 'user-1', roles: ['device_operator'], mfa: true, requestId: 'req-2',
    })

    await Promise.all([session.loadSession(), session.loadSession()])

    expect(fetchSession).toHaveBeenCalledTimes(2)
    expect(session.can('device.control')).toBe(true)
    expect(session.loadError).toBe('')
  })
})
