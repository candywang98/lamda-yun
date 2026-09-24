import type { JsonObject } from '@cloudctl/api-contracts'

/** 上位契约：contracts/live-capabilities/v1/README.md（FROZEN 20260917.1，K13）。 */
export const LIVE_CONTRACT_VERSION = 'live-capabilities/v1@20260917.1'

// ---------------------------------------------------------------------------
// 会话模型（L10 服务端 view() 载荷的保守映射；缺字段按可空处理，不发明值）
// ---------------------------------------------------------------------------

export type LiveTier = 'JPEG_PREVIEW' | 'INTERACTIVE_REMOTE' | 'WEBRTC'
export type LiveTransport = 'JPEG_WS' | 'WEBRTC'
export type LiveSessionState = 'VIEWING' | 'REMOTE' | 'CLOSED'

export interface SafeAreaInsets {
  left: number
  top: number
  right: number
  bottom: number
}

/** K13 §3 帧描述符；safeArea 以设备空间像素表达（挖孔/刘海/系统栏排除区）。 */
export interface FrameGeometry {
  frameWidth: number
  frameHeight: number
  deviceWidth: number
  deviceHeight: number
  rotation: 0 | 90 | 180 | 270
  safeArea: SafeAreaInsets | null
}

/** 档位派生能力信封；null = 服务端未回传 → fail-closed 按只读处理，不猜测。 */
export interface LiveCapabilities {
  allowsInput: boolean | null
  uiLabel: 'preview' | 'interactive' | 'interactive-hd' | null
  frameDownlink: boolean | null
  turnRequired: boolean | null
}

export interface InputPolicy {
  maxInputRatePerSecond: number
  ttlExpiryMs: number
  staleFrameThreshold: number
}

export interface LiveHandoverTask {
  taskId: string
  pauseState: string
  resumeMode: 'REQUEUE_AUTO' | 'CONFIRM_REQUIRED'
}

/** 交还回执（REMOTE → VIEWING）：K13 §5，含本地 ack 记录所需的全部事实。 */
export interface HandoverReceipt {
  sessionId: string
  deviceId: string
  tier: LiveTier | null
  from: string
  to: string
  affectedTasks: LiveHandoverTask[]
  singleWriterRestored: boolean
  frameDownlinkContinues: boolean
  releasedAt: string
  releasedBy: string
}

export interface LiveTerminalNotice {
  cause: string
  resumable: boolean
  reauthorizationRequired: boolean
  tokenInvalidated: boolean
  closedAt: string | null
}

export interface LiveSession {
  sessionId: string
  tenantId: string | null
  deviceId: string
  operatorId: string | null
  tier: LiveTier | null
  transport: LiveTransport | null
  state: LiveSessionState
  lease: { deviceLeaseId: string | null; epoch: number | null; purpose: 'LIVE' }
  frameGeometry: FrameGeometry
  capabilities: LiveCapabilities
  inputPolicy: InputPolicy | null
  authorization: {
    mediaProjectionRequired: boolean
    userConfirmedAt: string | null
    persistsAcrossReboot: boolean
    silentResumeAllowed: boolean
  }
  establishedAt: string | null
  expiresAt: string | null
  maxDurationMinutes: number | null
  terminal: LiveTerminalNotice | null
  transportPlan: { kind: string; turnRequired: boolean | null; operatorStreamPath: string | null } | null
  /** establish 响应一次性下发；此后只保存在内存，不落 localStorage。 */
  sessionToken: string | null
}

const TIER_VALUES: readonly LiveTier[] = ['JPEG_PREVIEW', 'INTERACTIVE_REMOTE', 'WEBRTC']
const TRANSPORT_VALUES: readonly LiveTransport[] = ['JPEG_WS', 'WEBRTC']
const UI_LABEL_VALUES = ['preview', 'interactive', 'interactive-hd'] as const

/**
 * K13 §1/§7：uiLabel / allowsInput / turnRequired 是档位派生常量（schema const 钉死）。
 * 本表是档位 → 派生常量的唯一 Web 侧参照，用于与服务端回传做一致性核对；
 * 服务端信封才是事实来源，本表只用来「拒绝不一致时升格输入权限」的 fail-closed 判定。
 */
