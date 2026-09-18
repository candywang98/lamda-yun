import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'
import { liveProblemHint, mapHandover, mapLiveSession, type HandoverReceipt, type LiveSession, type LiveTier, type LiveTransport } from './model'

/** 投屏面板 UI 自身版本（显示用，与契约版本区分）。 */
export const LIVE_PANEL_VERSION = 'live-fleet-panel/v1@20260917.1'

/** L10 会话令牌头（services/control-api/src/cloudctl_api/fleet_live.py SESSION_TOKEN_HEADER）。 */
export const LIVE_SESSION_TOKEN_HEADER = 'X-Live-Session-Token'

export class LiveFleetApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: string,
    /** K13 §4：拒收响应回带的双水位（problem fields），供客户端对齐；未知为 null。 */
    readonly inputWatermark: number | null = null,
    readonly latestFrameSeq: number | null = null,
  ) {
    super(detail)
    this.name = 'LiveFleetApiError'
  }

  get hint(): string {
    return liveProblemHint(this.code, this.status)
  }
}

/** L10 input 提交体：坐标一律帧空间（K13 §3），seq/frameSeq 必带（K13 §4）。 */
export interface LiveInputEvent {
  kind: 'tap' | 'swipe' | 'text'
  seq: number
  frameSeq: number
  epoch?: number
  x?: number
  y?: number
  x2?: number
  y2?: number
  text?: string
}

export interface LiveInputResult {
  accepted: boolean
  inputWatermark: number
  latestFrameSeq: number
}

