import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JsonObject } from '@cloudctl/api-contracts'
import { createMemoryHistory, createRouter } from 'vue-router'
import {
  createInputRateLimiter,
  frameToDevice,
  handoverAckKey,
  inputChannelOpen,
  inputGate,
  letterboxFrameRect,
  loadHandoverAck,
  mapLiveSession,
  nextInputSeq,
  panelStatus,
  resumeModeLabel,
  saveHandoverAck,
  tierBadgeLabelOf,
  tierEnvelopeCoherent,
  tierUiLabelOf,
  viewportPointToFrame,
  type FrameCursor,
  type FrameGeometry,
  type LiveSession,
} from '@/features/live/model'
import { liveFleetRoutes, registerLiveFleetRoutes } from '@/features/live/routes'
import LiveFleetPanelView from '@/features/live/LiveFleetPanelView.vue'

// ---------------------------------------------------------------------------
// API / 环境 mock（模式对齐 tests/reconciliation.spec.ts）
// ---------------------------------------------------------------------------

const { flags } = vi.hoisted(() => ({
  flags: { configured: true },
}))

vi.mock('@/api/control', () => ({
  get controlApiConfigured() {
    return flags.configured
  },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
}))

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  send(data: string): void {
    this.sent.push(data)
  }
  close(): void {
    this.onclose?.()
  }
  open(): void {
    this.onopen?.()
  }
  frame(jpeg: string, seq?: number): void {
    const payload: Record<string, unknown> = { t: 'frame', jpeg }
    if (seq !== undefined) payload.seq = seq
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

// ---------------------------------------------------------------------------
// 服务端载荷 fixture（对齐 L10 fleet_live.view() + K13 fixtures 字段形状）
// ---------------------------------------------------------------------------

const SID = 'live-0f1e2d3c'
const DEVICE = 'dev-a11'

function sessionPayload(overrides: JsonObject = {}): JsonObject {
  return {
    sessionId: SID,
    tenantId: 'tn-01',
    deviceId: DEVICE,
    operatorId: 'op-77',
    tier: 'INTERACTIVE_REMOTE',
    transport: 'JPEG_WS',
    state: 'VIEWING',
    lease: { deviceLeaseId: 'dl-9c2f', epoch: 4, purpose: 'LIVE' },
    frameGeometry: {
      frameWidth: 405,
      frameHeight: 720,
      deviceWidth: 1080,
      deviceHeight: 1920,
      rotation: 0,
      safeArea: { left: 0, top: 84, right: 0, bottom: 0 },
    },
    capabilities: { allowsInput: true, uiLabel: 'interactive', frameDownlink: true, turnRequired: false },
    inputPolicy: { maxInputRatePerSecond: 10, ttlExpiryMs: 2000, staleFrameThreshold: 10 },
    authorization: {
      mediaProjectionRequired: true,
      userConfirmedAt: '2026-09-17T09:15:00+08:00',
      persistsAcrossReboot: false,
      silentResumeAllowed: false,
    },
    establishedAt: '2026-09-17T09:15:02+08:00',
    expiresAt: '2026-09-17T09:45:02+08:00',
    maxDurationMinutes: 30,
    transportPlan: {
      kind: 'JPEG_WS',
      turnRequired: false,
      details: { operatorStreamPath: `/api/v1/devices/${DEVICE}/live/${SID}/stream` },
    },
    ...overrides,
  }
}

const GEOMETRY_BASE: FrameGeometry = {
  frameWidth: 405,
  frameHeight: 720,
  deviceWidth: 1080,
  deviceHeight: 1920,
  rotation: 0,
  safeArea: null,
}

function geometry(overrides: Partial<FrameGeometry> = {}): FrameGeometry {
  return { ...GEOMETRY_BASE, ...overrides }
}

// ---------------------------------------------------------------------------
// fetch 路由：按 method + URL 后缀分发
// ---------------------------------------------------------------------------

type FetchCall = { url: string; method: string; body: Record<string, unknown> | null }

let calls: FetchCall[] = []
let handlers: ((call: FetchCall) => Response | null)[] = []

function prime(handler: (call: FetchCall) => Response | null): void {
  handlers.push(handler)
}

function fetchMock(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input)
  const rawBody = typeof init?.body === 'string' ? init.body : null
  const call: FetchCall = { url, method: init?.method ?? 'GET', body: rawBody ? (JSON.parse(rawBody) as Record<string, unknown>) : null }
  calls.push(call)
  for (const handler of handlers) {
    const response = handler(call)
    if (response) return Promise.resolve(response)
  }
  return Promise.resolve(jsonResponse({ detail: `no fetch handler for ${call.method} ${call.url}` }, 500))
}

function callsTo(suffix: string, method?: string): FetchCall[] {
  return calls.filter((call) => call.url.endsWith(suffix) && (method === undefined || call.method === method))
}

