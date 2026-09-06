import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSessionStore } from '@/stores/session'

describe('personal session', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('does not gate actions on a demo role', () => {
    const session = useSessionStore()
    expect(session.can('publish:approve')).toBe(true)
    expect(session.can('device:operate')).toBe(true)
    expect(session.can('content:write')).toBe(true)
  })
})
