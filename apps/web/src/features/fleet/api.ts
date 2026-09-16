import type { JsonObject } from '@cloudctl/api-contracts'
import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders, createControlApiClient, operationsMockEnabled } from '@/api/control'
import { FLEET_CONTRACT_VERSION, mapFleetDevice, type FleetDeviceCard, type FleetTask } from './model'

/** 设备工作台 UI 自身版本（显示用，与合同版本区分）。 */
export const FLEET_UI_VERSION = 'fleet-workbench/v1@20260916.1'

export type FleetDataMode = 'api' | 'mock' | 'unavailable'

/**
 * 数据模式：正式模式（未配置 API 且未显式开 mock）→ unavailable，fail-closed，
 * 绝不自动回退 mock。operationsMockEnabled 只在开发构建 + 显式 flag 时为 true（见 api/runtime-mode.ts）。
 */
export function resolveFleetDataMode(
  apiConfigured: boolean = controlApiConfigured,
  mockEnabled: boolean = operationsMockEnabled,
): FleetDataMode {
  if (apiConfigured) return 'api'
  return mockEnabled ? 'mock' : 'unavailable'
}

/** 工作台版本行：正式模式显示 API 地址 + 合同/构建版本；mock 模式醒目标识由横幅承担。 */
export function fleetVersionLine(mode: FleetDataMode): string {
  if (mode === 'api') {
    const base = controlApiBaseUrl() || '（开发代理 /api）'
    return `API ${base} · 合同 ${FLEET_CONTRACT_VERSION} · UI ${FLEET_UI_VERSION}`
  }
  if (mode === 'mock') return `Mock 数据 · 合同 ${FLEET_CONTRACT_VERSION} · UI ${FLEET_UI_VERSION}`
  return `Control API 未配置 · 合同 ${FLEET_CONTRACT_VERSION} · UI ${FLEET_UI_VERSION}`
}

export class FleetApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    detail: string,
  ) {
    super(detail)
    this.name = 'FleetApiError'
  }
}

/** 服务端 list 返回 {items, nextCursor}；容错兼容直接数组。 */
export function normalizePlatformTasks(payload: unknown): FleetTask[] {
  const items = Array.isArray(payload)
    ? payload
    : payload !== null && typeof payload === 'object' && Array.isArray((payload as { items?: unknown }).items)
      ? (payload as { items: unknown[] }).items
      : []
  return items.map(normalizeTask).filter((task): task is FleetTask => task !== null)
}

