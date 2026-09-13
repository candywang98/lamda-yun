<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import {
  LiveApiError,
  liveStreamUrl,
  openLiveSession,
  releaseLiveControl,
  stopLiveSession,
  takeLiveControl,
  type LiveState,
} from '@/api/live'

const props = defineProps<{ deviceId: string }>()

const state = ref<LiveState | 'IDLE'>('IDLE')
const sid = ref('')
const frameSrc = ref('')
const errorMessage = ref('')
const busy = ref(false)

let socket: WebSocket | null = null
let seq = 0
let sentWindow: number[] = []

function rateLimited(): boolean {
  const now = Date.now()
  sentWindow = sentWindow.filter((stamp) => now - stamp < 1000)
  return sentWindow.length >= 10
}

async function guard(action: () => Promise<unknown>) {
  busy.value = true
  errorMessage.value = ''
  try {
    await action()
  } catch (error) {
    errorMessage.value = error instanceof LiveApiError ? error.message : '操作失败'
  } finally {
    busy.value = false
  }
}

function connect() {
  socket?.close()
  socket = new WebSocket(liveStreamUrl(props.deviceId, sid.value))
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data) as { t: string; jpeg?: string; state?: LiveState }
    if (message.t === 'frame' && message.jpeg) {
      frameSrc.value = `data:image/jpeg;base64,${message.jpeg}`
    } else if (message.t === 'state' && message.state) {
      state.value = message.state
      if (message.state === 'CLOSED') socket?.close()
    }
  }
  socket.onclose = () => {
    if (state.value !== 'CLOSED') state.value = 'CLOSED'
  }
}

function start() {
  guard(async () => {
    const status = await openLiveSession(props.deviceId)
    sid.value = status.sessionId
    state.value = status.state
    connect()
  })
}

function takeControl() {
  guard(async () => {
    const status = await takeLiveControl(props.deviceId, sid.value)
    state.value = status.state
    seq = 0
  })
}

function release() {
  guard(async () => {
    const status = await releaseLiveControl(props.deviceId, sid.value)
    state.value = status.state
  })
}

function stop() {
  guard(async () => {
    await stopLiveSession(props.deviceId, sid.value)
    socket?.close()
    state.value = 'CLOSED'
    frameSrc.value = ''
  })
}

function sendInput(kind: 'tap' | 'swipe', payload: Record<string, number>) {
  if (state.value !== 'REMOTE' || !socket || rateLimited()) return
  seq += 1
  sentWindow.push(Date.now())
  socket.send(JSON.stringify({ t: 'input', kind, seq, ...payload }))
}

function onCanvasPointerDown(event: PointerEvent) {
  if (state.value !== 'REMOTE') return
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width).toFixed(4)
  const y = ((event.clientY - rect.top) / rect.height).toFixed(4)
  const startX = Number(x)
  const startY = Number(y)
  let moved = false
  let lastX = startX
  let lastY = startY
  const move = (moveEvent: PointerEvent) => {
    lastX = (moveEvent.clientX - rect.left) / rect.width
    lastY = (moveEvent.clientY - rect.top) / rect.height
    if (Math.abs(lastX - startX) > 0.02 || Math.abs(lastY - startY) > 0.02) moved = true
  }
  const up = () => {
    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', up)
    if (moved) {
      sendInput('swipe', { x: startX, y: startY, x2: +lastX.toFixed(4), y2: +lastY.toFixed(4) })
    } else {
      sendInput('tap', { x: startX, y: startY })
    }
  }
  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', up)
}

onBeforeUnmount(() => {
  socket?.close()
  if (sid.value && state.value !== 'CLOSED') void stopLiveSession(props.deviceId, sid.value).catch(() => undefined)
})
</script>

<template>
  <section class="yy-panel live-panel">
    <header class="live-head">
      <h2>实时观看 / 远控</h2>
      <span class="live-state" :data-state="state">{{ state }}</span>
      <div class="live-actions">
        <button v-if="state === 'IDLE' || state === 'CLOSED'" class="yy-btn" type="button" :disabled="busy" @click="start">
          开始观看
        </button>
        <button v-if="state === 'VIEWING'" class="yy-btn primary" type="button" :disabled="busy" @click="takeControl">
          接管远控
        </button>
        <button v-if="state === 'REMOTE'" class="yy-btn" type="button" :disabled="busy" @click="release">
          交还自动
        </button>
        <button v-if="state !== 'IDLE' && state !== 'CLOSED'" class="yy-btn danger" type="button" :disabled="busy" @click="stop">
          结束会话
        </button>
      </div>
    </header>
    <p v-if="errorMessage" class="yy-error">{{ errorMessage }}</p>
    <p v-if="state === 'REMOTE'" class="yy-sub">远控中：单击=点按，按住拖动=滑动（手机需确认投屏授权）。</p>
    <div class="live-canvas" :class="{ interactive: state === 'REMOTE' }" @pointerdown="onCanvasPointerDown">
      <img v-if="frameSrc" :src="frameSrc" alt="设备实时画面" />
      <p v-else class="yy-sub">点击「开始观看」后，手机会请求屏幕录制授权；同意后画面显示在这里。</p>
    </div>
  </section>
</template>

<style scoped>
.live-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.live-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.live-head h2 {
  margin: 0;
  font-size: 16px;
}
.live-state {
  font-size: 12px;
  border-radius: 999px;
  padding: 2px 10px;
  background: #e2e8f0;
}
.live-state[data-state='REMOTE'] {
  background: #fef3c7;
  color: #92400e;
}
.live-state[data-state='VIEWING'] {
  background: #dcfce7;
  color: #166534;
}
.live-state[data-state='CLOSED'] {
  background: #fee2e2;
  color: #991b1b;
}
.live-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.live-canvas {
  border: 1px dashed var(--yy-line, #cbd5e1);
  border-radius: 12px;
  background: #0f172a08;
  aspect-ratio: 9 / 20;
  max-height: 520px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.live-canvas img {
  height: 100%;
  object-fit: contain;
}
.live-canvas.interactive {
  cursor: crosshair;
  border-style: solid;
}
</style>
