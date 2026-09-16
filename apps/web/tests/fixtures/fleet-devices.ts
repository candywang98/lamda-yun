import type { JsonObject } from '@cloudctl/api-contracts'

/**
 * Software-only UI fixture，形状冻结自 contracts/fleet/v1/fixtures/k10-positive-fleet-claim.json
 * （fleet-identity/v1@20260916.1）。不是可信生产数据，只用于测试。
 */

export const FROZEN_FIXTURE_DEVICE_ID = 'dev-b0644fb5'
export const FROZEN_FIXTURE_ACCOUNT_ID = 'acc-xianyu-01'
export const FROZEN_FIXTURE_BINDING_VERSION = 7

export interface RawFleetDeviceOverrides {
  deviceId?: string
  logicalName?: string
  accountId?: string | null
  bindingVersion?: number | null
  online?: boolean
  executable?: boolean | null
  executableGates?: string[]
  blockingGates?: string[] | null
  offlineReason?: string | null
  sessionId?: string | null
  lastSeenAt?: string | null
  unsupported?: string[]
}

/** 与冻结 fixture 同形状的设备信封（capabilities 封闭键集，缺省全部支持，media_projection 除外）。 */
export function rawFleetDeviceFixture(overrides: RawFleetDeviceOverrides = {}): JsonObject {
  const unsupported = new Set(overrides.unsupported ?? ['media_projection'])
  const capability = (key: string, engineMin?: number): JsonObject =>
    unsupported.has(key) ? { supported: false } : { supported: true, ...(engineMin != null ? { engineMin } : {}) }
  const device: JsonObject = {
    tenantId: 'tenant-0001',
    deviceId: overrides.deviceId ?? FROZEN_FIXTURE_DEVICE_ID,
    logicalName: overrides.logicalName ?? 'oneplus-9r-main',
    accountId: overrides.accountId !== undefined ? overrides.accountId : FROZEN_FIXTURE_ACCOUNT_ID,
    bindingVersion: overrides.bindingVersion !== undefined ? overrides.bindingVersion : FROZEN_FIXTURE_BINDING_VERSION,
    sessionId: overrides.sessionId !== undefined ? overrides.sessionId : 'sess-20260916-a1',
    bootId: 'boot-20260916-01',
    online: overrides.online ?? true,
    executable: overrides.executable !== undefined ? overrides.executable : true,
    executableGates: overrides.executableGates ?? [
      'transport',
      'accessibility-enabled',
      'accessibility-active',
      'ime',
      'screen-unlocked',
      'engine>=min',
    ],
    capabilities: {
      accessibility: capability('accessibility', 1),
      ime: capability('ime', 1),
      screen_capture: capability('screen_capture', 1),
      media_projection: capability('media_projection'),
      flutter_anchors: capability('flutter_anchors', 2),
      im_listen: capability('im_listen', 1),
    },
  }
  if (overrides.blockingGates !== undefined) device.blockingGates = overrides.blockingGates
  if (overrides.offlineReason !== undefined) device.offlineReason = overrides.offlineReason
  if (overrides.lastSeenAt !== undefined) device.lastSeenAt = overrides.lastSeenAt
  return device
}

export interface FleetTaskFixtureOverrides {
  taskId?: string
  deviceId?: string
  commandType?: string
  state?: string
  errorCode?: string | null
  detail?: string | null
  createdAt?: string
}

/** /api/v1/platform-tasks 业务视图子集。 */
export function platformTaskFixture(overrides: FleetTaskFixtureOverrides = {}): JsonObject {
  return {
    id: overrides.taskId ?? 'task-0001',
    taskId: overrides.taskId ?? 'task-0001',
    deviceId: overrides.deviceId ?? FROZEN_FIXTURE_DEVICE_ID,
    accountId: FROZEN_FIXTURE_ACCOUNT_ID,
    bindingVersion: FROZEN_FIXTURE_BINDING_VERSION,
    commandType: overrides.commandType ?? 'xianyu.publish_listing.steps.v1',
    state: overrides.state ?? 'RUNNING',
    runnerStatus: overrides.state ?? 'RUNNING',
    errorCode: overrides.errorCode ?? null,
    detail: overrides.detail ?? null,
    createdBy: 'operator-fixture',
    createdAt: overrides.createdAt ?? '2026-09-16T10:00:00+08:00',
  }
}
