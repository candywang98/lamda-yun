<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  establishLiveSession,
  fetchLiveSessionStatus,
  LIVE_PANEL_VERSION,
  LiveFleetApiError,
  liveOperatorStreamUrl,
  notifyLiveDisconnect,
  releaseLiveControl,
  stopLiveSession,
  submitLiveInput,
  takeLiveControl,
  type LiveInputEvent,
} from './api'
import {
  createInputRateLimiter,
  inputChannelOpen,
  inputGate,
  loadHandoverAck,
  LIVE_CONTRACT_VERSION,
  nextInputSeq,
  panelStatus,
  PANEL_STATUS_LABELS,
  resumeModeLabel,
  saveHandoverAck,
  tierBadgeLabelOf,
  tierEnvelopeCoherent,
  tierUiLabelOf,
  viewportPointToFrame,
  type FrameCursor,
  type FrameGeometry,
  type HandoverReceipt,
  type LiveSession,
  type LiveTier,
} from './model'

const DEVICE_PATTERN = /^[\w.-]+$/
const TIER_CHOICES: { tier: LiveTier; label: string; note: string }[] = [
  { tier: 'JPEG_PREVIEW', label: 'JPEG 预览（只读观察）', note: '无输入通道；仅帧下行' },
  { tier: 'INTERACTIVE_REMOTE', label: '交互远控（JPEG 传输）', note: '接管后可输入；无需 TURN' },
  { tier: 'WEBRTC', label: '交互远控（WebRTC 高清）', note: '需 TURN 生产门；本面板暂未接媒体管线' },
]

const deviceIdInput = ref('')
const tierChoice = ref<LiveTier>('JPEG_PREVIEW')

const session = ref<LiveSession | null>(null)
const sessionToken = ref<string | null>(null)
const frameSrc = ref('')
const frameCursor = ref<FrameCursor | null>(null)
const transportConnected = ref(false)
const transportNote = ref('')
const serverLatestFrameSeq = ref<number | null>(null)
const busy = ref(false)
const errorView = ref<{ code: string; detail: string; hint: string } | null>(null)
const confirmReleaseOpen = ref(false)
const handoverAck = ref<HandoverReceipt | null>(null)
const handoverAckPersisted = ref(false)
const droppedLetterbox = ref(0)
const lastRejection = ref<{ code: string; hint: string; watermark: string } | null>(null)

let socket: WebSocket | null = null
let localFrameCount = 0
let inputSeq = 0
let rateLimiter = createInputRateLimiter(10)
let statusTimer: ReturnType<typeof setInterval> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null

/**
 * 响应式时钟：TTL/旧帧判定依赖 Date.now()（非响应式），不驱动重算的话
 * 断流后 UI 会一直停留在旧的「允许交互」判定。会话期间每 500ms 踩一次。
 */
const nowTick = ref(Date.now())

// ---------------------------------------------------------------------------
// 派生状态（全部走 model 纯函数；档位标识以服务端会话数据为准）
// ---------------------------------------------------------------------------

const status = computed(() => panelStatus(session.value, frameCursor.value, transportConnected.value, serverLatestFrameSeq.value, nowTick.value))
const statusLabel = computed(() => PANEL_STATUS_LABELS[status.value])
const tierBadge = computed(() => (session.value ? tierBadgeLabelOf(session.value) : ''))
const tierUiLabel = computed(() => (session.value ? tierUiLabelOf(session.value) : ''))
const envelopeWarning = computed(() => {
  if (!session.value) return ''
  if (tierEnvelopeCoherent(session.value)) return ''
  return '服务端能力信封与 K13 档位派生常量不一致，已按只读 fail-closed 处理'
})
const channelOpen = computed(() => (session.value ? inputChannelOpen(session.value) : false))
const gate = computed(() =>
  inputGate({
    session: session.value,
    frame: frameCursor.value,
    transportConnected: transportConnected.value,
    serverLatestFrameSeq: serverLatestFrameSeq.value,
    nowMs: nowTick.value,
  }),
)
const awaitingProjectionAck = computed(() => session.value != null && session.value.authorization.userConfirmedAt == null && session.value.state !== 'CLOSED' && session.value.terminal == null)
const canTakeControl = computed(
  () => session.value != null && channelOpen.value && session.value.state === 'VIEWING' && session.value.terminal == null,
)
const takeControlDisabledReason = computed(() => {
  if (!session.value || !channelOpen.value) return ''
  if (session.value.state !== 'VIEWING') return ''
  if (awaitingProjectionAck.value) return '手机尚未确认投屏授权（MediaProjection），接管会被 428 拒绝'
  if (!transportConnected.value) return '帧通道断开，暂不可接管'
  return ''
})
/** 断连立即禁用：接管/交还/输入全部锁死；仅保留「结束会话」作为安全出口。 */
const interactionLocked = computed(() => session.value != null && session.value.terminal == null && !transportConnected.value)
const inputDisabledReason = computed(() => {
  if (!session.value) return ''
  if (session.value.terminal || session.value.state === 'CLOSED') return '会话已终态'
  if (!channelOpen.value) return '只读档位：无输入权限（预览 ≠ 远控）'
  if (session.value.state !== 'REMOTE') return '旁观会话（VIEWING）：无点击权限'
  if (interactionLocked.value) return '帧通道断开，交互已禁用'
  return gate.value.allowed ? '' : gate.value.hint
})

