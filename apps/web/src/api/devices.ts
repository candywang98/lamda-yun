import type { JsonObject, JsonValue } from '@cloudctl/api-contracts'
import type { Device, Status } from '@/types'

const statusValues = new Set<Status>([
  'ONLINE', 'OFFLINE', 'MAINTENANCE', 'PENDING_APPROVAL', 'APPROVED', 'QUEUED',
  'RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'UNKNOWN', 'CANCELED', 'PAUSED',
  'BLOCKED', 'SUPPORTED', 'CANDIDATE',
])

const ONLINE_WINDOW_MS = 90_000

export type DevicePresence = 'ONLINE' | 'OFFLINE' | 'BOUND_UNSEEN'

export function presenceFromLastSeen(lastSeenAt: string | null | undefined, now = Date.now()): DevicePresence {
  if (!lastSeenAt) return 'BOUND_UNSEEN'
  const seen = Date.parse(lastSeenAt)
  if (!Number.isFinite(seen)) return 'BOUND_UNSEEN'
  return now - seen <= ONLINE_WINDOW_MS ? 'ONLINE' : 'OFFLINE'
}

export function presenceLabel(presence: DevicePresence): string {
  return { ONLINE: '在线', OFFLINE: '离线', BOUND_UNSEEN: '已绑定未报活' }[presence]
}

export function mapControlDevice(value: JsonObject): Device {
  const targetApps = objectValue(value.target_app_versions ?? value.targetAppVersions)
  const capabilities = objectValue(value.capabilities)
  const lastSeenAt = stringValue(value.last_seen_at ?? value.lastSeenAt, '')
  const presence = presenceFromLastSeen(lastSeenAt || null)
  const storedState = stringValue(value.state, 'UNKNOWN').toUpperCase()
  const status: Status = presence === 'ONLINE'
    ? 'ONLINE'
    : presence === 'OFFLINE'
      ? 'OFFLINE'
      : statusValues.has(storedState as Status)
        ? storedState as Status
        : 'UNKNOWN'
  return {
    id: stringValue(value.id, 'unknown-device'),
    name: stringValue(value.logical_name ?? value.logicalName, '未命名设备'),
    status,
    android: stringValue(value.android_version ?? value.androidVersion, '未回传'),
    lamda: stringValue(value.lamda_version ?? value.lamdaVersion, '不适用'),
    app: Object.entries(targetApps).map(([name, version]) => `${name} ${String(version)}`).join(', ') || '未回传',
    edge: stringValue(value.edge_id ?? value.edgeId, '手机直连'),
    battery: numberValue(objectValue(capabilities.health).batteryPercent ?? objectValue(capabilities.health).battery_percent ?? value.battery_percent ?? value.batteryPercent),
    temperature: numberValue(objectValue(capabilities.health).temperatureCelsius ?? objectValue(capabilities.health).temperature_celsius ?? value.temperature_celsius ?? value.temperatureCelsius),
    account: '通过账号 API 查看',
    capability: Object.keys(capabilities).join(', ') || '未声明',
    version: numberValue(value.version),
    maintenance: booleanValue(value.maintenance),
    lastSeenAt: lastSeenAt || null,
    presence,
    accessibilityEnabled: booleanOrNull(capabilities.accessibilityEnabled ?? capabilities.accessibility_enabled),
    batteryOptimizationIgnored: booleanOrNull(
      capabilities.batteryOptimizationIgnored ?? capabilities.battery_optimization_ignored,
    ),
    runnerState: stringValue(capabilities.runnerState ?? capabilities.runner_state, '') || null,
  }
}

export function previewCaption(status: {
  active: boolean
  waitingForFrame: boolean
  hasFrame: boolean
  capturedAt: string | null
  accessibilityEnabled: boolean | null
}): string {
  if (status.accessibilityEnabled === false) return '无障碍未开启，手机无法截屏回传'
  if (!status.active && !status.hasFrame) return '尚未开始投屏'
  if (status.waitingForFrame && !status.hasFrame) return '已通知手机，等待 Companion 回传画面'
  if (status.waitingForFrame) return '正在刷新画面'
  if (status.hasFrame && status.capturedAt) {
    const captured = Date.parse(status.capturedAt)
    const clock = Number.isFinite(captured) ? new Date(captured).toLocaleTimeString() : status.capturedAt
    return `Companion 实时画面 · ${clock}`
  }
  return 'Companion 投屏'
}

export function keepAliveHint(
  device: Pick<Device, 'presence' | 'accessibilityEnabled' | 'batteryOptimizationIgnored'>,
): string | null {
  if (device.presence !== 'ONLINE' && device.presence !== 'OFFLINE') return null
  if (device.accessibilityEnabled === false) return '无障碍未开启，无法执行本机任务'
  if (device.batteryOptimizationIgnored === false) return '未忽略电池优化，国产 ROM 可能冻停心跳'
  return null
}

function stringValue(value: JsonValue | undefined, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function numberValue(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function booleanValue(value: JsonValue | undefined): boolean {
  return value === true
}

function booleanOrNull(value: JsonValue | undefined): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function objectValue(value: JsonValue | undefined): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value : {}
}
