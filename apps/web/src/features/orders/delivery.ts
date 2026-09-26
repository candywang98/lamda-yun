export const ORDER_DELIVERY_PROTOCOL = 'order-delivery/1' as const

export interface OrderDelivery {
  protocolVersion: typeof ORDER_DELIVERY_PROTOCOL | null
  state: 'LEGACY_UNVERIFIED' | 'PENDING' | 'SYNCED' | 'BLOCKED'
  receivedScreens: number[]
  expectedScreens: number | null
  collectionComplete: boolean
  stopReason: string | null
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export function isOrderTaskId(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

/** Missing legacy metadata stays unknown; negotiated runs must never downgrade. */
export function validOrderDelivery(
  value: unknown,
  tasks: readonly { state: string | null }[],
  durable: boolean,
  maxScreens = 3,
): value is OrderDelivery {
  if (!isRecord(value) || !Array.isArray(value.receivedScreens) ||
      typeof value.collectionComplete !== 'boolean' ||
      !(value.stopReason === null || (typeof value.stopReason === 'string' && value.stopReason.trim()))) return false
  const screens = value.receivedScreens
  if (screens.length > maxScreens || !screens.every((screen, index) => Number.isInteger(screen) && screen === index + 1)) return false
  const expected = value.expectedScreens
  if (expected !== null && (typeof expected !== 'number' || !Number.isInteger(expected) || expected < 1 || expected > maxScreens)) return false
  if (expected !== null && screens.length > (expected as number)) return false
  if (value.protocolVersion === null) return !durable && value.state === 'LEGACY_UNVERIFIED'
  if (value.protocolVersion !== ORDER_DELIVERY_PROTOCOL || !['PENDING', 'SYNCED', 'BLOCKED'].includes(String(value.state))) return false
  if (value.state === 'BLOCKED' && !value.stopReason) return false
  if (value.state === 'SYNCED') {
    return value.collectionComplete && expected !== null && screens.length === expected &&
      tasks.length > 0 && tasks.every((task) => task.state === 'SUCCEEDED')
  }
  return true
}

export function deliveryLabel(delivery: OrderDelivery | null | undefined): string {
  if (!delivery) return '同步状态未确认'
  return {
    LEGACY_UNVERIFIED: '旧任务：同步未核验',
    PENDING: '同步待确认',
    SYNCED: '同步完成',
    BLOCKED: '同步受阻',
  }[delivery.state]
}

export function deliveryProgress(delivery: OrderDelivery): string {
  return `已入库 ${delivery.receivedScreens.length} 屏 / 实际总屏数 ${delivery.expectedScreens ?? '待确认'}`
}

const reasonLabels: Record<string, string> = {
  TASK_FAILED: '采集任务失败',
  TASK_CANCELLED: '采集任务已取消',
  TASK_EXPIRED: '采集任务已过期',
  COLLECTION_RECONCILING: '采集结果核对中',
  MOBILE_BINDING_CHANGED: '手机绑定已变更',
  ACCOUNT_BINDING_CHANGED: '账号绑定已变更',
  PAYLOAD_CONFLICT: '上报载荷冲突',
  PLAN_FINISHED: '计划步骤结束',
  STOP_EMPTY_PAGE: '空页停止',
  STOP_STAGNANT: '无新增页面停止',
  STOP_MAX_SCREENS: '达到屏数上限',
}

export function deliveryReason(reason: string): string {
  return reasonLabels[reason] ? `${reasonLabels[reason]}（${reason}）` : reason
}
