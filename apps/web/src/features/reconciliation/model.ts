import type { JsonObject, JsonValue } from '@cloudctl/api-contracts'

/**
 * C11 对账与人工介入工作台的纯模型层。
 *
 * 后端事实（只读消费，不发明新语义）：
 * - services/control-api/src/cloudctl_api/platform_tasks.py 的
 *   _business_view() 返回 state（业务态）/ runnerStatus / reconciliation /
 *   stallReason / errorCode / commandPayload / controlEvents。
 * - reconcile() 只接受三种决策：KEEP_WAITING / CONFIRMED_APPLIED（必须带
 *   platformItemId，否则 409）/ CONFIRMED_NOT_SUBMITTED（台账已有 APPLIED 行时
 *   409 "reported APPLIED evidence contradicts NOT_SUBMITTED"）。
 * - CANCEL_TRANSITIONS：RECONCILING → REJECTED_RECONCILE_FIRST（409）；
 *   终态 → REJECTED_TERMINAL（409）；_has_commit_intent（payload 带
 *   commitIntent）在提交窗口内也拒绝取消。
 * - retry()：RECONCILING 409；仅 FAILED 可重试；errorCode ∈ UNSAFE_RETRY_CODES
 *   （ACCOUNT_CHANGED/COMMIT_UNKNOWN/XIANYU_PUBLISH_SUCCESS/RECONCILING）409；
 *   未归入 SAFE_RETRY_CODES 的错误码也 409。
 * 本文件的所有判定都是这些服务端规则的**前置镜像**（用于禁用按钮并说明原因），
 * 最终裁决永远在服务端；前端不是授权来源。
 */

export const RECONCILIATION_UI_VERSION = 'reconciliation-workbench/v1@20260917.1'

/** 服务端 RECONCILE_DECISIONS 的封闭集合（platform_tasks.py），只增不改。 */
export const RECONCILE_DECISIONS = ['KEEP_WAITING', 'CONFIRMED_APPLIED', 'CONFIRMED_NOT_SUBMITTED'] as const
export type ReconcileDecision = (typeof RECONCILE_DECISIONS)[number]

/** 平台任务业务视图（GET /api/v1/platform-tasks）中工作台需要的字段；缺字段按可空处理，不编造。 */
export interface ReconTask {
  taskId: string
  deviceId: string | null
  accountId: string | null
  bindingVersion: number | null
  commandType: string | null
  /** 业务态（服务端 _business_view 的 state 字段）。 */
  state: string
  /** Runner 原始状态（QUEUED/CLAIMED/RUNNING/SUCCEEDED/FAILED/UNKNOWN…）。 */
  runnerStatus: string | null
  commandPayload: JsonObject | null
  stallReason: string | null
  errorCode: string | null
  detail: string | null
  /** 服务端对账信封 {status, reason?, history?}，未进入过对账流程时为 null。 */
  reconciliation: ReconEnvelope | null
  controlRevision: number | null
  controlEvents: ReconControlEvent[]
  attempt: number | null
  result: JsonObject | null
  createdAt: string | null
}

export interface ReconEnvelope {
  status: string | null
  reason: string | null
  history: ReconHistoryEntry[]
}

export interface ReconHistoryEntry {
  decision: string | null
  evidence: string | null
  platformItemId: string | null
  actorId: string | null
  occurredAt: string | null
}

export interface ReconControlEvent {
  revision: number | null
  event: string | null
  reason: string | null
  actor: string | null
  issuedAt: string | null
}

const TERMINAL_STATES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'EXPIRED'])
/** platform_tasks.SAFE_RETRY_CODES：服务端判定可安全重试 = 未产生外部效果。 */
const SAFE_RETRY_CODES = new Set([
  'LOCATOR_NOT_FOUND',
  'STEP_TIMEOUT',
  'APP_NOT_FOREGROUND',
  'NETWORK_UNAVAILABLE',
  'PREFLIGHT_FAILED',
])
/** platform_tasks.UNSAFE_RETRY_CODES：不确定或绑定已变，必须先对账。 */
const UNSAFE_RETRY_CODES = new Set(['ACCOUNT_CHANGED', 'COMMIT_UNKNOWN', 'XIANYU_PUBLISH_SUCCESS', 'RECONCILING'])
/** 未到终态且不属于 RECONCILING 的活跃业务态。 */
const ACTIVE_STATES = new Set([
  'QUEUED',
  'WAITING_MATERIALS',
  'PREFLIGHT',
  'RUNNING',
  'RESUME_CHECK',
  'PAUSE_REQUESTED',
  'PAUSED_WAITING_USER',
  'CANCEL_REQUESTED',
])