export const TIER_DERIVED_CONSTANTS: Record<LiveTier, { allowsInput: boolean; uiLabel: (typeof UI_LABEL_VALUES)[number]; turnRequired: boolean }> = {
  JPEG_PREVIEW: { allowsInput: false, uiLabel: 'preview', turnRequired: false },
  INTERACTIVE_REMOTE: { allowsInput: true, uiLabel: 'interactive', turnRequired: false },
  WEBRTC: { allowsInput: true, uiLabel: 'interactive-hd', turnRequired: true },
}

/** 档位徽标（如实标档）：以服务端 capabilities.uiLabel 对齐 K13，缺失回退档位派生，再缺失如实标「未知」。 */
export function tierUiLabelOf(session: Pick<LiveSession, 'tier' | 'capabilities'>): string {
  const fromServer = session.capabilities.uiLabel
  if (fromServer && UI_LABEL_VALUES.includes(fromServer)) return fromServer
  if (session.tier && TIER_VALUES.includes(session.tier)) return TIER_DERIVED_CONSTANTS[session.tier].uiLabel
  return 'unknown'
}

export const TIER_UI_LABELS: Record<string, string> = {
  preview: 'JPEG 预览 · 只读观察',
  interactive: '交互远控 · JPEG 传输',
  'interactive-hd': '交互远控 · WebRTC 高清',
  unknown: '档位未知 · 按只读处理',
}

export function tierBadgeLabelOf(session: Pick<LiveSession, 'tier' | 'capabilities'>): string {
  return TIER_UI_LABELS[tierUiLabelOf(session)] ?? TIER_UI_LABELS.unknown
}

/**
 * 输入通道判定（fail-closed）：仅当 服务端 allowsInput === true 且（档位已知时）
 * 与 K13 档位派生常量一致，才认为输入通道开放。档位未知或信封不一致 → 按只读处理。
 * 「有图片」永远不是「可远控」的依据。
 */
export function inputChannelOpen(session: Pick<LiveSession, 'tier' | 'capabilities'>): boolean {
  if (session.capabilities.allowsInput !== true) return false
  if (session.tier && TIER_VALUES.includes(session.tier)) {
    return TIER_DERIVED_CONSTANTS[session.tier].allowsInput === true
  }
  return false
}

/** 服务端能力信封与 K13 档位派生常量的一致性（仅用于如实告警，不改变 fail-closed 判定）。 */
export function tierEnvelopeCoherent(session: Pick<LiveSession, 'tier' | 'capabilities'>): boolean {
  if (!session.tier || !TIER_VALUES.includes(session.tier)) return session.capabilities.uiLabel == null
  const derived = TIER_DERIVED_CONSTANTS[session.tier]
  const cap = session.capabilities
  if (cap.allowsInput != null && cap.allowsInput !== derived.allowsInput) return false
  if (cap.uiLabel != null && cap.uiLabel !== derived.uiLabel) return false
  if (cap.turnRequired != null && cap.turnRequired !== derived.turnRequired) return false
  return true
}

