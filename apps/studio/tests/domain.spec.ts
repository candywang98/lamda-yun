import { describe, expect, it } from 'vitest'
import { canReplay, canSafelyCancel, generateLocator, nextStage } from '@/domain'

describe('Studio domain guardrails', () => {
  it('prefers semantic resource identifiers for locators', () => {
    expect(generateLocator({ id: 'publish', className: 'Button', resourceId: 'com.target:id/publish', text: '发布', bounds: '[0,0][1,1]', depth: 1 })).toBe('locator(resource_id="com.target:id/publish")')
  })

  it('falls back explicitly when only bounds are available', () => {
    const generated = generateLocator({ id: 'unknown', className: 'View', bounds: '[1,2][3,4]', depth: 1 })
    expect(generated).toContain('fallback')
    expect(generated).not.toContain('[1,2][3,4]')
  })

  it('prevents replay after commit intent is written', () => {
    expect(canReplay('BEFORE_COMMIT')).toBe(true)
    expect(canReplay('COMMIT_INTENT_WRITTEN')).toBe(false)
    expect(canReplay('RECONCILE')).toBe(false)
  })

  it('does not promise safe cancellation during commit_once', () => {
    expect(canSafelyCancel('PREPARE')).toBe(true)
    expect(canSafelyCancel('COMMIT_ONCE')).toBe(false)
    expect(nextStage('COMMIT_ONCE')).toBe('RECONCILE')
  })
})
