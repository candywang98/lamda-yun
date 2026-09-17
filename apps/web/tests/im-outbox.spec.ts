import { describe, expect, it } from 'vitest'
import {
  isTerminalReplyState,
  outboxConsistency,
  outboxStateLabel,
  settleOutboxDelivery,
} from '@/features/im/outboxConsistency'

describe('im outbox delivery settle（镜像 im_service.TASK_TERMINAL_DELIVERY）', () => {
  it('terminal task states settle the OUT message deterministically', () => {
    expect(settleOutboxDelivery('PENDING', 'SUCCEEDED')).toBe('DELIVERED')
    expect(settleOutboxDelivery('PENDING', 'FAILED')).toBe('FAILED')
    expect(settleOutboxDelivery('PENDING', 'CANCELLED')).toBe('FAILED')
    expect(settleOutboxDelivery('PENDING', 'CANCELED')).toBe('FAILED')
    expect(settleOutboxDelivery('PENDING', 'EXPIRED')).toBe('FAILED')
  })

  it('DELIVERED is absorbing: late failure/cancel reports never retract a sent reply', () => {
    expect(settleOutboxDelivery('DELIVERED', 'FAILED')).toBe('DELIVERED')
    expect(settleOutboxDelivery('DELIVERED', 'CANCELLED')).toBe('DELIVERED')
    expect(settleOutboxDelivery('DELIVERED', 'EXPIRED')).toBe('DELIVERED')
  })

  it('non-terminal task states leave the outbox undecided', () => {
    expect(settleOutboxDelivery('PENDING', 'RUNNING')).toBeNull()
    expect(settleOutboxDelivery('PENDING', 'RECONCILING')).toBeNull()
    expect(settleOutboxDelivery('FAILED', 'RUNNING')).toBeNull()
    expect(isTerminalReplyState('RUNNING')).toBe(false)
    expect(isTerminalReplyState('CANCELLED')).toBe(true)
  })
})

describe('im outbox consistency（取消后本地待发与云端一致）', () => {
  it('a cancelled task must leave no pending send in the cloud outbox', () => {
    const verdict = outboxConsistency('CANCELLED', 'PENDING')
    expect(verdict.consistent).toBe(false)
    if (!verdict.consistent) {
      expect(verdict.expected).toBe('FAILED')
      expect(verdict.actual).toBe('PENDING')
      expect(verdict.reason).toContain('CANCELLED')
    }
  })

  it('a cancelled task with a FAILED outbox is consistent', () => {
    const verdict = outboxConsistency('CANCELLED', 'FAILED')
    expect(verdict.consistent).toBe(true)
    if (verdict.consistent) expect(verdict.expected).toBe('FAILED')
  })

  it('a succeeded task with a DELIVERED outbox is consistent', () => {
    const verdict = outboxConsistency('SUCCEEDED', 'DELIVERED')
    expect(verdict.consistent).toBe(true)
  })

  it('a succeeded task with a PENDING outbox is inconsistent', () => {
    expect(outboxConsistency('SUCCEEDED', 'PENDING').consistent).toBe(false)
  })

  it('a running task must keep the outbox in flight', () => {
    expect(outboxConsistency('RUNNING', 'PENDING').consistent).toBe(true)
    expect(outboxConsistency('RECONCILING', 'PENDING').consistent).toBe(true)
    // Local still executing but the cloud already ruled: misalignment.
    const early = outboxConsistency('RUNNING', 'FAILED')
    expect(early.consistent).toBe(false)
    if (!early.consistent) expect(early.reason).toContain('RUNNING')
  })

  it('labels the three delivery states for operators', () => {
    expect(outboxStateLabel('PENDING')).toContain('待发')
    expect(outboxStateLabel('DELIVERED')).toContain('已送达')
    expect(outboxStateLabel('FAILED')).toContain('未送达')
  })
})
