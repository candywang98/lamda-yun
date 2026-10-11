<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { collectImBody, ImApiError, imPlatformLabel, listImBodyCollections, type ImBodyCollection, type ImBodyCollections, type ImThread } from '@/api/im'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{ thread: ImThread; deviceLabel: string }>()
const session = useSessionStore()
const data = ref<ImBodyCollections | null>(null)
const loading = ref(false)
const submitting = ref(false)
const confirming = ref(false)
const error = ref('')
const missing = ref(false)
const pending = ref(false)
let key: string | null = null
let revision = 0
let disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
const activeStates = new Set(['PENDING', 'QUEUED', 'CREATED', 'DISPATCHED', 'CLAIMED', 'RUNNING', 'PAUSED', 'RETRYING'])
const latest = computed(() => data.value?.items[0])
const snapshot = computed(() => data.value?.items.find((item) => item.status === 'SUCCEEDED' && item.snapshot)?.snapshot)
const snapshotTitle = computed(() => latest.value?.status === 'SUCCEEDED' && latest.value.snapshot ? '本次读取的可见正文' : '上次读取的可见正文')
const statusLabels: Record<string, string> = { QUEUED: '等待手机读取', PENDING: '等待手机读取', CREATED: '等待手机读取', DISPATCHED: '等待手机读取', CLAIMED: '正在读取', RUNNING: '正在读取', PAUSED: '已暂停', RETRYING: '等待手机读取', SUCCEEDED: '读取完成', FAILED: '读取失败', CANCELLED: '已取消', EXPIRED: '读取已过期' }
const capabilityReason = computed(() => {
  const code = data.value?.capability?.reason
  const labels: Record<string, string> = { OFFLINE: '手机离线', DEVICE_OFFLINE: '手机离线', PROTOCOL_UNSUPPORTED: '需要支持正文读取的手机端', DEVICE_BUSY: '手机正在执行其他任务', NO_ACTIVE_BINDING: '没有有效手机绑定', PLATFORM_UNSUPPORTED: '当前平台不支持' }
  return code && labels[code] ? '：' + labels[code] : ''
})
function readTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false }) }
const reason = computed(() => {
  if (missing.value) return '云端尚不支持正文读取'
  if (props.thread.platform !== 'xianyu') return '当前仅支持闲鱼正文读取'
  if (!session.can('device.control')) return '当前角色无设备控制权限'
  if (!data.value) return loading.value ? '正在检查正文读取能力' : '尚未确认正文读取能力'
  if (data.value.capability?.supported !== true) return '设备尚不支持正文读取' + capabilityReason.value
  if (data.value.capability?.available !== true) return '设备当前不可读取' + capabilityReason.value
  if (pending.value) return '正文读取任务处理中'
  return ''
})
const canCollect = computed(() => !reason.value && !submitting.value && !loading.value)
function stop() { clearTimeout(timer); timer = undefined; controller?.abort(); controller = undefined }
function schedule() {
  clearTimeout(timer)
  if (!disposed && pending.value && document.visibilityState === 'visible') timer = setTimeout(() => { void refresh() }, 3000)
}
async function refresh() {
  if (disposed || loading.value) return
  const current = revision
  const threadId = props.thread.id
  controller = new AbortController()
  loading.value = true
  try {
    const result = await listImBodyCollections(threadId, controller.signal)
    if (disposed || current !== revision) return
    data.value = result
    missing.value = false
    error.value = ''
    pending.value = result.items.some((item) => activeStates.has(item.status))
  } catch (cause) {
    if (disposed || current !== revision || (cause instanceof Error && cause.name === 'AbortError')) return
    missing.value = cause instanceof ImApiError && cause.status === 404
    error.value = missing.value ? '' : '读取任务状态失败，请手动刷新后再试'
    data.value = null
    pending.value = false
  } finally {
    if (!disposed && current === revision) { loading.value = false; schedule() }
  }
}
function prepare() { if (canCollect.value) { key ??= crypto.randomUUID(); confirming.value = true } }
async function submit() {
  if (!canCollect.value || !confirming.value || !key) return
  const current = revision
  submitting.value = true
  error.value = ''
  try {
    const result = await collectImBody(props.thread.id, key)
    if (disposed || current !== revision) return
    key = null
    confirming.value = false
    pending.value = activeStates.has(result.status)
    const item: ImBodyCollection = { ...result, createdAt: '', snapshot: null, errorCode: null }
    if (data.value) data.value = { ...data.value, items: [item, ...data.value.items.filter((old) => old.taskId !== result.taskId)] }
    await refresh()
  } catch (cause) {
    if (disposed || current !== revision) return
    missing.value = cause instanceof ImApiError && cause.status === 404
    error.value = missing.value ? '' : '提交未确认。再次确认将使用同一请求编号重试，不会自动重试。'
  } finally { if (!disposed && current === revision) submitting.value = false }
}
watch(() => JSON.stringify([session.user.id, session.user.tenant, props.thread.id, props.thread.deviceId, props.thread.platform, props.thread.peerKey, props.thread.peerName]), () => {
  ++revision
  stop()
  data.value = null
  loading.value = false
  submitting.value = false
  confirming.value = false
  error.value = ''
  missing.value = false
  pending.value = false
  key = null
  void refresh()
}, { immediate: true, flush: 'sync' })
function visibility() {
  if (document.visibilityState !== 'visible') { clearTimeout(timer); timer = undefined }
  else if (pending.value) void refresh()
}
document.addEventListener('visibilitychange', visibility)
onBeforeUnmount(() => { disposed = true; ++revision; stop(); document.removeEventListener('visibilitychange', visibility) })
</script>

