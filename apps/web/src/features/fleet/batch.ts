import {
  capabilityGaps,
  offlineReasonOf,
  schedulingEligibility,
  type FleetDeviceCard,
  type FleetTask,
} from './model'

/**
 * 批量选择展开后的显式逐设备目标。
 * OFFLINE / NOT_EXECUTABLE / INELIGIBLE_CAPABILITY 都是「不派发」，不是任务失败（契约 §3）。
 */
export type FleetTargetStatus = 'ELIGIBLE' | 'OFFLINE' | 'NOT_EXECUTABLE' | 'INELIGIBLE_CAPABILITY'

export interface FleetDeviceTarget {
  deviceId: string
  deviceName: string
  accountId: string | null
  status: FleetTargetStatus
  /** 不派发原因（或可派发时为 null）。 */
  reason: string | null
  /** 该设备当前进行中的任务，用于逐设备查看/取消。 */
  currentTask: FleetTask | null
}

export interface FleetBatchCommand {
  commandType: string
  /** 任务侧 requiredCapabilities（command-v1 字段）；缺口的设备标 INELIGIBLE_CAPABILITY。 */
  requiredCapabilities?: readonly string[]
}

/** 把批量选择展开成显式逐设备目标；每台设备独立判定，互不影响。 */
export function expandDeviceTargets(
  devices: readonly FleetDeviceCard[],
  command: FleetBatchCommand,
): FleetDeviceTarget[] {
  return devices.map((device) => {
    const eligibility = schedulingEligibility(device)
    if (eligibility === 'OFFLINE') {
      return target(device, 'OFFLINE', `设备离线不派发：${offlineReasonOf(device) ?? '心跳缺失'}`)
    }
    if (eligibility === 'ONLINE_NOT_EXECUTABLE') {
      return target(device, 'NOT_EXECUTABLE', notExecutableReason(device))
    }
    const gaps = capabilityGaps(command.requiredCapabilities ?? [], device.capabilities)
    if (gaps.length > 0) {
      // 契约 §3：缺必备能力 → INELIGIBLE_CAPABILITY，任务不派发，不是失败。
      return target(device, 'INELIGIBLE_CAPABILITY', `能力缺口不派发（INELIGIBLE_CAPABILITY）：${gaps.join('、')}`)
    }
    return target(device, 'ELIGIBLE', null)
  })
}

export function targetStatusLabel(status: FleetTargetStatus): string {
  return {
    ELIGIBLE: '可派发',
    OFFLINE: '离线不派发',
    NOT_EXECUTABLE: '门禁未过不派发',
    INELIGIBLE_CAPABILITY: '能力缺口不派发',
  }[status]
}

const TERMINAL_TASK_STATES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'EXPIRED'])

/** 服务端取消规则（platform_tasks.cancel）：终态 409；RECONCILING 409 需先对账；其余可取消。 */
export function cancellableTask(task: FleetTask | null): { cancellable: boolean; reason: string | null } {
  if (!task) return { cancellable: false, reason: '该设备当前没有进行中的任务' }
  if (TERMINAL_TASK_STATES.has(task.state)) {
    return { cancellable: false, reason: `任务已终态（${task.state}），不能取消` }
  }
  if (task.state === 'RECONCILING') {
    return { cancellable: false, reason: '存在未收敛 UNKNOWN 台账行，需先对账（RECONCILE_REQUIRED）' }
  }
  return { cancellable: true, reason: null }
}

function notExecutableReason(device: FleetDeviceCard): string {
  if (device.blockingGates && device.blockingGates.length > 0) {
    return `executable=false，门禁未过：${device.blockingGates.join('、')}`
  }
  if (device.executable === null) return 'executable 未回传，按不可派发处理（fail-closed）'
  return 'executable=false，服务端未回传失败门禁明细'
}

function target(device: FleetDeviceCard, status: FleetTargetStatus, reason: string | null): FleetDeviceTarget {
  return {
    deviceId: device.deviceId,
    deviceName: device.name,
    accountId: device.accountId,
    status,
    reason,
    currentTask: device.currentTask,
  }
}