beforeEach(() => {
  calls = []
  handlers = []
  FakeWebSocket.instances = []
  vi.stubGlobal('fetch', vi.fn(fetchMock))
  vi.stubGlobal('WebSocket', FakeWebSocket)
  // jsdom 无 PointerEvent：fireEvent.pointerDown 会退化成 new Event()，clientX/clientY
  // 被 Event 构造器丢弃。用 MouseEvent 顶上，保证指针坐标可传递。
  vi.stubGlobal('PointerEvent', MouseEvent)
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// 面板驱动工具
// ---------------------------------------------------------------------------

function primeEstablish(overrides: JsonObject = {}): void {
  prime((call) => (call.method === 'POST' && call.url.endsWith(`/api/v1/live/devices/${DEVICE}/sessions`) ? jsonResponse({ ...sessionPayload(), sessionToken: 'tok-1', ...overrides }, 201) : null))
  prime((call) => (call.method === 'GET' && call.url.endsWith(`/api/v1/live/sessions/${SID}`) ? jsonResponse(sessionPayload(overrides)) : null))
}

async function openPanel(opts: { tier?: 'JPEG_PREVIEW' | 'INTERACTIVE_REMOTE'; establishOverrides?: JsonObject } = {}): Promise<void> {
  primeEstablish(opts.establishOverrides)
  render(LiveFleetPanelView)
  await fireEvent.update(screen.getByTestId('live-device-id'), DEVICE)
  const tier = opts.tier ?? 'INTERACTIVE_REMOTE'
  if (tier !== 'JPEG_PREVIEW') await fireEvent.click(screen.getByTestId(`live-tier-${tier}`))
  await fireEvent.click(screen.getByTestId('live-btn-establish'))
  await screen.findByTestId('live-status-badge')
  const socket = FakeWebSocket.instances.at(-1)
  socket?.open()
}

async function goToRemote(): Promise<void> {
  await injectFrame(1)
  prime((call) => (call.method === 'POST' && call.url.endsWith(`:take-control`) ? jsonResponse(sessionPayload({ state: 'REMOTE' })) : null))
  await fireEvent.click(await screen.findByTestId('live-btn-take-control'))
  await waitFor(() => expect(screen.getByTestId('live-state-badge').textContent).toBe('REMOTE'))
}

function mockViewportRect(width: number, height: number): void {
  const viewport = screen.getByTestId('live-frame-viewport') as HTMLElement
  vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({
    x: 0, y: 0, top: 0, left: 0, right: width, bottom: height, width, height, toJSON: () => ({}),
  } as DOMRect)
}

async function injectFrame(seq: number): Promise<void> {
  FakeWebSocket.instances.at(-1)?.frame('aGVsbG8', seq)
  await waitFor(() => expect(screen.getByTestId('live-frame-cursor').textContent).toContain(String(seq)))
}

function primeInput(result: { accepted: boolean; inputWatermark: number; latestFrameSeq: number } | { status: number; code: string; detail?: string; fields?: Record<string, string> }): void {
  prime((call) => {
    if (!call.url.endsWith(`/sessions/${SID}/input`) || call.method !== 'POST') return null
    if ('accepted' in result) return jsonResponse(result)
    return jsonResponse({ code: result.code, detail: result.detail ?? 'rejected', fields: result.fields ?? {} }, result.status)
  })
}

// ===========================================================================
// 一、缩放 / 旋转 / letterbox / 安全区 金样（对齐 K13 §3 逆变换）
// ===========================================================================

describe('L12 coordinate goldens (K13 §3)', () => {
  it('letterbox: object-fit contain 语义的显示矩形（整数缩放 + 非整数留黑）', () => {
    // 810×1440 视口装 405×720 帧：scale=2，无留黑。
    const exact = letterboxFrameRect({ width: 810, height: 1440 }, GEOMETRY_BASE)
    expect(exact).toEqual({ scale: 2, offsetX: 0, offsetY: 0, width: 810, height: 1440 })
    // 1000×1000 方形视口：scale=1000/720=1.3888…，左右各留 218.75。
    const boxed = letterboxFrameRect({ width: 1000, height: 1000 }, GEOMETRY_BASE)
    expect(boxed.width).toBeCloseTo(562.5, 10)
    expect(boxed.offsetX).toBeCloseTo(218.75, 10)
    expect(boxed.offsetY).toBe(0)
    expect(boxed.height).toBe(1000)
  })

  it('viewport → frame：视口像素去留黑后按比例映射；留黑区/帧外/非有限输入返回 null（不猜测）', () => {
    // 视口 810×1440 = 帧 405×720 的 2 倍：视口中心 (405,720) → 帧中心 (202.5,360)。
    expect(viewportPointToFrame(405, 720, { width: 810, height: 1440 }, GEOMETRY_BASE)).toEqual({ fx: 202.5, fy: 360 })
    expect(viewportPointToFrame(0, 0, { width: 810, height: 1440 }, GEOMETRY_BASE)).toEqual({ fx: 0, fy: 0 })
    // fx=810/2=405 = frameWidth，落在 [0, frameWidth) 之外 → 丢弃。
    expect(viewportPointToFrame(810, 1440, { width: 810, height: 1440 }, GEOMETRY_BASE)).toBeNull()
    // 1000 宽视口：x=218.75 是帧左边缘，x=100 在留黑区 → null。
    expect(viewportPointToFrame(218.75, 500, { width: 1000, height: 1000 }, GEOMETRY_BASE)).toEqual({ fx: 0, fy: 360 })
    expect(viewportPointToFrame(100, 500, { width: 1000, height: 1000 }, GEOMETRY_BASE)).toBeNull()
    expect(viewportPointToFrame(999, 500, { width: 1000, height: 1000 }, GEOMETRY_BASE)).toBeNull()
    // 非有限输入（畸形指针事件）：fail-closed 丢弃，绝不产生 NaN 坐标提交。
    expect(viewportPointToFrame(Number.NaN, 360, { width: 810, height: 1440 }, GEOMETRY_BASE)).toBeNull()
    expect(frameToDevice({ fx: Number.NaN, fy: 360 }, GEOMETRY_BASE)).toBeNull()
  })

  it('frame → device 逆变换金样：0/90/180/270 帧中心点（K13 §3 查表公式的手算期望）', () => {
    // 手算：u = fx·uw/frameWidth, v = fy·uh/frameHeight，再按 rotation 查表。
    expect(frameToDevice({ fx: 202.5, fy: 360 }, geometry({ rotation: 0 }))).toEqual({ dx: 540, dy: 960 })
    expect(frameToDevice({ fx: 202.5, fy: 360 }, geometry({ rotation: 180 }))).toEqual({ dx: 539, dy: 959 })
    expect(frameToDevice({ fx: 202.5, fy: 360 }, geometry({ rotation: 90 }))).toEqual({ dx: 540, dy: 959 })
    expect(frameToDevice({ fx: 202.5, fy: 360 }, geometry({ rotation: 270 }))).toEqual({ dx: 539, dy: 960 })
  })

  it('frame → device 角点映射：四角对四角（连续坐标 (dim-1) 约定）', () => {
    // rotation=90：帧左上 → 设备左下；帧右下边界外 → 越界丢弃。
    expect(frameToDevice({ fx: 0, fy: 0 }, geometry({ rotation: 90 }))).toEqual({ dx: 0, dy: 1919 })
    expect(frameToDevice({ fx: 0, fy: 0 }, geometry({ rotation: 180 }))).toEqual({ dx: 1079, dy: 1919 })
    expect(frameToDevice({ fx: 0, fy: 0 }, geometry({ rotation: 270 }))).toEqual({ dx: 1079, dy: 0 })
    expect(frameToDevice({ fx: 405, fy: 360 }, geometry({ rotation: 90 }))).toBeNull()
    // rotation=0 内部点：404×1920/720→1077.33 四舍五入 1077；719×1920/720→1917.33→1917。
    expect(frameToDevice({ fx: 404, fy: 719 }, geometry({ rotation: 0 }))).toEqual({ dx: 1077, dy: 1917 })
  })

  it('安全区排除：设备空间内缩带内的落点丢弃，禁止静默钳到边缘（K13 §3 第 4 步）', () => {
    const withSafe = geometry({ safeArea: { left: 0, top: 84, right: 0, bottom: 0 } })
    // fy=15 → dy=40（状态栏内）→ 丢弃；fy=31.5 → dy=84（安全区起点）→ 放行。
    expect(frameToDevice({ fx: 202.5, fy: 15 }, withSafe)).toBeNull()
    expect(frameToDevice({ fx: 202.5, fy: 31.5 }, withSafe)).toEqual({ dx: 540, dy: 84 })
    // 无 safeArea 时不排除。
    expect(frameToDevice({ fx: 202.5, fy: 15 }, GEOMETRY_BASE)).toEqual({ dx: 540, dy: 40 })
  })

  it('全链路金样：视口点击 → 帧空间提交坐标 → K13 逆变换落点（web 只产帧坐标，设备坐标仅作验证）', () => {
    const point = viewportPointToFrame(405, 720, { width: 810, height: 1440 }, geometry({ rotation: 90 }))
    expect(point).toEqual({ fx: 202.5, fy: 360 })
    expect(frameToDevice(point!, geometry({ rotation: 90 }))).toEqual({ dx: 540, dy: 959 })
  })
})

// ===========================================================================
// 二、档位如实标识（预览 ≠ 远控；fail-closed）
// ===========================================================================

describe('L12 honest tier labels (K13 §1/§7)', () => {
  it('档位派生常量与服务端信封一致时按 uiLabel 标识；缺失回退档位派生；档位未知按只读处理', () => {
    const interactive = mapLiveSession(sessionPayload())
    expect(tierUiLabelOf(interactive)).toBe('interactive')
    expect(tierBadgeLabelOf(interactive)).toBe('交互远控 · JPEG 传输')
    expect(tierEnvelopeCoherent(interactive)).toBe(true)
    const noEnvelope = mapLiveSession(sessionPayload({ capabilities: {} }))
    expect(tierUiLabelOf(noEnvelope)).toBe('interactive')
    expect(inputChannelOpen(noEnvelope)).toBe(false)
    const unknown = mapLiveSession(sessionPayload({ tier: 'JPEG_PREVIEW', capabilities: { allowsInput: true, uiLabel: 'interactive' } }))
    // 预览档谎报 allowsInput=true：与 K13 派生常量矛盾 → 不一致 + 输入通道仍关。
    expect(tierEnvelopeCoherent(unknown)).toBe(false)
    expect(inputChannelOpen(unknown)).toBe(false)
    expect(tierUiLabelOf(unknown)).toBe('interactive')
  })

  it('预览会话面板：标「JPEG 预览 · 只读观察」，无接管按钮，画布不可交互，点击不产生 input', async () => {
    await openPanel({ tier: 'JPEG_PREVIEW', establishOverrides: sessionPayload({ tier: 'JPEG_PREVIEW', capabilities: { allowsInput: false, uiLabel: 'preview', frameDownlink: true, turnRequired: false }, inputPolicy: false }) })
    expect(screen.getByTestId('live-tier-badge').textContent).toBe('JPEG 预览 · 只读观察')
    expect(screen.queryByTestId('live-btn-take-control')).toBeNull()
    mockViewportRect(810, 1440)
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 360, pointerId: 1 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 360, pointerId: 1 })
    expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(0)
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true')
  })

  it('旁观会话（VIEWING）：不标远控中，画布禁用且原因明确', async () => {
    await openPanel()
    await injectFrame(1)
    expect(screen.getByTestId('live-status-badge').textContent).toBe('观察中（VIEWING）')
    expect(screen.getByTestId('live-status-badge').textContent).not.toContain('远控')
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true')
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 360, pointerId: 1 })
    expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(0)
  })

  it('REMOTE 态才显示完整远控标识；服务端信封与档位矛盾时如实告警并保持只读', async () => {
    await openPanel({ establishOverrides: sessionPayload({ tier: 'JPEG_PREVIEW', state: 'REMOTE', capabilities: { allowsInput: true, uiLabel: 'interactive' } }) })
    expect(screen.getByTestId('live-envelope-warning').textContent).toContain('不一致')
    expect(screen.queryByTestId('live-btn-take-control')).toBeNull()
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true')
    // 修正档位后（INTERACTIVE_REMOTE + REMOTE）才有完整远控标识。
    cleanup()
    await openPanel({ establishOverrides: sessionPayload({ state: 'REMOTE' }) })
    await injectFrame(1)
    expect(screen.getByTestId('live-tier-badge').textContent).toBe('交互远控 · JPEG 传输')
    expect(screen.getByTestId('live-status-badge').textContent).toBe('远控中（REMOTE）')
  })
})

