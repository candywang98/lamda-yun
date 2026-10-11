import { normalizeImDeliveryState } from '@/api/im'

// A narrow local text hint, not a claim about server provenance or classification.
export function isNotificationPreview(text: string | null | undefined): boolean {
  return /^(?:给你)?发来(?:了)?(?:一条)?新消息[。！!]?$/u.test(text?.trim() ?? '')
}

export function deliveryLabel(value: unknown): string {
  return {
    PENDING: '等待手机确认',
    DELIVERED: '手机报告发送完成 · 不代表对方已收到或已读',
    FAILED: '回复任务失败 · 请核对手机与任务记录',
    UNKNOWN: '发送状态未知',
  }[normalizeImDeliveryState(value)]
}