export function isTerminalState(state: string): boolean {
  return TERMINAL_STATES.has(state)
}

// ---------------------------------------------------------------------------
// 轴 2：外部效果状态（business_state / reconciliation 推导，只读推导不回写）
// ---------------------------------------------------------------------------

/**
 * 外部效果轴。来源优先级：服务端 reconciliation.status > state/errorCode 推导。
 * FAIL_CLOSED：推导不出来时按 UNKNOWN 呈现，绝不显示成成功。
 */
export type ExternalEffectStatus = 'APPLIED' | 'NOT_SUBMITTED' | 'UNKNOWN' | 'PENDING'

export function externalEffectOf(task: Pick<ReconTask, 'state' | 'errorCode' | 'reconciliation'>): ExternalEffectStatus {
  const envelope = task.reconciliation?.status
  if (envelope === 'APPLIED') return 'APPLIED'
  if (envelope === 'NOT_SUBMITTED') return 'NOT_SUBMITTED'
  if (envelope === 'UNKNOWN' || envelope === 'KEEP_WAITING') return 'UNKNOWN'
  if (task.state === 'SUCCEEDED') return 'APPLIED'
  if (task.errorCode === 'CONFIRMED_NOT_SUBMITTED') return 'NOT_SUBMITTED'
  if (task.errorCode === 'COMMIT_UNKNOWN' || task.state === 'RECONCILING') return 'UNKNOWN'
  if (ACTIVE_STATES.has(task.state)) return 'PENDING'
  // FAILED + 安全错误码：服务端把这类失败归为可安全重试（= 未生效）。
  if (task.state === 'FAILED' && (task.errorCode == null || SAFE_RETRY_CODES.has(task.errorCode))) {
    return 'NOT_SUBMITTED'
  }
  // CANCELLED/EXPIRED：取消在提交窗口内会被服务端拒绝，落到终态的取消/过期未进入提交。
  if (task.state === 'CANCELLED' || task.state === 'EXPIRED') return 'NOT_SUBMITTED'
  // 其余（FAILED + 未知/不安全错误码，如 ACCOUNT_CHANGED）：不确定。
  return 'UNKNOWN'
}

export function externalEffectLabel(status: ExternalEffectStatus): string {
  return {
    APPLIED: '已生效（外部已提交）',
    NOT_SUBMITTED: '未提交（外部无此动作）',
    UNKNOWN: '不确定（需对账收敛）',
    PENDING: '执行中（尚未到提交点）',
  }[status]
}

// ---------------------------------------------------------------------------
// 轴 3：设备是否可安全交还（推导，不发明后端语义）
// ---------------------------------------------------------------------------

export type DeviceHandoverStatus = 'IN_USE' | 'HOLD_RECONCILE' | 'RETURNABLE'

export function deviceHandoverOf(
  task: Pick<ReconTask, 'state' | 'errorCode' | 'reconciliation'> & { effect?: ExternalEffectStatus },
): DeviceHandoverStatus {
  const effect = task.effect ?? externalEffectOf(task)
  if (effect === 'UNKNOWN' || task.state === 'RECONCILING') return 'HOLD_RECONCILE'
  if (!isTerminalState(task.state)) return 'IN_USE'
  return 'RETURNABLE'
}

export function deviceHandoverLabel(status: DeviceHandoverStatus): string {
  return {
    IN_USE: '占用中（任务未终态）',
    HOLD_RECONCILE: '不可交还（效果未收敛，先对账）',
    RETURNABLE: '可交还（终态且效果已收敛）',
  }[status]
}

// ---------------------------------------------------------------------------
// 对账可用性 / 三分支（镜像服务端 reconcile() 的门槛，最终裁决在服务端）
// ---------------------------------------------------------------------------

export interface Availability {
  available: boolean
  reason: string | null
}

/** platform_tasks.reconcile()：仅 RECONCILING 或 errorCode ∈ {COMMIT_UNKNOWN, RECONCILING} 可对账；终态 409。 */
export function reconcileAvailabilityOf(task: Pick<ReconTask, 'state' | 'errorCode'>): Availability {
  if (isTerminalState(task.state)) {
    return { available: false, reason: `终态任务（${task.state}）不可再对账，服务端将返回 409` }
  }
  if (task.state === 'RECONCILING' || task.errorCode === 'COMMIT_UNKNOWN' || task.errorCode === 'RECONCILING') {
    return { available: true, reason: null }
  }
  return { available: false, reason: '仅 RECONCILING 或 COMMIT_UNKNOWN 的任务可对账；如需介入先用「标记结果未知」' }
}

