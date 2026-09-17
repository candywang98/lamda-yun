import type { JsonObject } from '@cloudctl/api-contracts'
import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders, createControlApiClient } from '@/api/control'
import { mapReconTask, type ReconTask } from './model'

/** 对账工作台 UI 自身版本（显示用）。 */
export const RECONCILIATION_WORKBENCH_VERSION = 'reconciliation-workbench/v1@20260917.1'

export class ReconciliationApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    detail: string,
  ) {
    super(detail)
    this.name = 'ReconciliationApiError'
  }
}

/**
 * 数据模式：对账工作台是 operator 介入面，只有 api / unavailable 两态，
 * 不提供 Mock 浏览（避免把演示数据当成待对账的真实任务），fail-closed。
 */
export function resolveReconciliationDataMode(apiConfigured: boolean = controlApiConfigured): 'api' | 'unavailable' {
  return apiConfigured ? 'api' : 'unavailable'
}

/** 服务端 list 返回 {items, nextCursor}；容错兼容直接数组。 */
export function normalizeReconTasks(payload: unknown): ReconTask[] {
  const items = Array.isArray(payload)
    ? payload
    : payload !== null && typeof payload === 'object' && Array.isArray((payload as { items?: unknown }).items)
      ? (payload as { items: unknown[] }).items
      : []
  return items
    .filter((item): item is JsonObject => item !== null && typeof item === 'object' && !Array.isArray(item))
    .map((item) => mapReconTask(item))
    .filter((task): task is ReconTask => task !== null)
}

/** GET /api/v1/platform-tasks（列表，含 business_state / reconciliation）。 */
export async function fetchReconTasks(): Promise<ReconTask[]> {
  const api = createControlApiClient()
  try {
    return normalizeReconTasks(await api.listPlatformTasks({ limit: 100 }))
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new ReconciliationApiError(0, 'RECONCILIATION_LIST_FAILED', detail)
  }
}

/** GET /api/v1/platform-tasks/{taskId}（含 events 的完整视图）。 */
export async function fetchReconTaskDetail(taskId: string): Promise<ReconTask> {
  const api = createControlApiClient()
  try {
    const view = (await api.getPlatformTask(taskId)) as unknown
    const task = view !== null && typeof view === 'object' && !Array.isArray(view) ? mapReconTask(view as JsonObject) : null
    if (!task) throw new ReconciliationApiError(0, 'RECONCILIATION_INVALID_RESPONSE', '任务响应缺少 taskId 字段')
    return task
  } catch (error) {
    if (error instanceof ReconciliationApiError) throw error
    const detail = error instanceof Error ? error.message : String(error)
    throw new ReconciliationApiError(0, 'RECONCILIATION_GET_FAILED', detail)
  }
}

/**
 * 所有放行动作都走服务端端点（前端不是授权来源，无本地豁免）。
 * 服务端负例（409 冲突 / 404 / 403）原样抛 ReconciliationApiError，detail 保留服务端原文。
 */
async function postTaskAction(taskId: string, action: string, body: JsonObject): Promise<ReconTask> {
  if (!controlApiConfigured) {
    throw new ReconciliationApiError(0, 'RECONCILIATION_API_NOT_CONFIGURED', '未配置 Control API，人工介入动作已关闭（不会回退 Mock）')
  }
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  headers.set('Content-Type', 'application/json')
  const response = await fetch(
    `${controlApiBaseUrl()}/api/v1/platform-tasks/${encodeURIComponent(taskId)}:${action}`,
    { method: 'POST', headers, credentials: 'same-origin', body: JSON.stringify(body) },
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
    const detail =
      typeof problem.detail === 'string' && problem.detail.trim()
        ? problem.detail
        : text.trim() || `操作失败（HTTP ${response.status}）`
    throw new ReconciliationApiError(response.status, code, detail)
  }
  const task = payload !== null && typeof payload === 'object' && !Array.isArray(payload) ? mapReconTask(payload as JsonObject) : null
  if (!task) throw new ReconciliationApiError(response.status, 'RECONCILIATION_INVALID_RESPONSE', '操作响应缺少任务字段')
  return task
}

/** POST :mark-unknown body {reason} → 任务进入 RECONCILING（终态任务服务端 409）。 */
export function markTaskUnknown(taskId: string, reason: string): Promise<ReconTask> {
  return postTaskAction(taskId, 'mark-unknown', { reason })
}

/** POST :reconcile body {decision, evidence, platformItemId}。CONFIRMED_APPLIED 必带 platformItemId（服务端 409）。 */
export function reconcileTask(
  taskId: string,
  decision: string,
  evidence: string,
  platformItemId: string | null,
): Promise<ReconTask> {
  const body: JsonObject = { decision, evidence }
  if (platformItemId && platformItemId.trim()) body.platformItemId = platformItemId.trim()
  return postTaskAction(taskId, 'reconcile', body)
}

/** POST :cancel body {reason}。RECONCILING / 终态 / 提交窗口内服务端一律 409。 */
export function cancelTask(taskId: string, reason: string): Promise<ReconTask> {
  return postTaskAction(taskId, 'cancel', { reason })
}

/** POST :retry body {reason}。RECONCILING / 不安全错误码服务端一律 409。 */
export function retryTask(taskId: string, reason: string): Promise<ReconTask> {
  return postTaskAction(taskId, 'retry', { reason })
}