// ===========================================================================
// 三、输入闸门：旧帧 / 低帧率 / 断连 / 授权待确认
// ===========================================================================

describe('L12 input gating (K13 §4 watermark mirror)', () => {
  const interactive = () => mapLiveSession(sessionPayload({ state: 'REMOTE' }))

  it('帧序落后服务端水位超过阈值 → 危险交互禁用', () => {
    const frame: FrameCursor = { seq: 100, receivedAtMs: Date.now(), seqSource: 'transport' }
    const fresh = inputGate({ session: interactive(), frame, transportConnected: true, serverLatestFrameSeq: 105 })
    expect(fresh.allowed).toBe(true)
    const stale = inputGate({ session: interactive(), frame, transportConnected: true, serverLatestFrameSeq: 130 })
    expect(stale.allowed).toBe(false)
    expect(stale.reason).toBe('FRAME_STALE_SEQ')
    expect(panelStatus(interactive(), frame, true, 130)).toBe('STALE_FRAME')
  })

  it('帧龄超过 TTL → 旧帧上不允许危险交互', () => {
    const now = Date.now()
    const frame: FrameCursor = { seq: 100, receivedAtMs: now - 2500, seqSource: 'transport' }
    const gate = inputGate({ session: interactive(), frame, transportConnected: true, serverLatestFrameSeq: null, nowMs: now })
    expect(gate.allowed).toBe(false)
    expect(gate.reason).toBe('FRAME_STALE_TTL')
  })

  it('无策略回传 / 无帧 / 断连 / 非 REMOTE / 只读档 → 全部 fail-closed', () => {
    const now = Date.now()
    const frame: FrameCursor = { seq: 1, receivedAtMs: now, seqSource: 'transport' }
    expect(inputGate({ session: mapLiveSession(sessionPayload({ state: 'REMOTE', inputPolicy: false })), frame, transportConnected: true, serverLatestFrameSeq: null, nowMs: now }).reason).toBe('NO_FRAME')
    expect(inputGate({ session: interactive(), frame: null, transportConnected: true, serverLatestFrameSeq: null, nowMs: now }).reason).toBe('NO_FRAME')
    expect(inputGate({ session: interactive(), frame, transportConnected: false, serverLatestFrameSeq: null, nowMs: now }).reason).toBe('TRANSPORT_DISCONNECTED')
    expect(inputGate({ session: mapLiveSession(sessionPayload({ state: 'VIEWING' })), frame, transportConnected: true, serverLatestFrameSeq: null, nowMs: now }).reason).toBe('NOT_REMOTE')
    expect(inputGate({ session: mapLiveSession(sessionPayload({ tier: 'JPEG_PREVIEW', state: 'REMOTE', capabilities: { allowsInput: false, uiLabel: 'preview' }, inputPolicy: false })), frame, transportConnected: true, serverLatestFrameSeq: null, nowMs: now }).reason).toBe('TIER_READ_ONLY')
    expect(inputGate({ session: mapLiveSession(sessionPayload({ state: 'CLOSED', terminal: { cause: 'DEVICE_REBOOT', resumable: false, reauthorizationRequired: true, tokenInvalidated: true, closedAt: '2026-09-17T09:30:00+08:00' } })), frame, transportConnected: true, serverLatestFrameSeq: null, nowMs: now }).reason).toBe('SESSION_TERMINAL')
  })

  it('组件：输入响应回带高水位后旧帧禁用危险交互（INPUT_EXPIRED 预防）', async () => {
    await openPanel()
    await goToRemote()
    await injectFrame(100)
    mockViewportRect(810, 1440)
    // 状态化水位：第一次输入回 latestFrameSeq=101（新鲜），第二次跳到 130（客户端没渲染到新帧）。
    let latest = 101
    prime((call) => {
      if (!call.url.endsWith(`/sessions/${SID}/input`) || call.method !== 'POST') return null
      const result = jsonResponse({ accepted: true, inputWatermark: callsTo(`/sessions/${SID}/input`, 'POST').length, latestFrameSeq: latest })
      latest = 130
      return result
    })
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 1 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 1 })
    await waitFor(() => expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(1))
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 2 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 2 })
    await waitFor(() => expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(2))
    // 服务端水位 130 vs 当前帧 100：差 30 > 阈值 10 → 危险交互禁用。
    await waitFor(() => expect(screen.getByTestId('live-status-badge').textContent).toBe('旧帧 / 低帧率，危险交互已禁用'))
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true')
    expect(screen.getByTestId('live-input-disabled-reason').textContent).toContain('帧序落后')
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 3 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 3 })
    expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(2)
  })

  it('组件：帧龄超 TTL（假时钟推进 2.6s）→ 危险交互禁用', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    await openPanel()
    await goToRemote()
    await injectFrame(50)
    mockViewportRect(810, 1440)
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('false')
    // 推进 2.6s：面板 500ms 时钟踩点重算 TTL → 帧龄 2.6s > 2.0s。
    await vi.advanceTimersByTimeAsync(2600)
    await waitFor(() => expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true'))
    expect(screen.getByTestId('live-input-disabled-reason').textContent).toContain('TTL')
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 1 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 1 })
    expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(0)
  })

  it('组件：需要手机授权（projection ack 待确认）明确呈现，且不误标远控', async () => {
    await openPanel({ establishOverrides: sessionPayload({ authorization: { mediaProjectionRequired: true, userConfirmedAt: null, persistsAcrossReboot: false, silentResumeAllowed: false } }) })
    expect(screen.getByTestId('live-auth-pending').textContent).toContain('等待设备现场确认投屏')
    expect(screen.getByTestId('live-status-badge').textContent).toBe('等待手机确认投屏授权')
    expect(screen.getByTestId('live-btn-take-control').getAttribute('title')).toContain('MediaProjection')
  })
})