async function liveRequest<T>(method: string, path: string, options: { body?: unknown; token?: string | null } = {}): Promise<T> {
  if (!controlApiConfigured) {
    throw new LiveFleetApiError(0, 'LIVE_API_NOT_CONFIGURED', '未配置 Control API，投屏面板不可用（不会回退 Mock）')
  }
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  if (options.body !== undefined) headers.set('Content-Type', 'application/json')
  if (options.token) headers.set(LIVE_SESSION_TOKEN_HEADER, options.token)
  const response = await fetch(`${controlApiBaseUrl()}${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!response.ok) {
    throw problemToError(payload, response.status)
  }
  return payload as T
}

function problemToError(payload: unknown, status: number): LiveFleetApiError {
  const problem = payload !== null && typeof payload === 'object' ? (payload as Record<string, unknown>) : {}
  const rawCode = typeof problem.code === 'string' && problem.code ? problem.code : `HTTP_${status}`
  const detail = typeof problem.detail === 'string' && problem.detail ? problem.detail : `请求失败（HTTP ${status}）`
  // L10 的占用类冲突走通用 ConflictError（problem.code=CONFLICT），特定语义在 detail 前缀
  // （LIVE_REMOTE_HELD / LIVE_SESSION_EXISTS / LIVE_EPOCH_STALE…）。这里提取稳定 token 作为
  // 展示 code，避免把「被其他执行者占用」误降级成泛化冲突提示。
  const token = typeof problem.detail === 'string' ? problem.detail.match(/\b(LIVE_[A-Z_]+|INPUT_[A-Z_]+)\b/)?.[1] : undefined
  const code = rawCode.startsWith('LIVE_') || rawCode.startsWith('INPUT_') || !token ? rawCode : token
  const fields = problem.fields !== null && typeof problem.fields === 'object' && !Array.isArray(problem.fields) ? (problem.fields as Record<string, unknown>) : {}
  const watermark = numberFrom(fields.inputWatermark)
  const latestFrameSeq = numberFrom(fields.latestFrameSeq)
  return new LiveFleetApiError(status, code, detail, watermark, latestFrameSeq)
}

function numberFrom(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

// ---------------------------------------------------------------------------
// L10 端点（services/control-api/src/cloudctl_api/fleet_live.py，只读对接）
// ---------------------------------------------------------------------------

/** POST /api/v1/live/devices/{deviceId}/sessions — 建会话（响应一次性携带 sessionToken）。 */
export async function establishLiveSession(deviceId: string, tier: LiveTier, transport?: LiveTransport): Promise<LiveSession> {
  const payload = await liveRequest<Record<string, unknown>>(`POST`, `/api/v1/live/devices/${encodeURIComponent(deviceId)}/sessions`, {
    body: transport ? { tier, transport } : { tier },
  })
  return mapLiveSession(payload)
}

/** GET /api/v1/live/sessions/{sid} — 状态（含 sweep：终态/强制交还在这里可观察）。 */
export async function fetchLiveSessionStatus(sid: string, token: string | null): Promise<LiveSession> {
  const payload = await liveRequest<Record<string, unknown>>('GET', `/api/v1/live/sessions/${encodeURIComponent(sid)}`, { token })
  return mapLiveSession(payload)
}

/** POST /api/v1/live/sessions/{sid}:take-control — 接管（409 = 占用，428 = 授权未确认，403 = 只读档）。 */
export async function takeLiveControl(sid: string, token: string | null): Promise<LiveSession> {
  const payload = await liveRequest<Record<string, unknown>>(`POST`, `/api/v1/live/sessions/${encodeURIComponent(sid)}:take-control`, { token })
  return mapLiveSession(payload)
}

/** POST /api/v1/live/sessions/{sid}:release — 交还；响应在会话字段外携带 handover 回执。 */
export async function releaseLiveControl(
  sid: string,
  token: string | null,
): Promise<{ session: LiveSession; handover: HandoverReceipt | null }> {
  const payload = await liveRequest<Record<string, unknown>>(`POST`, `/api/v1/live/sessions/${encodeURIComponent(sid)}:release`, { token })
  const session = mapLiveSession(payload)
  const handover = mapHandover(payload.handover, { sessionId: session.sessionId, deviceId: session.deviceId })
  return { session, handover }
}

/** POST /api/v1/live/sessions/{sid}:stop — 主动终态。 */
export async function stopLiveSession(sid: string, token: string | null): Promise<LiveSession> {
  const payload = await liveRequest<Record<string, unknown>>(`POST`, `/api/v1/live/sessions/${encodeURIComponent(sid)}:stop`, { token })
  return mapLiveSession(payload)
}

/** POST /api/v1/live/sessions/{sid}/disconnect — 通知断连（who ∈ operator|companion）。 */
export async function notifyLiveDisconnect(sid: string, who: 'operator' | 'companion', token: string | null): Promise<LiveSession> {
  const payload = await liveRequest<Record<string, unknown>>('POST', `/api/v1/live/sessions/${encodeURIComponent(sid)}/disconnect`, {
    body: { who },
    token,
  })
  return mapLiveSession(payload)
}

/**
 * POST /api/v1/live/devices/{deviceId}/sessions/{sid}/input — 输入提交。
 * 拒收（403/422/429）抛 LiveFleetApiError，双水位在 error.inputWatermark/latestFrameSeq。
 */
export async function submitLiveInput(deviceId: string, sid: string, token: string | null, event: LiveInputEvent): Promise<LiveInputResult> {
  const body: Record<string, unknown> = { kind: event.kind, seq: event.seq, frameSeq: event.frameSeq }
  if (event.epoch !== undefined) body.epoch = event.epoch
  if (event.x !== undefined) body.x = event.x
  if (event.y !== undefined) body.y = event.y
  if (event.x2 !== undefined) body.x2 = event.x2
  if (event.y2 !== undefined) body.y2 = event.y2
  if (event.text !== undefined) body.text = event.text
  const payload = await liveRequest<Record<string, unknown>>(
    `POST`,
    `/api/v1/live/devices/${encodeURIComponent(deviceId)}/sessions/${encodeURIComponent(sid)}/input`,
    { body, token },
  )
  return {
    accepted: payload.accepted === true,
    inputWatermark: numberFrom(payload.inputWatermark) ?? 0,
    latestFrameSeq: numberFrom(payload.latestFrameSeq) ?? 0,
  }
}

/** 帧流 WS 地址（L10 JPEG transportPlan.details.operatorStreamPath，slice1 兼容信令）。 */
export function liveOperatorStreamUrl(operatorStreamPath: string): string {
  return `${controlApiBaseUrl().replace(/^http/, 'ws')}${operatorStreamPath}`
}
