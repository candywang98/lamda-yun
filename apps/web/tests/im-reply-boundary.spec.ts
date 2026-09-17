import { describe, expect, it } from 'vitest'
import {
  replyRefusalClass,
  replyRefusalLabel,
  replyRefusalRetryable,
} from '@/features/im/replyBoundary'

describe('im reply boundary（只对授权会话回复，fail-closed）', () => {
  it('translates every known refusal code into an operator-facing reason', () => {
    expect(replyRefusalLabel('REPLY_WRONG_CONVERSATION')).toContain('授权会话不一致')
    expect(replyRefusalLabel('REPLY_CONVERSATION_UNVERIFIED')).toContain('无法确认')
    expect(replyRefusalLabel('REPLY_CHAT_TARGET_CHANGED')).toContain('焦点')
    expect(replyRefusalLabel('REPLY_NO_INBOUND_TRIGGER')).toContain('群发')
    expect(replyRefusalLabel('REPLY_SYSTEM_SESSION')).toContain('系统通知')
    expect(replyRefusalLabel('REPLY_HARASSMENT_SESSION')).toContain('骚扰')
    expect(replyRefusalLabel('THREAD_HAS_NO_INBOUND')).toContain('买家消息')
    expect(replyRefusalLabel('DEVICE_BUSY')).toContain('设备')
    expect(replyRefusalLabel('INPUT_TARGET_CHANGED')).toContain('输入目标')
  })

  it('unknown codes fail closed with a generic refusal, never a send hint', () => {
    const label = replyRefusalLabel('SOME_FUTURE_CODE')
    expect(label).toContain('已拒发')
    expect(label).toContain('未知')
    // Unknown codes are never classified as a retryable transient.
    expect(replyRefusalRetryable('SOME_FUTURE_CODE')).toBe(false)
  })

  it('only rate-limit and busy are retryable; boundary refusals need operator action', () => {
    expect(replyRefusalRetryable('THREAD_REPLY_RATE_LIMITED')).toBe(true)
    expect(replyRefusalRetryable('DEVICE_BUSY')).toBe(true)
    expect(replyRefusalRetryable('REPLY_WRONG_CONVERSATION')).toBe(false)
    expect(replyRefusalRetryable('REPLY_NO_INBOUND_TRIGGER')).toBe(false)
    expect(replyRefusalRetryable('INPUT_TARGET_CHANGED')).toBe(false)
  })

  it('groups refusals into boundary classes', () => {
    expect(replyRefusalClass('REPLY_WRONG_CONVERSATION')).toBe('wrong-session')
    expect(replyRefusalClass('REPLY_CONVERSATION_UNVERIFIED')).toBe('wrong-session')
    expect(replyRefusalClass('REPLY_CHAT_TARGET_CHANGED')).toBe('focus')
    expect(replyRefusalClass('INPUT_TARGET_CHANGED')).toBe('focus')
    expect(replyRefusalClass('REPLY_NO_INBOUND_TRIGGER')).toBe('unsolicited')
    expect(replyRefusalClass('THREAD_HAS_NO_INBOUND')).toBe('unsolicited')
    expect(replyRefusalClass('REPLY_SYSTEM_SESSION')).toBe('session-type')
    expect(replyRefusalClass('REPLY_HARASSMENT_SESSION')).toBe('session-type')
    expect(replyRefusalClass('DEVICE_BUSY')).toBe('device-busy')
    expect(replyRefusalClass('INPUT_REJECTED')).toBe('field-input')
    expect(replyRefusalClass('SOME_FUTURE_CODE')).toBe('unknown')
  })
})