const viewportGeometry = computed<FrameGeometry | null>(() => session.value?.frameGeometry ?? null)

// ---------------------------------------------------------------------------
// 传输（帧下行 WS；slice1 兼容信令 {t:frame|state}，帧序 seq 存在则用，否则本地计数）
// ---------------------------------------------------------------------------

function connectTransport(path: string | null): void {
  socket?.close()
  socket = null
  transportConnected.value = false
  localFrameCount = 0
  if (!path) {
    transportNote.value = '传输计划未提供帧流端点'
    return
  }
  if (typeof WebSocket === 'undefined') {
    transportNote.value = '当前环境不支持 WebSocket，帧下行不可用'
    return
  }
  transportNote.value = ''
  const ws = new WebSocket(liveOperatorStreamUrl(path))
  socket = ws
  ws.onopen = () => {
    if (socket !== ws) return
    transportConnected.value = true
  }
  ws.onmessage = (event: MessageEvent) => {
    if (socket !== ws) return
    let message: { t?: string; jpeg?: string; seq?: number; state?: string }
    try {
      message = JSON.parse(String(event.data)) as typeof message
    } catch {
      return
    }
    if (message.t === 'frame' && typeof message.jpeg === 'string' && message.jpeg) {
      frameSrc.value = `data:image/jpeg;base64,${message.jpeg}`
      const transportSeq = typeof message.seq === 'number' && Number.isInteger(message.seq) && message.seq >= 1 ? message.seq : null
      frameCursor.value = {
        seq: transportSeq ?? (localFrameCount += 1),
        receivedAtMs: Date.now(),
        seqSource: transportSeq != null ? 'transport' : 'local-count',
      }
    } else if (message.t === 'state' && message.state) {
      refreshStatus().catch(() => undefined)
    }
  }
  ws.onclose = () => {
    if (socket !== ws) return
    transportConnected.value = false
    // 断连立即禁用全部交互（上方 interactionLocked）；同时如实通知服务端。
    const sid = session.value?.sessionId
    if (sid && session.value?.terminal == null) {
      void notifyLiveDisconnect(sid, 'operator', sessionToken.value)
        .then((updated) => {
          session.value = updated
        })
        .catch(() => undefined)
    }
  }
}

function startStatusPolling(): void {
  stopStatusPolling()
  statusTimer = setInterval(() => {
    if (session.value && session.value.terminal == null) refreshStatus().catch(() => undefined)
  }, 10000)
  tickTimer = setInterval(() => {
    nowTick.value = Date.now()
  }, 500)
}