export function mapLiveSession(raw: Record<string, unknown>): LiveSession {
  const capabilitiesRaw = objectValue(raw.capabilities)
  const authorizationRaw = objectValue(raw.authorization)
  const leaseRaw = objectValue(raw.lease)
  const geometryRaw = objectValue(raw.frameGeometry)
  const terminalRaw = objectValue(raw.terminal)
  const planRaw = objectValue(raw.transportPlan)
  const detailsRaw = objectValue(planRaw.details)
  const tier = stringOrNull(raw.tier)
  const transport = stringOrNull(raw.transport)
  const uiLabel = stringOrNull(capabilitiesRaw.uiLabel)
  const policyRaw = raw.inputPolicy === false || raw.inputPolicy == null ? null : objectValue(raw.inputPolicy)
  return {
    sessionId: stringValue(raw.sessionId, ''),
    tenantId: stringOrNull(raw.tenantId),
    deviceId: stringValue(raw.deviceId, ''),
    operatorId: stringOrNull(raw.operatorId),
    tier: tier && TIER_VALUES.includes(tier as LiveTier) ? (tier as LiveTier) : null,
    transport: transport && TRANSPORT_VALUES.includes(transport as LiveTransport) ? (transport as LiveTransport) : null,
    state: raw.state === 'REMOTE' ? 'REMOTE' : raw.state === 'CLOSED' ? 'CLOSED' : 'VIEWING',
    lease: {
      deviceLeaseId: stringOrNull(leaseRaw.deviceLeaseId),
      epoch: numberOrNull(leaseRaw.epoch),
      purpose: 'LIVE',
    },
    frameGeometry: {
      frameWidth: numberOrNull(geometryRaw.frameWidth) ?? 0,
      frameHeight: numberOrNull(geometryRaw.frameHeight) ?? 0,
      deviceWidth: numberOrNull(geometryRaw.deviceWidth) ?? 0,
      deviceHeight: numberOrNull(geometryRaw.deviceHeight) ?? 0,
      rotation: (rotationOrNull(geometryRaw.rotation) ?? 0) as 0 | 90 | 180 | 270,
      safeArea: mapSafeArea(geometryRaw.safeArea),
    },
    capabilities: {
      allowsInput: booleanOrNull(capabilitiesRaw.allowsInput),
      uiLabel: uiLabel && (UI_LABEL_VALUES as readonly string[]).includes(uiLabel) ? (uiLabel as LiveCapabilities['uiLabel']) : null,
      frameDownlink: booleanOrNull(capabilitiesRaw.frameDownlink),
      turnRequired: booleanOrNull(capabilitiesRaw.turnRequired),
    },
    inputPolicy: policyRaw
      ? {
          maxInputRatePerSecond: numberOrNull(policyRaw.maxInputRatePerSecond) ?? 10,
          ttlExpiryMs: numberOrNull(policyRaw.ttlExpiryMs) ?? 2000,
          staleFrameThreshold: numberOrNull(policyRaw.staleFrameThreshold) ?? 10,
        }
      : null,
    authorization: {
      mediaProjectionRequired: authorizationRaw.mediaProjectionRequired !== false,
      userConfirmedAt: stringOrNull(authorizationRaw.userConfirmedAt),
      persistsAcrossReboot: authorizationRaw.persistsAcrossReboot === true,
      silentResumeAllowed: authorizationRaw.silentResumeAllowed === true,
    },
    establishedAt: stringOrNull(raw.establishedAt),
    expiresAt: stringOrNull(raw.expiresAt),
    maxDurationMinutes: numberOrNull(raw.maxDurationMinutes),
    terminal: objectKeys(terminalRaw).length
      ? {
          cause: stringValue(terminalRaw.cause, 'UNKNOWN'),
          resumable: terminalRaw.resumable === true,
          reauthorizationRequired: terminalRaw.reauthorizationRequired !== false,
          tokenInvalidated: terminalRaw.tokenInvalidated !== false,
          closedAt: stringOrNull(terminalRaw.closedAt),
        }
      : null,
    transportPlan:
      objectKeys(planRaw).length > 0
        ? {
            kind: stringValue(planRaw.kind, ''),
            turnRequired: booleanOrNull(planRaw.turnRequired),
            operatorStreamPath: stringOrNull(detailsRaw.operatorStreamPath),
          }
        : null,
    sessionToken: stringOrNull(raw.sessionToken),
  }
}

export function mapHandover(raw: unknown, fallback: { sessionId: string; deviceId: string }): HandoverReceipt | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null
  const row = raw as JsonObject
  const affected = Array.isArray(row.affectedTasks)
    ? row.affectedTasks
        .map((task) => {
          const entry = objectValue(task)
          const taskId = stringOrNull(entry.taskId)
          if (!taskId) return null
          return {
            taskId,
            pauseState: stringValue(entry.pauseState, 'PAUSED_WAITING_USER'),
            resumeMode: entry.resumeMode === 'CONFIRM_REQUIRED' ? 'CONFIRM_REQUIRED' : 'REQUEUE_AUTO',
          } satisfies LiveHandoverTask
        })
        .filter((task): task is LiveHandoverTask => task !== null)
    : []
  return {
    sessionId: stringOrNull(row.sessionId) ?? fallback.sessionId,
    deviceId: stringOrNull(row.deviceId) ?? fallback.deviceId,
    tier: (stringOrNull(row.tier) as LiveTier | null) ?? null,
    from: stringValue(row.from, 'REMOTE'),
    to: stringValue(row.to, 'VIEWING'),
    affectedTasks: affected,
    singleWriterRestored: row.singleWriterRestored === true,
    frameDownlinkContinues: row.frameDownlinkContinues === true,
    releasedAt: stringOrNull(row.releasedAt) ?? '',
    releasedBy: stringOrNull(row.releasedBy) ?? '',
  }
}