/** platform_tasks.mark_unknown()：终态拒绝；非终态可标记（进入 RECONCILING）。 */
export function markUnknownAvailabilityOf(task: Pick<ReconTask, 'state'>): Availability {
  if (isTerminalState(task.state)) {
    return { available: false, reason: `终态任务（${task.state}）不能进入对账，服务端将返回 409` }
  }
  return { available: true, reason: null }
}

/** platform_tasks.retry() 的前置镜像：RECONCILING / 非失败 / 不安全错误码一律 409。 */
export function retryAvailabilityOf(task: Pick<ReconTask, 'state' | 'errorCode'>): Availability {
  if (task.state === 'RECONCILING') {
    return { available: false, reason: '结果不确定必须先对账才能重试（服务端 409）' }
  }
  if (task.state !== 'FAILED') {
    return { available: false, reason: `仅失败任务可重试（当前 ${task.state}）` }
  }
  if (task.errorCode && UNSAFE_RETRY_CODES.has(task.errorCode)) {
    return { available: false, reason: `不安全错误码 ${task.errorCode}：不确定或绑定已变化，必须先对账（服务端 409）` }
  }
  if (task.errorCode && !SAFE_RETRY_CODES.has(task.errorCode)) {
    return { available: false, reason: `错误码 ${task.errorCode} 未被服务端归类为可安全重试（409）` }
  }
  return { available: true, reason: null }
}

/** CANCEL_TRANSITIONS 前置镜像 + commitIntent 提交窗口修饰（_has_commit_intent）。 */
export function cancelAvailabilityOf(
  task: Pick<ReconTask, 'state'> & { commandPayload?: JsonObject | null },
): Availability & { consequence: string | null } {
  if (task.state === 'RECONCILING') {
    return {
      available: false,
      reason: 'RECONCILING：不确定结果必须先经 :reconcile 收敛，服务端拒绝取消（409 REJECTED_RECONCILE_FIRST）',
      consequence: null,
    }
  }
  if (isTerminalState(task.state)) {
    return { available: false, reason: `任务已终态（${task.state}），服务端拒绝取消（409 REJECTED_TERMINAL）`, consequence: null }
  }
  if (task.state === 'CANCEL_REQUESTED') {
    return { available: false, reason: '已在取消中（服务端幂等返回当前视图，无需重复请求）', consequence: null }
  }
  if (task.commandPayload && 'commitIntent' in task.commandPayload) {
    return {
      available: false,
      reason: '任务 payload 带 commitIntent（提交窗口内），服务端拒绝取消，需经 :reconcile 收敛',
      consequence: null,
    }
  }
  return {
    available: true,
    reason: null,
    consequence: '取消不可恢复：服务端会终止该任务并释放其设备占用；它不会把不确定结果改成成功',
  }
}

// ---------------------------------------------------------------------------
// 确认前校验（前端拦截明显必败请求；服务端仍是最终裁决）
// ---------------------------------------------------------------------------

export interface ReconTargetCard {
  taskId: string
  commandType: string | null
  deviceId: string | null
  accountId: string | null
  bindingVersion: number | null
  attempt: number | null
  platformItemIdRequired: boolean
}

/** 确认前必须能展示精确目标；关键字段缺失 → 不允许确认（fail-closed）。 */
export function preciseTargetOf(task: ReconTask, decision: ReconcileDecision | null): ReconTargetCard {
  return {
    taskId: task.taskId,
    commandType: task.commandType,
    deviceId: task.deviceId,
    accountId: task.accountId,
    bindingVersion: task.bindingVersion,
    attempt: task.attempt,
    platformItemIdRequired: decision === 'CONFIRMED_APPLIED',
  }
}

export function preciseTargetComplete(task: ReconTask): boolean {
  return Boolean(task.taskId.trim() && task.commandType?.trim() && task.deviceId?.trim() && task.accountId?.trim())
}

export interface ReconSubmissionCheck {
  ok: boolean
  reason: string | null
}

/**
 * 三分支提交校验：
 * - decision 必须在封闭集合内（不提供第四条路）；
 * - 证据至少 3 个非空白字符（与服务端 Field(min_length=3) 对齐），证据不可读不允许通过；
 * - CONFIRMED_APPLIED 必须填 platformItemId（服务端 409 "CONFIRMED_APPLIED requires a unique platformItemId"）；
 * - 精确目标不完整（taskId/commandType/deviceId/accountId 缺失）不允许确认。
 */
