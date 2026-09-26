import type { ImBucket, ImCategory, ImClassification } from '@/api/im'

export const IM_BUCKETS: ReadonlyArray<{ key: ImBucket; label: string }> = [
  { key: 'user', label: '用户消息' },
  { key: 'notice', label: '通知 / 营销' },
  { key: 'review', label: '待确认' },
  { key: 'all', label: '全部' },
]

export const IM_CATEGORIES: ReadonlyArray<{ key: ImCategory; label: string }> = [
  { key: 'HUMAN_MESSAGE', label: '用户消息' },
  { key: 'SYSTEM_NOTICE', label: '系统通知' },
  { key: 'PROMOTION', label: '营销通知' },
  { key: 'UNKNOWN', label: '待确认' },
]

export function categoryLabel(category?: ImCategory | null): string {
  return IM_CATEGORIES.find((item) => item.key === category)?.label ?? '待确认'
}

export function classificationSource(classification?: ImClassification | null): string {
  const labels = { MANUAL: '人工', RULE: '规则', MODEL: '模型', UNCLASSIFIED: '未分类' }
  return classification ? labels[classification.source] ?? '未分类' : '未分类'
}

export function classificationVersion(classification?: ImClassification | null): number | null {
  if (classification == null) return 0
  return Number.isSafeInteger(classification.version) && classification.version >= 0 ? classification.version : null
}