export function resumeModeLabel(mode: LiveHandoverTask['resumeMode']): string {
  return mode === 'CONFIRM_REQUIRED' ? '需人工确认后才恢复（禁止自动恢复）' : '自动回队列'
}

// ---------------------------------------------------------------------------
// K13 §3 坐标变换（纯函数；金样测试对齐契约逆变换表）
// ---------------------------------------------------------------------------

export interface Size {
  width: number
  height: number
}

export interface FramePoint {
  fx: number
  fy: number
}

export interface DevicePoint {
  dx: number
  dy: number
}

/**
 * object-fit: contain 语义：帧在展示视口里的实际显示矩形。
 * scale = min(vw/frameW, vh/frameH)；留黑 = 视口减去显示矩形后的对称偏移。
 */
export function letterboxFrameRect(
  viewport: Size,
  geometry: Pick<FrameGeometry, 'frameWidth' | 'frameHeight'>,
): { scale: number; offsetX: number; offsetY: number; width: number; height: number } {
  if (viewport.width <= 0 || viewport.height <= 0 || geometry.frameWidth <= 0 || geometry.frameHeight <= 0) {
    return { scale: 0, offsetX: 0, offsetY: 0, width: 0, height: 0 }
  }
  const scale = Math.min(viewport.width / geometry.frameWidth, viewport.height / geometry.frameHeight)
  const width = geometry.frameWidth * scale
  const height = geometry.frameHeight * scale
  return { scale, offsetX: (viewport.width - width) / 2, offsetY: (viewport.height - height) / 2, width, height }
}

/**
 * 视口 CSS 像素 → 帧空间坐标（K13 §3：input 坐标一律以帧空间为准）。
 * 点击落在留黑区 → null：丢弃，不猜测、不钳到帧边缘。
 */
export function viewportPointToFrame(x: number, y: number, viewport: Size, geometry: Pick<FrameGeometry, 'frameWidth' | 'frameHeight'>): FramePoint | null {
  // fail-closed：非有限输入（畸形指针事件等）直接丢弃，NaN 比较恒为 false 会绕过边界检查。
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  const rect = letterboxFrameRect(viewport, geometry)
  if (rect.scale <= 0) return null
  const fx = (x - rect.offsetX) / rect.scale
  const fy = (y - rect.offsetY) / rect.scale
  if (fx < 0 || fy < 0 || fx >= geometry.frameWidth || fy >= geometry.frameHeight) return null
  return { fx: round3(fx), fy: round3(fy) }
}

/**
 * K13 §3 严格逆变换（帧空间 → 设备空间），查表对齐契约：
 *   1. 逆缩放：u = fx·uw/frameWidth，v = fy·uh/frameHeight
 *      （uw,uh) = rotation∈{0,180} ? (deviceWidth,deviceHeight) : (deviceHeight,deviceWidth)
 *   2. 逆旋转：0 → (u,v)；180 → (uw−1−u, uh−1−v)；90 → (v, uw−1−u)；270 → (uh−1−v, u)
 *   3. 四舍五入到设备像素
 *   4. 越界或 safeArea 排除区 → null（丢弃，禁止静默钳位）
 *
 * 职责切分注意（K13 §3）：Companion 持有产帧变换核并执行严格逆；Web 只提交帧空间坐标。
 * 本函数是契约公式的镜像实现，仅用于（a）金样测试验证提交坐标落点、（b）客户端安全区
 * 预检提示；它绝不参与 input 序列化——提交体里永远只有帧空间坐标 + frameSeq。
 */
