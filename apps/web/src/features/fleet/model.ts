import type { JsonObject, JsonValue } from '@cloudctl/api-contracts'
import { presenceFromLastSeen } from '@/api/devices'

/** 上位契约：contracts/fleet/v1/fleet-identity-v1.md（FROZEN 20260916.1）。 */
export const FLEET_CONTRACT_VERSION = 'fleet-identity/v1@20260916.1'

/** 契约 §3：封闭能力键集，新增键只增不改。 */
export const FLEET_CAPABILITY_KEYS = [
  'accessibility',
  'ime',
  'screen_capture',
  'media_projection',
  'flutter_anchors',
  'im_listen',
] as const

export type FleetCapabilityKey = (typeof FLEET_CAPABILITY_KEYS)[number]

export interface FleetCapability {
  key: FleetCapabilityKey
  supported: boolean
  engineMin: number | null
}

/** 平台任务（/api/v1/platform-tasks 业务视图）中工作台需要的子集。 */
export interface FleetTask {
  taskId: string
  deviceId: string
  commandType: string
  state: string
  runnerStatus: string | null
  errorCode: string | null
  detail: string | null
  createdAt: string | null
}

export interface FleetDeviceCard {
  deviceId: string
  name: string
  tenantId: string | null
  /** online = 传输心跳存在；与 executable 分开判定（契约 §2）。 */
  online: boolean
  /** executable = online ∧ 门禁全过 ∧ 引擎达标；调度资格只看它。未知为 null，不猜测。 */
  executable: boolean | null
  /** 已通过的门禁（契约 fixture 中的 executableGates）。 */
  executableGates: string[]
  /** 失败/缺失的门禁 = 权限缺口；API 未回传明细时为 null（不编造）。 */
  blockingGates: string[] | null
  capabilities: FleetCapability[]
  /** 绑定平台账号（契约 §2 accountId 现状债务字段）。 */
  accountId: string | null
  bindingVersion: number | null
  /** 持有者：Companion 进程会话（sessionId 只入遥测，不入 actionKey）。 */
  holderSessionId: string | null
  holderBootId: string | null
  lastSeenAt: string | null
  /** 离线原因：服务端显式回传优先，否则按 transport 心跳缺失描述（仅离线设备非空）。 */
  offlineReason: string | null
  /** 当前进行中的任务（按 deviceId 严格匹配，契约 §6 每设备至多一条 CLAIMED/RUNNING）。 */
  currentTask: FleetTask | null
  /** 最近一条终态任务（含失败详情，仅本设备的）。 */
  settledTask: FleetTask | null
}

const TERMINAL_TASK_STATES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'EXPIRED'])

const GATE_LABELS: Record<string, string> = {
  transport: '心跳连接',
  'accessibility-enabled': '无障碍已开启',
  'accessibility-active': '无障碍处于激活',
  ime: '输入法就绪',
  'screen-unlocked': '屏幕已解锁',
  'engine>=min': '引擎版本达标',
}

export function gateLabel(gate: string): string {
  return GATE_LABELS[gate] ?? gate
}

/**
 * 契约 §2/§5：online 只看传输心跳，executable 才是调度资格。
 * 三档：EXECUTABLE（可派发）/ ONLINE_NOT_EXECUTABLE（在线但门禁未过，权限缺口）/
 * OFFLINE（心跳缺失）。executable 未知按未达标处理（fail-closed，不猜测）。
 */
export type SchedulingEligibility = 'EXECUTABLE' | 'ONLINE_NOT_EXECUTABLE' | 'OFFLINE'

export function schedulingEligibility(device: Pick<FleetDeviceCard, 'online' | 'executable'>): SchedulingEligibility {
  if (!device.online) return 'OFFLINE'
  return device.executable === true ? 'EXECUTABLE' : 'ONLINE_NOT_EXECUTABLE'
}

/** 契约 §3：任务 requiredCapabilities 与设备能力表求交；缺口 → INELIGIBLE_CAPABILITY（不派发，不是失败）。 */
export function capabilityGaps(
  requiredCapabilities: readonly string[],
  capabilities: readonly FleetCapability[],
): FleetCapabilityKey[] {
  const owned = new Set(capabilities.filter((entry) => entry.supported).map((entry) => entry.key))
  const known = new Set<string>(FLEET_CAPABILITY_KEYS)
  return requiredCapabilities
    .filter((key) => known.has(key) && !owned.has(key as FleetCapabilityKey)) as FleetCapabilityKey[]
}