<template>
  <section class="body-collection" aria-label="当前可见正文读取">
    <div class="actions">
      <button type="button" :disabled="!canCollect || confirming" @click="prepare">{{ submitting ? '提交中…' : '读取当前可见正文' }}</button>
      <button type="button" :disabled="loading || submitting" @click="refresh">刷新读取状态</button>
    </div>
    <p v-if="reason" aria-live="polite">{{ reason }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="confirming" class="confirmation" role="region" aria-label="确认读取正文">
      <strong>确认读取：{{ deviceLabel }} · {{ thread.deviceId }} · {{ imPlatformLabel(thread.platform) }} · {{ thread.peerName }}</strong>
      <p>账号：未核验。请核对手机当前账号与联系人。</p>
      <p>将打开手机聊天界面，可能将会话标为已读；只读取当前一屏可见文字，不滚动历史、不输入、不发送，不开启值班。</p>
      <button type="button" :disabled="submitting" @click="confirming = false">取消</button>
      <button type="button" :disabled="!canCollect" @click="submit">确认读取当前可见正文</button>
    </div>
    <p v-if="latest">最近读取任务：{{ statusLabels[latest.status] ?? '状态待确认' }}</p>
    <section v-if="snapshot" class="snapshot" :aria-label="snapshotTitle">
      <h3>{{ snapshotTitle }}</h3>
      <p>来源：手机无障碍可见文字 · 仅当前一屏，非完整聊天历史。原始通知保留不变。</p>
      <p>读取时间：{{ readTime(snapshot.capturedAt) }} · 原消息时间：未知</p>
      <p>账号：未核验 · 聊天页显示名称：{{ snapshot.peerIdentity.observedName }}（仅标题匹配）</p>
      <p>方向根据气泡位置推测，不证明发送成功或对方已读。</p>
      <p v-if="snapshot.truncated" role="status">内容达到读取上限，已截断。</p>
      <p v-if="snapshot.messages.length === 0">本次未读取到可见文字，不代表会话没有消息。</p>
      <ol v-else>
        <li v-for="message in snapshot.messages" :key="message.visibleOrder">
          <span>{{ message.direction === 'IN' ? '推测收到' : '推测发出' }}</span>
          <p class="text">{{ message.text }}</p>
        </li>
      </ol>
    </section>
  </section>
</template>

<style scoped>
.body-collection { margin: 12px 14px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; min-width: 0; overflow-wrap: anywhere; font-size: 12px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
button { min-height: 34px; padding: 6px 10px; border: 1px solid var(--line-strong); border-radius: 5px; background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; max-width: 100%; }
button:disabled { opacity: .55; cursor: default; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
p { margin: 8px 0; }
h3 { font-size: 14px; margin: 0 0 8px; }
.confirmation, .snapshot { margin-top: 12px; padding: 12px; background: var(--surface); border-radius: 6px; }
ol { padding-left: 22px; }
.text { white-space: pre-wrap; }
</style>