export function frameToDevice(point: FramePoint, geometry: FrameGeometry): DevicePoint | null {
  const { frameWidth, frameHeight, deviceWidth, deviceHeight, rotation } = geometry
  // fail-closed：非有限坐标直接丢弃（NaN 与任何边界比较均为 false，必须显式拦截）。
  if (!Number.isFinite(point.fx) || !Number.isFinite(point.fy)) return null
  if (frameWidth <= 0 || frameHeight <= 0 || deviceWidth <= 0 || deviceHeight <= 0) return null
  if (point.fx < 0 || point.fy < 0 || point.fx >= frameWidth || point.fy >= frameHeight) return null
  const uw = rotation === 0 || rotation === 180 ? deviceWidth : deviceHeight
  const uh = rotation === 0 || rotation === 180 ? deviceHeight : deviceWidth
  const u = (point.fx * uw) / frameWidth
  const v = (point.fy * uh) / frameHeight
  let dx: number
  let dy: number
  if (rotation === 0) {
    dx = u
    dy = v
  } else if (rotation === 180) {
    dx = uw - 1 - u
    dy = uh - 1 - v
  } else if (rotation === 90) {
    dx = v
    dy = uw - 1 - u
  } else {
    dx = uh - 1 - v
    dy = u
  }
  const rx = Math.round(dx)
  const ry = Math.round(dy)
  if (rx < 0 || ry < 0 || rx >= deviceWidth || ry >= deviceHeight) return null
  if (inSafeAreaExclusion(rx, ry, geometry)) return null
  return { dx: rx, dy: ry }
}

/** safeArea 是设备空间内缩排除带：命中即丢弃（K13 §3 第 4 步）。 */
export function inSafeAreaExclusion(dx: number, dy: number, geometry: Pick<FrameGeometry, 'deviceWidth' | 'deviceHeight' | 'safeArea'>): boolean {
  const safe = geometry.safeArea
  if (!safe) return false
  return dx < safe.left || dy < safe.top || dx >= geometry.deviceWidth - safe.right || dy >= geometry.deviceHeight - safe.bottom
}

// ---------------------------------------------------------------------------
// 帧游标与输入闸门（K13 §4 水位规则的客户端镜像；服务端仍是唯一裁决者）
// ---------------------------------------------------------------------------

/** 当前展示帧的游标：seq 来源如实标注（transport 下发或本地计数，绝不冒充服务端水位）。 */
export interface FrameCursor {
  seq: number
  receivedAtMs: number
  seqSource: 'transport' | 'local-count'
}

export type InputGateReason =
  | 'NO_SESSION'
  | 'SESSION_TERMINAL'
  | 'TIER_READ_ONLY'
  | 'NOT_REMOTE'
  | 'TRANSPORT_DISCONNECTED'
  | 'NO_FRAME'
  | 'FRAME_STALE_SEQ'
  | 'FRAME_STALE_TTL'

export interface InputGate {
  allowed: boolean
  reason: InputGateReason | null
  hint: string
}

/**
 * 危险交互总闸门（fail-closed）。判定顺序对齐 K13 拒收规则的精神：
 * 档位只读 → 非终态检查 → 非 REMOTE → 断流 → 无帧 → 帧序过期 → 帧 TTL 过期。
 * 任何未知（策略缺失、帧游标缺失）一律不放行。
 */
export function inputGate(params: {
  session: LiveSession | null
  frame: FrameCursor | null
  transportConnected: boolean
  /** 已知的服务端最新帧水位（input 响应 / 拒收 problem fields 回带）；null = 未知，跳过 seq 距离判定。 */
  serverLatestFrameSeq: number | null
  nowMs?: number
}): InputGate {
  const { session, frame, transportConnected, serverLatestFrameSeq } = params
  const nowMs = params.nowMs ?? Date.now()
  if (!session) return deny('NO_SESSION', '尚无活动会话')
  if (session.terminal || session.state === 'CLOSED') return deny('SESSION_TERMINAL', '会话已终态，交互通道关闭')
  if (!inputChannelOpen(session)) return deny('TIER_READ_ONLY', '只读档位无输入通道（K13：JPEG_PREVIEW 禁止 input）')
  if (session.state !== 'REMOTE') return deny('NOT_REMOTE', '未处于 REMOTE 态，无点击权限')
  if (!transportConnected) return deny('TRANSPORT_DISCONNECTED', '帧通道已断开，交互立即禁用')
  if (!frame || frame.seq < 1) return deny('NO_FRAME', '尚无可参照的帧，拒绝猜测坐标')
  const policy = session.inputPolicy
  if (policy) {
    if (serverLatestFrameSeq != null && serverLatestFrameSeq - frame.seq > policy.staleFrameThreshold) {
      return deny('FRAME_STALE_SEQ', `帧序落后服务端水位超过 ${policy.staleFrameThreshold}（当前 ${frame.seq} / 服务端 ${serverLatestFrameSeq}）`)
    }
    if (nowMs - frame.receivedAtMs > policy.ttlExpiryMs) {
      return deny('FRAME_STALE_TTL', `帧龄超过 ${policy.ttlExpiryMs}ms 手势 TTL，旧帧上不允许危险交互`)
    }
  } else {
    // 无策略回传（服务端必回 inputPolicy 于输入档）→ fail-closed。
    return deny('NO_FRAME', '服务端未回传 inputPolicy，按不可交互处理')
  }
  return { allowed: true, reason: null, hint: '' }
}