// ===========================================================================
// 四、断连与占用 / 终态
// ===========================================================================

describe('parallel live status regressions', () => {
  it.each(['JPEG_PREVIEW', 'INTERACTIVE_REMOTE'] as const)('已授权的%s旁观会话断线不能继续标观察中', (tier) => {
    const session = mapLiveSession(sessionPayload({ tier }))
    expect(panelStatus(session, null, false)).toBe('DISCONNECTED')
  })

  it('已授权但没有首帧时明确等待画面，而不是观察中', () => {
    expect(panelStatus(mapLiveSession(sessionPayload()), null, true)).toBe('WAITING_FRAME')
  })

  it('预览没有inputPolicy也会提示长期未更新的画面', () => {
    const session = mapLiveSession(sessionPayload({ tier: 'JPEG_PREVIEW', inputPolicy: false }))
    const frame: FrameCursor = { seq: 1, receivedAtMs: 1000, seqSource: 'transport' }
    expect(panelStatus(session, frame, true, null, 6500)).toBe('STALE_FRAME')
    expect(panelStatus(session, frame, true, null, 1500)).toBe('VIEWING')
  })

  it('接管按钮在授权未确认时实际禁用且不发请求', async () => {
    await openPanel({ establishOverrides: { authorization: { mediaProjectionRequired: true, userConfirmedAt: null } } })
    await injectFrame(1)
    expect((screen.getByTestId('live-btn-take-control') as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(screen.getByTestId('live-btn-take-control'))
    expect(callsTo(':take-control', 'POST')).toHaveLength(0)
  })

  it('接管需要首帧，画面过期后禁用，新帧到达后恢复', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    await openPanel()
    const button = screen.getByTestId('live-btn-take-control') as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(screen.getByTestId('live-status-badge').textContent).toContain('等待画面')
    await injectFrame(1)
    expect(button.disabled).toBe(false)
    await vi.advanceTimersByTimeAsync(2600)
    expect(button.disabled).toBe(true)
    expect(screen.getByTestId('live-status-badge').textContent).toContain('旧帧')
    await fireEvent.click(button)
    expect(callsTo(':take-control', 'POST')).toHaveLength(0)
    await injectFrame(2)
    expect(button.disabled).toBe(false)
    expect(screen.getByTestId('live-status-badge').textContent).toBe('观察中（VIEWING）')
  })

  it('帧龄随时钟更新；旁观断线后不显示正常观察', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    await openPanel()
    await injectFrame(3)
    await vi.advanceTimersByTimeAsync(1200)
    expect(screen.getByTestId('live-frame-age').textContent).toContain('1.0 秒')
    FakeWebSocket.instances.at(-1)!.close()
    await waitFor(() => expect(screen.getByTestId('live-status-badge').textContent).toContain('帧通道断开'))
    expect((screen.getByTestId('live-btn-take-control') as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('L12 disconnect & occupancy honesty', () => {
  it('断连立即禁用全部交互按钮并通知服务端', async () => {
    await openPanel()
    await goToRemote()
    await injectFrame(30)
    FakeWebSocket.instances.at(-1)!.close()
    await waitFor(() => expect(screen.getByTestId('live-disconnected')).toBeTruthy())
    expect((screen.getByTestId('live-btn-take-control') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByTestId('live-btn-release') as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true')
    expect(screen.getByTestId('live-status-badge').textContent).toBe('帧通道断开，交互已禁用')
    await waitFor(() => expect(callsTo(`/api/v1/live/sessions/${SID}/disconnect`, 'POST')).toHaveLength(1))
    expect(callsTo(`/api/v1/live/sessions/${SID}/disconnect`, 'POST')[0]!.body).toEqual({ who: 'operator' })
  })

  it('其他执行者占用远控（409 CONFLICT + LIVE_REMOTE_HELD detail）→ 占用提示明确，不升级输入', async () => {
    await openPanel()
    await injectFrame(1)
    prime((call) =>
      call.method === 'POST' && call.url.endsWith(':take-control')
        ? jsonResponse({ code: 'CONFLICT', title: 'ConflictError', status: 409, detail: 'LIVE_REMOTE_HELD: another session holds the remote write lease' }, 409)
        : null,
    )
    await fireEvent.click(screen.getByTestId('live-btn-take-control'))
    await waitFor(() => expect(screen.getByTestId('live-error').textContent).toContain('LIVE_REMOTE_HELD'))
    expect(screen.getByTestId('live-error').textContent).toContain('其他会话持有')
    expect(screen.getByTestId('live-state-badge').textContent).toBe('VIEWING')
    expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true')
  })

  it('终态呈现：stop 成功后标 CLOSED + 不可恢复 + 需重新授权', async () => {
    await openPanel()
    prime((call) =>
      call.method === 'POST' && call.url.endsWith(':stop')
        ? jsonResponse(sessionPayload({ state: 'CLOSED', terminal: { cause: 'OPERATOR_STOP', resumable: false, reauthorizationRequired: true, tokenInvalidated: true, closedAt: '2026-09-17T09:31:00+08:00' } }))
        : null,
    )
    await fireEvent.click(screen.getByTestId('live-btn-stop'))
    await waitFor(() => expect(screen.getByTestId('live-terminal').textContent).toContain('OPERATOR_STOP'))
    expect(screen.getByTestId('live-terminal').textContent).toContain('不可恢复')
    expect(screen.getByTestId('live-status-badge').textContent).toBe('会话已终态（CLOSED）')
  })
})

// ===========================================================================
// 五、交还：确认对话框 + 本地 ack 记录 + 恢复语义呈现
// ===========================================================================

describe('L12 handover confirm + local ack (K13 §5)', () => {
  it('交还必须过确认对话框：取消不调用，确认后记录回执与受影响任务恢复模式', async () => {
    await openPanel()
    await goToRemote()
    prime((call) =>
      call.method === 'POST' && call.url.endsWith(':release')
        ? jsonResponse({
            ...sessionPayload({ state: 'VIEWING' }),
            handover: {
              doc: 'handover',
              sessionId: SID,
              tenantId: 'tn-01',
              deviceId: DEVICE,
              operatorId: 'op-77',
              tier: 'INTERACTIVE_REMOTE',
              from: 'REMOTE',
              to: 'VIEWING',
              affectedTasks: [
                { taskId: 'mt-3301', pauseState: 'PAUSED_WAITING_USER', resumeMode: 'REQUEUE_AUTO' },
                { taskId: 'mt-3302', pauseState: 'PAUSED_WAITING_USER', resumeMode: 'CONFIRM_REQUIRED' },
              ],
              singleWriterRestored: true,
              frameDownlinkContinues: true,
              releasedAt: '2026-09-17T09:31:10+08:00',
              releasedBy: 'op-77',
              auditEvent: 'live.session.release',
            },
          })
        : null,
    )
    // 取消路径：对话框出现但未发请求。
    await fireEvent.click(screen.getByTestId('live-btn-release'))
    expect(screen.getByTestId('live-release-confirm')).toBeTruthy()
    await fireEvent.click(screen.getByTestId('live-btn-cancel-release'))
    expect(callsTo(':release', 'POST')).toHaveLength(0)
    // 确认路径：调用 release，写本地 ack，回呈恢复语义。
    await fireEvent.click(screen.getByTestId('live-btn-release'))
    await fireEvent.click(screen.getByTestId('live-btn-confirm-release'))
    await waitFor(() => expect(callsTo(':release', 'POST')).toHaveLength(1))
    await waitFor(() => expect(screen.getByTestId('live-handover-ack')).toBeTruthy())
    expect(screen.getByTestId('live-state-badge').textContent).toBe('VIEWING')
    const tasks = screen.getByTestId('live-handover-tasks')
    expect(tasks.textContent).toContain('mt-3301')
    expect(tasks.textContent).toContain('mt-3302')
    expect(tasks.querySelector('li[data-resume-mode="CONFIRM_REQUIRED"]')?.textContent).toContain('需人工确认')
    // 本地 ack 记录确实落在 localStorage（按 sessionId 键）。
    const stored = loadHandoverAck(SID)
    expect(stored).not.toBeNull()
    expect(stored!.affectedTasks).toHaveLength(2)
    expect(localStorage.getItem(handoverAckKey(SID))).toContain('"singleWriterRestored":true')
  })

  it('ack 读写与恢复模式文案（纯函数）', () => {
    expect(resumeModeLabel('REQUEUE_AUTO')).toContain('自动回队列')
    expect(resumeModeLabel('CONFIRM_REQUIRED')).toContain('需人工确认')
    const receipt = {
      sessionId: 'live-x', deviceId: 'dev-x', tier: null, from: 'REMOTE', to: 'VIEWING',
      affectedTasks: [], singleWriterRestored: true, frameDownlinkContinues: true, releasedAt: '', releasedBy: 'op-1',
    }
    expect(saveHandoverAck(receipt)).toBe(true)
    expect(loadHandoverAck('live-x')?.singleWriterRestored).toBe(true)
    expect(loadHandoverAck('live-other')).toBeNull()
  })
})

// ===========================================================================
// 六、输入提交形状（帧空间 + frameSeq + seq 递增 + epoch）
// ===========================================================================

describe('L12 input submission shape', () => {
  it('tap/swipe 以帧空间坐标 + 当前帧序提交，seq 严格递增，绝不含设备空间坐标', async () => {
    await openPanel()
    await goToRemote()
    await injectFrame(7)
    mockViewportRect(810, 1440)
    primeInput({ accepted: true, inputWatermark: 1, latestFrameSeq: 7 })
    // tap：视口 (405,720) → 帧 (202.5, 360)。
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 1 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 1 })
    // swipe：起点帧 (202.5,360)，终点帧 (204.5,364)（帧空间位移 > 2）。
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 720, pointerId: 2 })
    await fireEvent.pointerMove(screen.getByTestId('live-frame-viewport'), { clientX: 409, clientY: 728, pointerId: 2 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 409, clientY: 728, pointerId: 2 })
    await waitFor(() => expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(2))
    const [tap, swipe] = callsTo(`/sessions/${SID}/input`, 'POST').map((call) => call.body!)
    expect(tap).toEqual({ kind: 'tap', seq: 1, frameSeq: 7, epoch: 4, x: 202.5, y: 360 })
    expect(swipe).toEqual({ kind: 'swipe', seq: 2, frameSeq: 7, epoch: 4, x: 202.5, y: 360, x2: 204.5, y2: 364 })
    // 帧空间边界：坐标必须小于帧宽 405（设备空间会是 540/960，绝不允许出现）。
    for (const body of [tap, swipe]) {
      expect(body.x as number).toBeLessThan(405)
      expect(body.y as number).toBeLessThan(720)
    }
  })

  it('留黑区点击被丢弃且不发送（不猜测坐标）', async () => {
    await openPanel()
    await goToRemote()
    await injectFrame(9)
    mockViewportRect(1000, 1000) // 帧 405×720 → 显示 562.5×1000，左右留黑 218.75。
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 100, clientY: 500, pointerId: 1 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 100, clientY: 500, pointerId: 1 })
    expect(callsTo(`/sessions/${SID}/input`, 'POST')).toHaveLength(0)
  })

  it('拒收呈现双水位；INPUT_EXPIRED 后输入不再盲发', async () => {
    await openPanel()
    await goToRemote()
    await injectFrame(12)
    mockViewportRect(810, 1440)
    primeInput({ status: 422, code: 'INPUT_EXPIRED', detail: 'input rejected: INPUT_EXPIRED', fields: { inputWatermark: '5', latestFrameSeq: '40' } })
    await fireEvent.pointerDown(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 360, pointerId: 1 })
    await fireEvent.pointerUp(screen.getByTestId('live-frame-viewport'), { clientX: 405, clientY: 360, pointerId: 1 })
    await waitFor(() => expect(screen.getByTestId('live-input-rejection').textContent).toContain('INPUT_EXPIRED'))
    expect(screen.getByTestId('live-input-rejection').textContent).toContain('latestFrameSeq=40')
    // 水位 40 vs 当前帧 12：差 28 > 阈值 10 → 立即按旧帧禁用。
    await waitFor(() => expect(screen.getByTestId('live-frame-viewport').getAttribute('aria-disabled')).toBe('true'))
  })

  it('限速器与 seq 递增（K13 §4 ≤10/s、严格递增的客户端镜像）', () => {
    const limiter = createInputRateLimiter(3)
    expect([limiter(), limiter(), limiter()]).toEqual([true, true, true])
    expect(limiter()).toBe(false)
    expect(nextInputSeq(0)).toBe(1)
    expect(nextInputSeq(41)).toBe(42)
  })
})

// ===========================================================================
// 七、会话映射与路由注册
// ===========================================================================

describe('L12 session mapping & routes', () => {
  it('mapLiveSession：保守映射，token 只在 establish 出现，终态与传输计划如实带出', () => {
    const session: LiveSession = mapLiveSession(sessionPayload({ sessionToken: 'tok-abc', state: 'CLOSED', terminal: { cause: 'DEVICE_REBOOT', resumable: false, reauthorizationRequired: true, tokenInvalidated: true, closedAt: '2026-09-17T10:00:00+08:00' } }))
    expect(session.sessionToken).toBe('tok-abc')
    expect(session.terminal?.cause).toBe('DEVICE_REBOOT')
    expect(session.terminal?.reauthorizationRequired).toBe(true)
    expect(session.lease.epoch).toBe(4)
    expect(session.frameGeometry.rotation).toBe(0)
    expect(session.frameGeometry.safeArea).toEqual({ left: 0, top: 84, right: 0, bottom: 0 })
    expect(session.transportPlan?.operatorStreamPath).toContain(`/live/${SID}/stream`)
    expect(session.inputPolicy?.ttlExpiryMs).toBe(2000)
  })

  it('路由：/live 面板路由可被注册（对照 fleet/reconciliation 模式）', () => {
    expect(liveFleetRoutes[0]!.path).toBe('/live')
    const router = createRouter({ history: createMemoryHistory(), routes: liveFleetRoutes })
    expect(router.hasRoute('live-fleet-panel')).toBe(true)
    const empty = createRouter({ history: createMemoryHistory(), routes: [] })
    registerLiveFleetRoutes(empty)
    expect(empty.hasRoute('live-fleet-panel')).toBe(true)
  })
})