export function validateReconcileSubmission(
  task: ReconTask,
  decision: string | null,
  evidence: string,
  platformItemId: string,
): ReconSubmissionCheck {
  if (!preciseTargetComplete(task)) {
    return { ok: false, reason: '精确目标不完整（taskId/commandType/deviceId/accountId 有缺失），禁止确认' }
  }
  if (decision === null) {
    return { ok: false, reason: '先在三个对账分支中明确选择一个' }
  }
  if (!(RECONCILE_DECISIONS as readonly string[]).includes(decision)) {
    return { ok: false, reason: `非法决策 ${decision}：只有 KEEP_WAITING / CONFIRMED_APPLIED / CONFIRMED_NOT_SUBMITTED` }
  }
  if (evidence.trim().length < 3) {
    return { ok: false, reason: '证据不可读：请填写至少 3 个字符的核实证据（与服务端校验一致）' }
  }
  if (decision === 'CONFIRMED_APPLIED' && platformItemId.trim().length === 0) {
    return { ok: false, reason: 'CONFIRMED_APPLIED 必须填写唯一 platformItemId（服务端会以 409 拒绝）' }
  }
  return { ok: true, reason: null }
}

/** 三个对账分支的展示元数据（顺序固定，不提供「重试 UNKNOWN」之类的快捷分支）。 */
export const RECONCILE_BRANCHES: ReadonlyArray<{
  decision: ReconcileDecision
  label: string
  hint: string
  requiresPlatformItemId: boolean
}> = [
  {
    decision: 'KEEP_WAITING',
    label: '继续等待（KEEP_WAITING）',
    hint: '保留未决动作，不收敛台账；设备继续被占，等待唯一平台结果。',
    requiresPlatformItemId: false,
  },
  {
    decision: 'CONFIRMED_APPLIED',
    label: '可信确认已执行（CONFIRMED_APPLIED）',
    hint: '任务改判成功；必须填写平台侧唯一 platformItemId 作为证据锚点。',
    requiresPlatformItemId: true,
  },
  {
    decision: 'CONFIRMED_NOT_SUBMITTED',
    label: '可信确认未提交（CONFIRMED_NOT_SUBMITTED）',
    hint: '任务改判失败（errorCode=CONFIRMED_NOT_SUBMITTED）；若台账已有 APPLIED 行，服务端返回 409 冲突。',
    requiresPlatformItemId: false,
  },
]

// ---------------------------------------------------------------------------
// 原始 JSON → ReconTask（缺字段按可空处理，绝不编造）
// ---------------------------------------------------------------------------

export function mapReconTask(raw: JsonObject): ReconTask | null {
  const taskId = stringOr(raw.taskId, raw.id)
  if (!taskId) return null
  return {
    taskId,
    deviceId: stringOr(raw.deviceId),
    accountId: stringOr(raw.accountId),
    bindingVersion: numberOrNull(raw.bindingVersion),
    commandType: stringOr(raw.commandType),
    state: stringOr(raw.state) ?? 'UNKNOWN',
    runnerStatus: stringOr(raw.runnerStatus),
    commandPayload: objectOrNull(raw.commandPayload),
    stallReason: stringOr(raw.stallReason),
    errorCode: stringOr(raw.errorCode),
    detail: stringOr(raw.detail),
    reconciliation: mapEnvelope(raw.reconciliation),
    controlRevision: numberOrNull(raw.controlRevision),
    controlEvents: mapControlEvents(raw.controlEvents),
    attempt: numberOrNull(raw.attempt),
    result: objectOrNull(raw.result),
    createdAt: stringOr(raw.createdAt),
  }
}

function mapEnvelope(value: JsonValue | undefined): ReconEnvelope | null {
  const envelope = objectOrNull(value)
  if (envelope === null) return null
  const history = Array.isArray(envelope.history)
    ? envelope.history.filter((item): item is JsonObject => item !== null && typeof item === 'object' && !Array.isArray(item))
    : []
  return {
    status: stringOr(envelope.status),
    reason: stringOr(envelope.reason),
    history: history.map((entry) => ({
      decision: stringOr(entry.decision),
      evidence: stringOr(entry.evidence),
      platformItemId: stringOr(entry.platformItemId),
      actorId: stringOr(entry.actorId),
      occurredAt: stringOr(entry.occurredAt),
    })),
  }
}

function mapControlEvents(value: JsonValue | undefined): ReconControlEvent[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is JsonObject => item !== null && typeof item === 'object' && !Array.isArray(item))
    .map((entry) => ({
      revision: numberOrNull(entry.revision),
      event: stringOr(entry.event),
      reason: stringOr(entry.reason),
      actor: stringOr(entry.actor),
      issuedAt: stringOr(entry.issuedAt),
    }))
}

function stringOr(...values: JsonValue[] | undefined[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

function numberOrNull(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function objectOrNull(value: JsonValue | undefined): JsonObject | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value : null
}