function deny(reason: InputGateReason, hint: string): InputGate {
  return { allowed: false, reason, hint }
}

// ---------------------------------------------------------------------------
// 面板状态呈现（各状态明确，不以「有图片」当「可远控」）
// ---------------------------------------------------------------------------

export type LivePanelStatus =
  | 'IDLE'
  | 'AWAITING_PROJECTION_ACK'
  | 'WAITING_FRAME'
  | 'VIEWING'
  | 'REMOTE'
  | 'STALE_FRAME'
  | 'DISCONNECTED'
  | 'TERMINAL'

/** 预览无输入 TTL，5 秒只作画面停滞提示，不改变服务端会话与租约。 */
const PREVIEW_STALE_AFTER_MS = 5000

/** 帧龄仅表示本浏览器距收帧的时间，不是采集到显示的端到端延迟。 */
export function frameAgeMs(frame: FrameCursor | null, nowMs: number): number | null {
  if (!frame || !Number.isFinite(frame.receivedAtMs) || !Number.isFinite(nowMs)) return null
  return Math.max(0, nowMs - frame.receivedAtMs)
}

/** 授权提示优先保留；授权后所有档位都按实际通道与帧状态呈现。 */
export function panelStatus(
  session: LiveSession | null,
  frame: FrameCursor | null,
  transportConnected: boolean,
  serverLatestFrameSeq: number | null = null,
  nowMs: number = Date.now(),
): LivePanelStatus {
  if (!session) return 'IDLE'
  if (session.terminal || session.state === 'CLOSED') return 'TERMINAL'
  if (session.authorization.userConfirmedAt == null) return 'AWAITING_PROJECTION_ACK'
  if (!transportConnected) return 'DISCONNECTED'
  const age = frameAgeMs(frame, nowMs)
  if (!frame || !Number.isInteger(frame.seq) || frame.seq < 1 || age == null) return 'WAITING_FRAME'
  const policy = session.inputPolicy
  if (age > (policy?.ttlExpiryMs ?? PREVIEW_STALE_AFTER_MS)) return 'STALE_FRAME'
  if (policy && serverLatestFrameSeq != null && serverLatestFrameSeq - frame.seq > policy.staleFrameThreshold) return 'STALE_FRAME'
  return session.state === 'REMOTE' ? 'REMOTE' : 'VIEWING'
}

export const PANEL_STATUS_LABELS: Record<LivePanelStatus, string> = {
  IDLE: '未开始',
  AWAITING_PROJECTION_ACK: '等待手机确认投屏授权',
  WAITING_FRAME: '已授权，等待画面到达',
  VIEWING: '观察中（VIEWING）',
  REMOTE: '远控中（REMOTE）',
  STALE_FRAME: '旧帧 / 低帧率，危险交互已禁用',
  DISCONNECTED: '帧通道断开，交互已禁用',
  TERMINAL: '会话已终态（CLOSED）',
}

// ---------------------------------------------------------------------------
// 交还 ack 本地记录（K13 §5；localStorage 键按 sessionId 隔离）
// ---------------------------------------------------------------------------

const HANDOVER_ACK_KEY_PREFIX = 'cloudctl.live.handoverAck.'

export function handoverAckKey(sessionId: string): string {
  return `${HANDOVER_ACK_KEY_PREFIX}${sessionId}`
}

function safeStorage(): Storage | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage
  } catch {
    return null
  }
}

/** 交还成功后写本地 ack 记录；返回是否写入成功（无 localStorage 环境如实返回 false，不抛错）。 */
export function saveHandoverAck(receipt: HandoverReceipt, storage: Storage | null = safeStorage()): boolean {
  if (!storage) return false
  try {
    storage.setItem(handoverAckKey(receipt.sessionId), JSON.stringify(receipt))
    return true
  } catch {
    return false
  }
}