function normalizeTask(value: unknown): FleetTask | null {
  if (value === null || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const taskId = stringOr(row.taskId, row.id)
  const deviceId = stringOr(row.deviceId)
  if (!taskId || !deviceId) return null
  return {
    taskId,
    deviceId,
    commandType: stringOr(row.commandType) ?? 'unknown-command',
    state: stringOr(row.state) ?? 'UNKNOWN',
    runnerStatus: stringOr(row.runnerStatus),
    errorCode: stringOr(row.errorCode),
    detail: stringOr(row.detail),
    createdAt: stringOr(row.createdAt),
  }
}

function stringOr(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

export interface FleetSnapshot {
  devices: FleetDeviceCard[]
  /** 任务列表加载失败不阻塞设备卡（Viewer 角色可能无权限），但把原因带出来。 */
  taskLoadError: string | null
}

export async function fetchFleetSnapshot(): Promise<FleetSnapshot> {
  const api = createControlApiClient()
  const [rawDevices, taskResult] = await Promise.all([
    api.devices(),
    api
      .listPlatformTasks({ limit: 100 })
      .then((payload) => ({ tasks: normalizePlatformTasks(payload), error: null as string | null }))
      .catch(() => ({ tasks: [] as FleetTask[], error: '任务列表加载失败，设备卡暂不显示当前任务' })),
  ])
  return {
    devices: rawDevices.map((raw: JsonObject) => mapFleetDevice(raw, taskResult.tasks)),
    taskLoadError: taskResult.error,
  }
}

/** 逐设备取消：POST /api/v1/platform-tasks/{taskId}:cancel（服务端负例 409/404 → FleetApiError）。 */
export async function cancelFleetTask(taskId: string, reason: string): Promise<FleetTask> {
  if (!controlApiConfigured) {
    throw new FleetApiError(0, 'FLEET_API_NOT_CONFIGURED', '未配置 Control API，取消操作已关闭（不会回退 Mock）')
  }
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  headers.set('Content-Type', 'application/json')
  const response = await fetch(
    `${controlApiBaseUrl()}/api/v1/platform-tasks/${encodeURIComponent(taskId)}:cancel`,
    { method: 'POST', headers, credentials: 'same-origin', body: JSON.stringify({ reason }) },
  )
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!response.ok) {
    const problem = payload !== null && typeof payload === 'object' ? (payload as Record<string, unknown>) : {}
    const code = typeof problem.code === 'string' ? problem.code : `HTTP_${response.status}`
    const detail = typeof problem.detail === 'string' ? problem.detail : `取消失败（HTTP ${response.status}）`
    throw new FleetApiError(response.status, code, detail)
  }
  const task = normalizeTask(payload)
  if (!task) throw new FleetApiError(response.status, 'FLEET_INVALID_RESPONSE', '取消响应缺少任务字段')
  return task
}

/**
 * 开发 Mock 快照：形状取自冻结 fixture contracts/fleet/v1/fixtures/k10-positive-fleet-claim.json，
 * 仅用于 mock 模式浏览 UI，正式模式永远不会被调用。
 */
export function mockFleetSnapshot(): FleetSnapshot {
  const tasks: FleetTask[] = [
    {
      taskId: '0a1b2c3d-aaaa-bbbb-cccc-444455556666',
      deviceId: 'dev-b0644fb5',
      commandType: 'xianyu.publish_listing.steps.v1',
      state: 'RUNNING',
      runnerStatus: 'RUNNING',
      errorCode: null,
      detail: null,
      createdAt: '2026-09-16T10:00:00+08:00',
    },
    {
      taskId: '0a1b2c3d-aaaa-bbbb-cccc-444455557777',
      deviceId: 'dev-c9977aa2',
      commandType: 'xianyu.publish_listing.steps.v1',
      state: 'FAILED',
      runnerStatus: 'FAILED',
      errorCode: 'STEP_TIMEOUT',
      detail: '第 4 步等待发布按钮超时',
      createdAt: '2026-09-16T09:40:00+08:00',
    },
  ]
  const devices = [
    mapFleetDevice(
      {
        deviceId: 'dev-b0644fb5',
        logicalName: 'oneplus-9r-main',
        accountId: 'acc-xianyu-01',
        bindingVersion: 7,
        sessionId: 'sess-20260916-a1',
        bootId: 'boot-20260916-01',
        online: true,
        executable: true,
        executableGates: ['transport', 'accessibility-enabled', 'accessibility-active', 'ime', 'screen-unlocked', 'engine>=min'],
        capabilities: {
          accessibility: { supported: true, engineMin: 1 },
          ime: { supported: true, engineMin: 1 },
          screen_capture: { supported: true, engineMin: 1 },
          media_projection: { supported: false },
          flutter_anchors: { supported: true, engineMin: 2 },
          im_listen: { supported: true, engineMin: 1 },
        },
      } as JsonObject,
      tasks,
    ),
    mapFleetDevice(
      {
        deviceId: 'dev-c9977aa2',
        logicalName: 'redmi-k60-broken',
        accountId: 'acc-xianyu-02',
        bindingVersion: 3,
        online: true,
        executable: false,
        executableGates: ['transport'],
        blockingGates: ['accessibility-enabled', 'ime'],
        capabilities: {
          accessibility: { supported: false },
          ime: { supported: false },
          screen_capture: { supported: true, engineMin: 1 },
          media_projection: { supported: false },
          flutter_anchors: { supported: true, engineMin: 2 },
          im_listen: { supported: true, engineMin: 1 },
        },
      } as JsonObject,
      tasks,
    ),
    mapFleetDevice(
      {
        deviceId: 'dev-d3128e77',
        logicalName: 'pixel-8-offline',
        accountId: 'acc-xianyu-03',
        bindingVersion: 11,
        online: false,
        offlineReason: 'Companion 心跳超时 3 个周期，最后在线 2026-09-16 09:12',
        executable: false,
        capabilities: {
          accessibility: { supported: true, engineMin: 1 },
          ime: { supported: true, engineMin: 1 },
          screen_capture: { supported: true, engineMin: 1 },
          media_projection: { supported: false },
          flutter_anchors: { supported: false },
          im_listen: { supported: true, engineMin: 1 },
        },
      } as JsonObject,
      tasks,
    ),
  ]
  return { devices, taskLoadError: null }
}
