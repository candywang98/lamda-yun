import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSessionStore } from '@/stores/session'

describe('personal session', () => {
  beforeEach(() => setActivePinia(createPinia()))

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
})