function stopStatusPolling(): void {
  if (statusTimer != null) {
    clearInterval(statusTimer)
    statusTimer = null
  }
  if (tickTimer != null) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

async function refreshStatus(): Promise<void> {
  if (!session.value) return
  const updated = await fetchLiveSessionStatus(session.value.sessionId, sessionToken.value)
  session.value = updated
  if (updated.terminal) {
    socket?.close()
    socket = null
    transportConnected.value = false
  }
}

// ---------------------------------------------------------------------------
// 动作
// ---------------------------------------------------------------------------

async function guard(action: () => Promise<void>): Promise<void> {
  busy.value = true
  errorView.value = null
  lastRejection.value = null
  try {
    await action()
  } catch (error) {
    if (error instanceof LiveFleetApiError) {
      errorView.value = { code: error.code, detail: error.detail, hint: error.hint }
      if (error.latestFrameSeq != null) serverLatestFrameSeq.value = error.latestFrameSeq
      if (['INPUT_EXPIRED', 'INPUT_SEQ_REGRESSION', 'LIVE_INPUT_FORBIDDEN', 'LIVE_RATE_LIMITED'].includes(error.code)) {
        lastRejection.value = {
          code: error.code,
          hint: error.hint,
          watermark: `inputWatermark=${error.inputWatermark ?? '?'} · latestFrameSeq=${error.latestFrameSeq ?? '?'}`,
        }
      }
      if (error.code === 'LIVE_RATE_LIMITED') await refreshStatus().catch(() => undefined)
    } else {
      errorView.value = { code: 'NETWORK', detail: error instanceof Error ? error.message : '操作失败', hint: '网络或未知错误' }
    }
  } finally {
    busy.value = false
  }
}

function establish(): void {
  const deviceId = deviceIdInput.value.trim()
  if (!DEVICE_PATTERN.test(deviceId)) {
    errorView.value = { code: 'VALIDATION', detail: '请输入有效的设备 ID', hint: '设备 ID 必填' }
    return
  }
  void guard(async () => {
    const established = await establishLiveSession(deviceId, tierChoice.value)
    session.value = established
    sessionToken.value = established.sessionToken
    frameSrc.value = ''
    frameCursor.value = null
    serverLatestFrameSeq.value = null
    inputSeq = 0
    rateLimiter = createInputRateLimiter(established.inputPolicy?.maxInputRatePerSecond ?? 10)
    handoverAck.value = loadHandoverAck(established.sessionId)
    handoverAckPersisted.value = handoverAck.value != null
    confirmReleaseOpen.value = false
    connectTransport(established.transportPlan?.operatorStreamPath ?? null)
    startStatusPolling()
  })
}

function takeControl(): void {
  const current = session.value
  if (!current) return
  void guard(async () => {
    session.value = await takeLiveControl(current.sessionId, sessionToken.value)
    inputSeq = 0
  })
}

function requestRelease(): void {
  confirmReleaseOpen.value = true
}

function cancelRelease(): void {
  confirmReleaseOpen.value = false
}

function confirmRelease(): void {
  const current = session.value
  if (!current) return
  void guard(async () => {
    const { session: updated, handover } = await releaseLiveControl(current.sessionId, sessionToken.value)
    session.value = updated
    confirmReleaseOpen.value = false
    if (handover) {
      handoverAck.value = handover
      handoverAckPersisted.value = saveHandoverAck(handover)
    }
  })
}

function stopSession(): void {
  const current = session.value
  if (!current) return
  void guard(async () => {
    session.value = await stopLiveSession(current.sessionId, sessionToken.value)
    socket?.close()
    socket = null
    transportConnected.value = false
    stopStatusPolling()
  })
}

// ---------------------------------------------------------------------------
// 输入：视口 CSS 像素 → 帧空间（letterbox + 缩放），带 frameSeq 提交；绝不发屏幕猜测坐标
// ---------------------------------------------------------------------------

async function sendInput(event: Omit<LiveInputEvent, 'seq' | 'epoch'>): Promise<void> {
  const current = session.value
  if (!current || !gate.value.allowed || !rateLimiter()) return
  inputSeq = nextInputSeq(inputSeq)
  try {
    const result = await submitLiveInput(current.deviceId, current.sessionId, sessionToken.value, {
      ...event,
      seq: inputSeq,
      epoch: current.lease.epoch ?? undefined,
    })
    if (result.latestFrameSeq > 0) serverLatestFrameSeq.value = result.latestFrameSeq
  } catch (error) {
    if (error instanceof LiveFleetApiError) {
      errorView.value = { code: error.code, detail: error.detail, hint: error.hint }
      if (error.latestFrameSeq != null) serverLatestFrameSeq.value = error.latestFrameSeq
      if (['INPUT_EXPIRED', 'INPUT_SEQ_REGRESSION', 'LIVE_INPUT_FORBIDDEN', 'LIVE_RATE_LIMITED'].includes(error.code)) {
        lastRejection.value = {
          code: error.code,
          hint: error.hint,
          watermark: `inputWatermark=${error.inputWatermark ?? '?'} · latestFrameSeq=${error.latestFrameSeq ?? '?'}`,
        }
      }
      if (error.code === 'LIVE_RATE_LIMITED') await refreshStatus().catch(() => undefined)
    } else {
      errorView.value = { code: 'NETWORK', detail: error instanceof Error ? error.message : '输入提交失败', hint: '网络或未知错误' }
    }
  }
}

function framePointFromPointer(viewport: HTMLElement, clientX: number, clientY: number) {
  const geometry = viewportGeometry.value
  if (!geometry) return null
  const rect = viewport.getBoundingClientRect()
  return viewportPointToFrame(clientX - rect.left, clientY - rect.top, { width: rect.width, height: rect.height }, geometry)
}

function onPointerDown(event: PointerEvent): void {
  if (!gate.value.allowed) return
  const viewport = event.currentTarget as HTMLElement
  const start = framePointFromPointer(viewport, event.clientX, event.clientY)
  if (!start) {
    droppedLetterbox.value += 1
    return
  }
  const startX = start.fx
  const startY = start.fy
  let endX = startX
  let endY = startY
  const move = (moveEvent: PointerEvent) => {
    const point = framePointFromPointer(viewport, moveEvent.clientX, moveEvent.clientY)
    if (point) {
      endX = point.fx
      endY = point.fy
    }
  }
  const up = (): void => {
    viewport.removeEventListener('pointermove', move)
    viewport.removeEventListener('pointerup', up)
    const frameSeq = frameCursor.value?.seq
    if (!frameSeq || !gate.value.allowed) return
    const moved = Math.abs(endX - startX) > 2 || Math.abs(endY - startY) > 2
    const payload = moved ? { x: startX, y: startY, x2: endX, y2: endY } : { x: startX, y: startY }
    void sendInput({ kind: moved ? 'swipe' : 'tap', frameSeq, ...payload })
  }
  viewport.addEventListener('pointermove', move)
  viewport.addEventListener('pointerup', up)
}

onBeforeUnmount(() => {
  stopStatusPolling()
  socket?.close()
  socket = null
  if (session.value && session.value.terminal == null && sessionToken.value) {
    void stopLiveSession(session.value.sessionId, sessionToken.value).catch(() => undefined)
  }
})
</script>

<template>
  <section class="live-page">
    <PageHeader
      kicker="舰队"
      title="投屏预览 / 远控"
      description="档位如实标识（K13 live-capabilities/v1）：预览 ≠ 远控；输入按帧空间坐标提交，附带帧序号。"
    />

    <div v-if="!session" class="live-establish" data-testid="live-establish">
      <label class="live-field">
        设备 ID
        <input v-model="deviceIdInput" data-testid="live-device-id" placeholder="例如 dev-b0644fb5" />
      </label>
      <fieldset class="live-field">
        <legend>档位（建立时选择，档位 × 传输为闭集）</legend>
        <label v-for="choice in TIER_CHOICES" :key="choice.tier" class="live-tier-choice">
          <input v-model="tierChoice" type="radio" :value="choice.tier" :data-testid="`live-tier-${choice.tier}`" />
          <span>{{ choice.label }}</span>
          <small>{{ choice.note }}</small>
        </label>
      </fieldset>
      <button class="yy-btn primary" type="button" :disabled="busy" data-testid="live-btn-establish" @click="establish">
        发起投屏会话
      </button>
    </div>

    <template v-else>
      <header class="live-statusbar">
        <span class="live-badge" :data-tier="tierUiLabel" data-testid="live-tier-badge">{{ tierBadge }}</span>
        <span class="live-badge" :data-status="status" data-testid="live-status-badge">{{ statusLabel }}</span>
        <span class="live-badge plain" data-testid="live-state-badge">{{ session.state }}</span>
        <span v-if="session.lease.epoch != null" class="live-badge plain">epoch {{ session.lease.epoch }}</span>
      </header>

      <p v-if="envelopeWarning" class="yy-error" data-testid="live-envelope-warning">{{ envelopeWarning }}</p>
      <p v-if="awaitingProjectionAck" class="live-hint" data-testid="live-auth-pending">
        需要手机授权：等待设备现场确认投屏（MediaProjection ack 待确认，userConfirmedAt 为空）。
      </p>
      <p v-if="interactionLocked && session.terminal == null" class="yy-error" data-testid="live-disconnected">
        帧通道断开：交互已全部禁用（仅保留结束会话）。
      </p>
      <p v-if="errorView" class="yy-error" data-testid="live-error">
        [{{ errorView.code }}] {{ errorView.hint }}（{{ errorView.detail }}）
      </p>
      <p v-if="lastRejection" class="live-hint" data-testid="live-input-rejection">
        输入被拒收：{{ lastRejection.code }} — {{ lastRejection.watermark }}
      </p>
      <p v-if="transportNote" class="live-hint">{{ transportNote }}</p>

      <div class="live-actions">
        <button
          v-if="channelOpen"
          class="yy-btn primary"
          type="button"
          :disabled="busy || !canTakeControl || session.state === 'REMOTE' || interactionLocked"
          :title="takeControlDisabledReason"
          data-testid="live-btn-take-control"
          @click="takeControl"
        >
          接管远控
        </button>
        <button
          class="yy-btn"
          type="button"
          :disabled="busy || session.state !== 'REMOTE' || interactionLocked"
          data-testid="live-btn-release"
          @click="requestRelease"
        >
          交还设备（REMOTE → VIEWING）
        </button>
        <button class="yy-btn danger" type="button" :disabled="busy || session.terminal != null" data-testid="live-btn-stop" @click="stopSession">
          结束会话
        </button>
      </div>

      <div
        class="live-viewport"
        :class="{ interactive: gate.allowed }"
        data-testid="live-frame-viewport"
        :aria-disabled="!gate.allowed"
        @pointerdown="onPointerDown"
      >
        <img v-if="frameSrc" :src="frameSrc" alt="设备实时画面（帧下行）" />
        <p v-else class="live-hint">等待帧下行…（建立后设备需现场确认投屏授权）</p>
      </div>

      <p v-if="inputDisabledReason && channelOpen && session.state === 'REMOTE'" class="live-hint" data-testid="live-input-disabled-reason">
        危险交互已禁用：{{ inputDisabledReason }}
      </p>
      <p v-else-if="inputDisabledReason && session.state === 'REMOTE'" class="live-hint" data-testid="live-input-disabled-reason">
        {{ inputDisabledReason }}
      </p>
      <p v-if="frameCursor" class="live-hint plain" data-testid="live-frame-cursor">
        当前帧序 {{ frameCursor.seq }}（{{ frameCursor.seqSource === 'transport' ? '传输下发' : '本地计数' }}）
        <template v-if="serverLatestFrameSeq != null"> · 服务端最新帧水位 {{ serverLatestFrameSeq }}</template>
      </p>
      <p v-if="droppedLetterbox > 0" class="live-hint plain">已丢弃 {{ droppedLetterbox }} 次落在留黑区的点击（不猜测坐标）。</p>

      <div v-if="confirmReleaseOpen" class="live-confirm" data-testid="live-release-confirm" role="dialog">
        <p>确认交还？交还后：帧下行不中断、设备恢复单写者；暂停任务按服务端回执恢复（破坏性窗口需人工确认）。</p>
        <div class="live-actions">
          <button class="yy-btn primary" type="button" :disabled="busy" data-testid="live-btn-confirm-release" @click="confirmRelease">
            确认交还
          </button>
          <button class="yy-btn" type="button" :disabled="busy" data-testid="live-btn-cancel-release" @click="cancelRelease">取消</button>
        </div>
      </div>

      <div v-if="handoverAck" class="live-ack" data-testid="live-handover-ack">
        <h3>交还回执{{ handoverAckPersisted ? '（已记录本地 ack）' : '（本地记录失败：环境无 localStorage）' }}</h3>
        <p data-testid="live-handover-meta">
          {{ handoverAck.sessionId }} · {{ handoverAck.from }} → {{ handoverAck.to }} · 单写者已恢复：{{
            handoverAck.singleWriterRestored ? '是' : '否'
          }} · 帧下行继续：{{ handoverAck.frameDownlinkContinues ? '是' : '否' }}
        </p>
        <ul v-if="handoverAck.affectedTasks.length" data-testid="live-handover-tasks">
          <li v-for="task in handoverAck.affectedTasks" :key="task.taskId" :data-resume-mode="task.resumeMode">
            {{ task.taskId }} — {{ resumeModeLabel(task.resumeMode) }}
          </li>
        </ul>
        <p v-else class="live-hint plain">无受影响任务。</p>
      </div>

      <dl class="live-meta" data-testid="live-session-meta">
        <div><dt>会话</dt><dd>{{ session.sessionId }}</dd></div>
        <div><dt>设备</dt><dd>{{ session.deviceId }}</dd></div>
        <div><dt>传输</dt><dd>{{ session.transport }}（{{ session.transportPlan?.kind ?? '—' }}）</dd></div>
        <div>
          <dt>帧几何</dt>
          <dd>
            帧 {{ session.frameGeometry.frameWidth }}×{{ session.frameGeometry.frameHeight }} · 设备
            {{ session.frameGeometry.deviceWidth }}×{{ session.frameGeometry.deviceHeight }} · 旋转
            {{ session.frameGeometry.rotation }}°
          </dd>
        </div>
        <div v-if="session.inputPolicy">
          <dt>输入策略</dt>
          <dd>≤{{ session.inputPolicy.maxInputRatePerSecond }}/s · TTL {{ session.inputPolicy.ttlExpiryMs }}ms · 旧帧阈值 {{ session.inputPolicy.staleFrameThreshold }}</dd>
        </div>
        <div><dt>硬上限</dt><dd>{{ session.maxDurationMinutes ?? '?' }} 分钟（服务端强制 CLOSED）</dd></div>
        <div v-if="session.terminal">
          <dt>终态</dt>
          <dd data-testid="live-terminal">{{ session.terminal.cause }} · 不可恢复，需重新授权（persistsAcrossReboot=false）</dd>
        </div>
      </dl>
    </template>

    <footer class="live-footer">契约 {{ LIVE_CONTRACT_VERSION }} · 面板 {{ LIVE_PANEL_VERSION }}</footer>
  </section>
</template>

<style scoped>
.live-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.live-establish {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 460px;
}
.live-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.live-tier-choice {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 8px;
  align-items: center;
}
.live-tier-choice small {
  grid-column: 2;
  color: #64748b;
}
.live-statusbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.live-badge {
  font-size: 12px;
  border-radius: 999px;
  padding: 3px 10px;
  background: #e2e8f0;
}
.live-badge[data-tier='preview'] {
  background: #e0e7ff;
  color: #3730a3;
}
.live-badge[data-tier='interactive'],
.live-badge[data-tier='interactive-hd'] {
  background: #fef3c7;
  color: #92400e;
}
.live-badge[data-tier='unknown'] {
  background: #fee2e2;
  color: #991b1b;
}
.live-badge[data-status='REMOTE'] {
  background: #dcfce7;
  color: #166534;
}
.live-badge[data-status='AWAITING_PROJECTION_ACK'],
.live-badge[data-status='STALE_FRAME'] {
  background: #fef3c7;
  color: #92400e;
}
.live-badge[data-status='DISCONNECTED'],
.live-badge[data-status='TERMINAL'] {
  background: #fee2e2;
  color: #991b1b;
}
.live-badge.plain {
  background: #f1f5f9;
  color: #334155;
}
.live-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.live-viewport {
  position: relative;
  border: 1px dashed var(--yy-line, #cbd5e1);
  border-radius: 12px;
  background: #0f172a08;
  width: 100%;
  max-width: 480px;
  aspect-ratio: 9 / 16;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.live-viewport img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.live-viewport.interactive {
  cursor: crosshair;
  border-style: solid;
}
.live-viewport[aria-disabled='true'] {
  cursor: not-allowed;
}
.live-hint {
  font-size: 13px;
  color: #475569;
  margin: 0;
}
.live-hint.plain {
  color: #64748b;
}
.live-confirm {
  border: 1px solid #f59e0b;
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #fffbeb;
}
.live-ack {
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.live-ack h3 {
  margin: 0;
  font-size: 14px;
}
.live-ack ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
}
.live-ack li[data-resume-mode='CONFIRM_REQUIRED'] {
  color: #b45309;
  font-weight: 600;
}
.live-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 8px;
  font-size: 13px;
  margin: 0;
}
.live-meta div {
  display: flex;
  gap: 8px;
}
.live-meta dt {
  color: #64748b;
  white-space: nowrap;
}
.live-meta dd {
  margin: 0;
}
.live-footer {
  font-size: 12px;
  color: #94a3b8;
}
</style>