export function loadHandoverAck(sessionId: string, storage: Storage | null = safeStorage()): HandoverReceipt | null {
  if (!storage) return null
  try {
    const raw = storage.getItem(handoverAckKey(sessionId))
    if (!raw) return null
    return mapHandover(JSON.parse(raw), { sessionId, deviceId: '' })
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// input 序号与限速（K13 §4：seq 严格递增、≤10/秒，客户端镜像预检）
// ---------------------------------------------------------------------------

/** input seq：会话内严格递增，从 1 开始；服务端按 inputWatermark 拒收回退。 */
export function nextInputSeq(current: number): number {
  return current + 1
}

/** 限速器（滑动 1 秒窗）；超限返回 false —— 由调用方放弃发送，服务端 429 会直接断 REMOTE。 */
export function createInputRateLimiter(maxPerSecond: number): () => boolean {
  let stamps: number[] = []
  return () => {
    const now = Date.now()
    stamps = stamps.filter((stamp) => now - stamp < 1000)
    if (stamps.length >= maxPerSecond) return false
    stamps.push(now)
    return true
  }
}

/** K13 §9 problem code → 操作者可读提示（占用/终态/过期各自明确）。 */
export function liveProblemHint(code: string, status: number): string {
  switch (code) {
    case 'LIVE_SESSION_EXISTS':
      return '该设备已有进行中的投屏会话（可能被其他执行者占用）；需先结束旧会话再发起'
    case 'LIVE_REMOTE_HELD':
      return '远控写租约被其他会话持有（先到先得）；需对方交还或会话结束后再接管'
    case 'LIVE_AUTH_REQUIRED':
      return '手机尚未确认投屏授权（MediaProjection）；需现场用户确认后才能接管'
    case 'LIVE_SESSION_TERMINAL':
      return '会话已终态（重启/撤销授权/超时均为终态）；必须重新发起会话并重新系统授权，旧会话不可恢复'
    case 'LIVE_INPUT_FORBIDDEN':
      return '只读档或非 REMOTE 态：输入被服务端拒收（会话保持）'
    case 'INPUT_EXPIRED':
      return '手势过期（帧序过旧或超 TTL）；服务端已拒收，请在新帧上操作'
    case 'INPUT_SEQ_REGRESSION':
      return '输入序号回退/重复；服务端已拒收（短窗多次会断开 REMOTE）'
    case 'LIVE_RATE_LIMITED':
      return '输入超速（>10/秒）；服务端已断开 REMOTE，请重新接管'
    case 'LIVE_EPOCH_STALE':
      return '会话 epoch 已过期（租约换代）；当前会话上的旧操作被拒'
    case 'LIVE_TIER_UNSUPPORTED':
      return '档位 × 传输组合非法或租户未开放该档'
    case 'LIVE_TURN_UNAVAILABLE':
      return 'WEBRTC 档 TURN 不可用；服务端拒绝建档（不静默降档）'
    case 'AUTHENTICATION_REQUIRED':
      return '会话令牌无效或缺失；请重新发起会话'
    default:
      return `请求失败（HTTP ${status}）`
  }
}

// ---------------------------------------------------------------------------
// 内部小工具（保守解析，不发明值）
// ---------------------------------------------------------------------------

function stringValue(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function booleanOrNull(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function rotationOrNull(value: unknown): 0 | 90 | 180 | 270 | null {
  return value === 0 || value === 90 || value === 180 || value === 270 ? value : null
}

function objectValue(value: unknown): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as JsonObject) : {}
}

function objectKeys(value: JsonObject): string[] {
  return Object.keys(value)
}

function mapSafeArea(value: unknown): SafeAreaInsets | null {
  const raw = objectValue(value)
  if (objectKeys(raw).length === 0) return null
  return {
    left: numberOrNull(raw.left) ?? 0,
    top: numberOrNull(raw.top) ?? 0,
    right: numberOrNull(raw.right) ?? 0,
    bottom: numberOrNull(raw.bottom) ?? 0,
  }
}

function round3(value: number): number {
  return Math.round(value * 1000) / 1000
}