/** 离线原因：服务端显式回传优先，否则按 transport 心跳缺失描述，不编造其他原因。 */
export function offlineReasonOf(
  device: Pick<FleetDeviceCard, 'online'> & { offlineReason?: string | null },
  explicitReason?: string | null,
): string | null {
  if (device.online) return null
  const reason = device.offlineReason ?? explicitReason
  if (reason && reason.trim()) return reason.trim()
  return '心跳缺失（transport 门禁未上报）'
}

/** 权限缺口文案：失败门禁 + 未回传提示。在线设备才有权限缺口一说。 */
export function permissionGapSummary(device: FleetDeviceCard): string[] {
  if (!device.online) return []
  if (device.executable === true) return []
  if (device.blockingGates && device.blockingGates.length > 0) {
    return device.blockingGates.map((gate) => `${gateLabel(gate)} 未满足`)
  }
  if (device.blockingGates && device.blockingGates.length === 0) return ['门禁明细为空，服务端未回传可执行判定依据']
  return ['executable 未回传，等待 Companion 上报门禁明细']
}

/** 按 deviceId 严格匹配取当前进行中的任务（A 设备永远拿不到 B 设备的任务）。 */
export function activeTaskFor(deviceId: string, tasks: readonly FleetTask[]): FleetTask | null {
  return tasks.find((task) => task.deviceId === deviceId && !TERMINAL_TASK_STATES.has(task.state)) ?? null
}

/** 按 deviceId 严格匹配取最近终态任务（失败原因只挂在它自己的设备卡上）。 */
export function settledTaskFor(deviceId: string, tasks: readonly FleetTask[]): FleetTask | null {
  return tasks.find((task) => task.deviceId === deviceId && TERMINAL_TASK_STATES.has(task.state)) ?? null
}

/**
 * 将 /api/v1/devices 的原始记录（含 A10 落地后的 fleet 信封字段）映射为设备卡模型。
 * 字段缺失时保守处理：online 退化到 lastSeen 心跳窗口；executable 缺失为 null；不发明任何值。
 */
export function mapFleetDevice(raw: JsonObject, tasks: readonly FleetTask[] = []): FleetDeviceCard {
  const deviceId = stringValue(raw.deviceId ?? raw.device_id ?? raw.id, '')
  const lastSeenAt = stringOrNull(raw.lastSeenAt ?? raw.last_seen_at)
  const explicitOnline = booleanOrNull(raw.online)
  const online = explicitOnline ?? (lastSeenAt ? presenceFromLastSeen(lastSeenAt) === 'ONLINE' : false)
  const blockingGates = stringArray(raw.blockingGates ?? raw.blocking_gates ?? raw.failedGates ?? raw.failed_gates)
  const executableGates = stringArray(raw.executableGates ?? raw.executable_gates)
  return {
    deviceId: deviceId || 'unknown-device',
    name: stringValue(raw.logicalName ?? raw.logical_name ?? raw.name, deviceId || '未命名设备'),
    tenantId: stringOrNull(raw.tenantId ?? raw.tenant_id),
    online,
    executable: booleanOrNull(raw.executable),
    executableGates: executableGates ?? [],
    blockingGates,
    capabilities: FLEET_CAPABILITY_KEYS.flatMap((key) => {
      const entry = objectValue(objectValue(raw.capabilities)[key])
      const supported = booleanOrNull(entry.supported)
      return supported == null ? [] : [{ key, supported, engineMin: numberOrNull(entry.engineMin ?? entry.engine_min) }]
    }),
    accountId: stringOrNull(raw.accountId ?? raw.account_id),
    bindingVersion: numberOrNull(raw.bindingVersion ?? raw.binding_version),
    holderSessionId: stringOrNull(raw.sessionId ?? raw.session_id),
    holderBootId: stringOrNull(raw.bootId ?? raw.boot_id),
    lastSeenAt,
    offlineReason: stringOrNull(raw.offlineReason ?? raw.offline_reason),
    currentTask: deviceId ? activeTaskFor(deviceId, tasks) : null,
    settledTask: deviceId ? settledTaskFor(deviceId, tasks) : null,
  }
}

function stringValue(value: JsonValue | undefined, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function stringOrNull(value: JsonValue | undefined): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function numberOrNull(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function booleanOrNull(value: JsonValue | undefined): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function objectValue(value: JsonValue | undefined): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function stringArray(value: JsonValue | undefined): string[] | null {
  if (!Array.isArray(value)) return null
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}
