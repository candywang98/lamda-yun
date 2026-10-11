<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import {
  fetchImConfig,
  classifyImMessage,
  reclassifyImMessage,
  imDutyStatus,
  imDutyStatusLabel,
  imPlatformDmFiltered,
  imPlatformLabel,
  IM_PLATFORM_OPTIONS,
  ImApiError,
  listImMessages,
  listImThreads,
  markImThreadRead,
  replyImThread,
  saveImConfig,
  validateImConfigDraft,
  type ImMessage,
  type ImBucket,
  type ImCategory,
  type ImThreadPage,
  type ImMonitorConfig,
  type ImThread,
} from '@/api/im'
import { useSessionStore } from '@/stores/session'
import { deliveryLabel, isNotificationPreview } from '@/features/im/presentation'
import MessageClassification from '@/features/im/MessageClassification.vue'
import { categoryLabel, classificationVersion, IM_BUCKETS } from '@/features/im/classification'

const threads = ref<ImThread[]>([])
const selected = ref<ImThread | null>(null)
const messages = ref<ImMessage[]>([])
const deviceFilter = ref('')
const unreadOnly = ref(false)
const bucket = ref<ImBucket>('user')
const bucketCounts = ref<ImThreadPage['bucketCounts']>(null)
const threadsLoading = ref(false)
const moreThreadsLoading = ref(false)
const threadsHasMore = ref(false)
const THREAD_PAGE_SIZE = 50
const messagesLoading = ref(false)
const classificationBusy = ref('')
const classificationError = ref('')
const classificationNotice = ref('')

const session = useSessionStore()
/** 设备监控设置是设备侧运维写操作，沿用 device.control 权限；只读角色仅可查看。 */
const canEditConfig = computed(() => session.can('device.control'))

/* ---------------- 会话流 ---------------- */

const searchText = ref('')
const visibleThreads = computed(() => threads.value.filter((thread) => {
  if (deviceFilter.value && thread.deviceId !== deviceFilter.value) return false
  const query = searchText.value.trim().toLocaleLowerCase()
  return !query || [thread.peerName, thread.lastMessageText, deviceLabel(thread.deviceId), thread.deviceId, imPlatformLabel(thread.platform)]
    .some((value) => value?.toLocaleLowerCase().includes(query))
}))
const deviceIds = computed(() => [...new Set(threads.value.map((thread) => thread.deviceId))])
const filterDeviceOptions = computed(() => {
  const merged = new Map<string, ConfigDeviceOption>()
  for (const option of deviceOptions.value) merged.set(option.id, option)
  for (const id of deviceIds.value) {
    if (!merged.has(id)) merged.set(id, { id, name: `设备 ${deviceShort(id)}` })
  }
  return [...merged.values()]
})
const deviceNameById = computed(() => new Map(filterDeviceOptions.value.map((option) => [option.id, option.name])))

const drafts = ref<Record<string, string>>({})
const replyText = computed({
  get: () => selected.value ? drafts.value[selected.value.id] ?? '' : '',
  set: (value: string) => { if (selected.value) drafts.value[selected.value.id] = value },
})
const replyIntent = ref<{ threadId: string; text: string; destination: string } | null>(null)
const replyResults = ref<Record<string, { text: string; error: boolean }>>({})
const replyFeedback = computed(() => selected.value ? replyResults.value[selected.value.id] : undefined)
let identityRevision = 0
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

let threadRequest = 0
let messageRequest = 0
let contextRevision = 0
let conversationRevision = 0
let disposed = false

function clearSelection() {
  ++messageRequest
  ++conversationRevision
  selected.value = null
  messages.value = []
  messagesLoading.value = false
  replyIntent.value = null
  classificationError.value = ''
  classificationNotice.value = ''
}

async function refreshThreads(preserveSelection = true) {
  const request = ++threadRequest
  const pagesToLoad = preserveSelection ? Math.max(1, Math.ceil(threads.value.length / THREAD_PAGE_SIZE)) : 1
  if (!preserveSelection) clearSelection()
  moreThreadsLoading.value = false
  threadsLoading.value = true
  try {
    let page = await listImThreads(deviceFilter.value || undefined, unreadOnly.value, bucket.value)
    if (disposed || request !== threadRequest) return false
    const nextThreads = [...page.items]
    for (let index = 1; index < pagesToLoad && page.items.length === THREAD_PAGE_SIZE; index += 1) {
      page = await listImThreads(deviceFilter.value || undefined, unreadOnly.value, bucket.value, page.items.at(-1)!.id)
      if (disposed || request !== threadRequest) return false
      nextThreads.push(...page.items)
    }
    threads.value = [...new Map(nextThreads.map((thread) => [thread.id, thread])).values()]
    threadsHasMore.value = page.items.length === THREAD_PAGE_SIZE
    bucketCounts.value = page.bucketCounts
    if (selected.value && !nextThreads.some((thread) => thread.id === selected.value?.id)) {
      clearSelection()
    } else if (selected.value) {
      selected.value = nextThreads.find((thread) => thread.id === selected.value?.id) ?? selected.value
    }
    errorMessage.value = ''
    await loadDeviceConfigs()
    return !disposed && request === threadRequest
  } catch (error) {
    if (!disposed && request === threadRequest) {
      errorMessage.value = error instanceof ImApiError ? error.message : '会话列表加载失败'
    }
    return false
  } finally {
    if (!disposed && request === threadRequest) threadsLoading.value = false
  }
}

async function loadMoreThreads() {
  if (disposed || threadsLoading.value || moreThreadsLoading.value || !threadsHasMore.value) return
  const after = threads.value.at(-1)?.id
  if (!after) return
  const request = ++threadRequest
  moreThreadsLoading.value = true
  try {
    const page = await listImThreads(deviceFilter.value || undefined, unreadOnly.value, bucket.value, after)
    if (disposed || request !== threadRequest) return
    threads.value = [...new Map([...threads.value, ...page.items].map((thread) => [thread.id, thread])).values()]
    threadsHasMore.value = page.items.length === THREAD_PAGE_SIZE
    bucketCounts.value = page.bucketCounts
    errorMessage.value = ''
    await loadDeviceConfigs()
  } catch (error) {
    if (!disposed && request === threadRequest) {
      errorMessage.value = error instanceof ImApiError ? error.message : '更多会话加载失败'
    }
  } finally {
    if (!disposed && request === threadRequest) moreThreadsLoading.value = false
  }
}

async function refreshSelectedMessages(markRead = false) {
  const thread = selected.value
  if (!thread) return
  const request = ++messageRequest
  const revision = contextRevision
  const current = () => !disposed && request === messageRequest && revision === contextRevision && selected.value?.id === thread.id
  messagesLoading.value = true
  try {
    const nextMessages = await listImMessages(thread.id, bucket.value)
    if (!current()) return
    messages.value = nextMessages
    cacheThreadSummary(thread)
    errorMessage.value = ''
    if (markRead && thread.unreadCount > 0) {
      await markImThreadRead(thread.id)
      if (!current()) return
      const listed = threads.value.find((item) => item.id === thread.id)
      if (listed) listed.unreadCount = 0
      if (selected.value) selected.value.unreadCount = 0
    }
  } catch (error) {
    if (current()) errorMessage.value = error instanceof ImApiError ? error.message : '消息加载失败'
  } finally {
    if (current()) messagesLoading.value = false
  }
}

async function openThread(thread: ImThread) {
  clearSelection()
  selected.value = thread
  errorMessage.value = ''
  successMessage.value = ''
  await refreshSelectedMessages(true)
}

/** 会话打开后用本地已见正文回填摘要（后端 lastMessageText 字段位优先）。 */
function cacheThreadSummary(thread: ImThread) {
  if (threadSummary(thread)) return
  const last = messages.value[messages.value.length - 1]
  if (!last) return
  thread.lastMessageText = last.text
}

function threadSummary(thread: ImThread): string {
  if (typeof thread.lastMessageText === 'string' && thread.lastMessageText.trim()) return thread.lastMessageText
  return ''
}

async function refreshInbox() {
  if (await refreshThreads()) await refreshSelectedMessages()
}

async function changeClassification(message: ImMessage, category: ImCategory | null, retry = false) {
  const expectedVersion = classificationVersion(message.classification)
  if (!session.can('device.control') || message.direction !== 'IN' || classificationBusy.value ||
      expectedVersion === null || !messages.value.some((item) => item.id === message.id)) return
  const revision = contextRevision
  const conversation = conversationRevision
  const current = () => !disposed && revision === contextRevision && conversation === conversationRevision
  classificationBusy.value = message.id
  classificationError.value = ''
  classificationNotice.value = ''
  // Invalidate reads started before the correction, including in-flight polling.
  ++threadRequest
  ++messageRequest
  threadsLoading.value = false
  messagesLoading.value = false
  let shouldRefresh = false
  let feedback = ''
  let conflict = false
  try {
    const updated = retry
      ? await reclassifyImMessage(message.id, expectedVersion)
      : await classifyImMessage(message.id, category, expectedVersion)
    if (!current()) return
    messages.value = messages.value.map((item) => item.id === updated.id ? updated : item)
    shouldRefresh = true
    feedback = retry ? '重新分类已提交' : '分类已更新'
  } catch (error) {
    if (!current()) return
    conflict = error instanceof ImApiError && error.status === 409
    shouldRefresh = conflict
    feedback = conflict
      ? '分类版本已变化，本次修改未保存；已请求刷新，请核对后重试。'
      : error instanceof ImApiError ? error.message : '分类更新失败，请重试'
    classificationError.value = feedback
  } finally {
    if (!current() || !shouldRefresh) classificationBusy.value = ''
  }
  if (!current() || !shouldRefresh) return
  ++threadRequest
  ++messageRequest
  // Membership, ordering and counts can all change, even within a mixed thread.
  try {
    await refreshInbox()
    if (!disposed && revision === contextRevision &&
        (conversation === conversationRevision || selected.value === null)) {
      if (conflict) classificationError.value = feedback
      else classificationNotice.value = feedback
    }
  } finally {
    classificationBusy.value = ''
  }
}

function prepareReply() {
  const thread = selected.value
  if (!thread || busy.value || !canReply.value || !replyText.value.trim()) return
  replyIntent.value = {
    threadId: thread.id, text: replyText.value.trim(),
    destination: deviceLabel(thread.deviceId) + ' · ' + imPlatformLabel(thread.platform) + ' · ' + thread.peerName,
  }
}

async function sendReply() {
  const intent = replyIntent.value
  if (!intent || busy.value || !canReply.value || selected.value?.id !== intent.threadId) return
  const revision = identityRevision
  const tenant = session.user.tenant
  const user = session.user.id
  const current = () => !disposed && revision === identityRevision && tenant === session.user.tenant && user === session.user.id
  busy.value = true
  delete replyResults.value[intent.threadId]
  try {
    const result = await replyImThread(intent.threadId, intent.text)
    if (!current()) return
    replyResults.value[intent.threadId] = { error: false, text: intent.destination + '：任务已提交（' + result.taskId.slice(0, 8) + '），等待手机执行；不是发送成功确认。' }
    if (drafts.value[intent.threadId]?.trim() === intent.text) delete drafts.value[intent.threadId]
    if (selected.value?.id === intent.threadId) await refreshSelectedMessages()
  } catch (error) {
    if (!current()) return
    replyResults.value[intent.threadId] = { error: true, text: intent.destination + '：' + (error instanceof ImApiError
      ? error.message
      : '未能确认请求结果，任务可能已提交。请先刷新核对任务记录，勿直接重复发送。') }
  } finally {
    if (current()) {
      busy.value = false
      replyIntent.value = null
    }
  }
}

/* ---------------- 设备监控设置 ---------------- */

interface ConfigDeviceOption { id: string; name: string }

const deviceOptions = ref<ConfigDeviceOption[]>([])
const cfgDevice = ref('')
const configOpen = ref(false)
const cfgBusy = ref(false)
const cfgMessage = ref('')
const cfgMessageIsError = ref(false)
const cfgErrors = ref<string[]>([])
const cfg = ref<ImMonitorConfig | null>(null)
const deviceConfigs = ref(new Map<string, ImMonitorConfig>())
const replyDisabledReason = computed(() => {
  const thread = selected.value
  if (!thread) return '请选择会话'
  if (!session.can('device.control')) return '当前角色没有设备回复权限'
  if (thread.platform !== 'xianyu') return '当前仅支持闲鱼文字回复，此平台暂不支持'
  const config = deviceConfigs.value.get(thread.deviceId)
  if (!config || config.receiveOnly === undefined) return '回复配置尚未核验，暂不可发送'
  if (config.receiveOnly !== false) return '当前仅接收消息，服务端未允许回复'
  return ''
})
const canReply = computed(() => !replyDisabledReason.value)

const configDeviceOptions = computed(() => {
  const merged = new Map<string, ConfigDeviceOption>()
  for (const option of deviceOptions.value) merged.set(option.id, option)
  for (const id of deviceIds.value) {
    if (!merged.has(id)) merged.set(id, { id, name: `设备 ${id.slice(0, 8)}` })
  }
  return [...merged.values()]
})

const dmFilteredPlatforms = computed(() =>
  (cfg.value?.platforms ?? []).filter((key) => imPlatformDmFiltered(key)).map(imPlatformLabel),
)

async function loadDeviceOptions() {
  const revision = identityRevision
  if (!controlApiConfigured) {
    deviceOptions.value = []
    return
  }
  try {
    const rows = await createControlApiClient().devices()
    if (disposed || revision !== identityRevision) return
    deviceOptions.value = rows.map((row) => {
      const mapped = mapControlDevice(row)
      return { id: mapped.id, name: mapped.name }
    })
  } catch {
    if (disposed || revision !== identityRevision) return
    deviceOptions.value = []
  }
}

/** 会话列表按设备拉取监控配置：值班徽标 + 配置面板共用，失败静默（徽标缺失不阻塞收件箱）。 */
async function loadDeviceConfigs() {
  const request = ++deviceConfigsRequest
  const ids = new Set([...deviceIds.value, ...(cfgDevice.value ? [cfgDevice.value] : [])])
  const entries = await Promise.all(
    [...ids].map(async (id) => {
      try {
        return [id, await fetchImConfig(id)] as const
      } catch {
        return null
      }
    }),
  )
  if (!disposed && request === deviceConfigsRequest) {
    deviceConfigs.value = new Map(entries.filter((entry): entry is readonly [string, ImMonitorConfig] => entry !== null))
  }
}

let deviceConfigsRequest = 0
let configRequest = 0
async function loadConfig() {
  const request = ++configRequest
  const deviceId = cfgDevice.value
  cfg.value = null
  cfgMessage.value = ''
  cfgMessageIsError.value = false
  cfgErrors.value = []
  if (!deviceId) return
  try {
    const next = await fetchImConfig(deviceId)
    if (disposed || request !== configRequest || deviceId !== cfgDevice.value) return
    cfg.value = next
    await loadDeviceConfigs()
  } catch (error) {
    if (disposed || request !== configRequest || deviceId !== cfgDevice.value) return
    cfg.value = null
    cfgMessageIsError.value = true
    cfgMessage.value = error instanceof ImApiError ? error.message : '监控设置加载失败'
  }
}

function togglePlatform(key: string) {
  if (!cfg.value || !canEditConfig.value) return
  const set = new Set(cfg.value.platforms)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  cfg.value.platforms = [...set]
  cfgErrors.value = []
}

const cfgDutyStatus = computed(() => (cfg.value ? imDutyStatus(cfg.value) : 'off'))

async function saveConfig() {
  if (!cfg.value || !cfgDevice.value || !canEditConfig.value || cfgBusy.value) return
  const deviceId = cfgDevice.value
  const request = configRequest
  const current = () => !disposed && request === configRequest && deviceId === cfgDevice.value
  cfgMessage.value = ''
  cfgMessageIsError.value = false
  const draft = {
    enabled: cfg.value.enabled,
    platforms: [...cfg.value.platforms],
    mode: cfg.value.mode,
    dutyStart: cfg.value.dutyStart,
    dutyEnd: cfg.value.dutyEnd,
  }
  const errors = validateImConfigDraft(draft)
  cfgErrors.value = errors
  if (errors.length > 0) return
  cfgBusy.value = true
  try {
    const saved = await saveImConfig(deviceId, draft)
    if (!current()) return
    cfg.value = saved
    cfgMessageIsError.value = false
    cfgMessage.value = '已保存，手机下一轮同步生效（约 1 分钟内）'
    await loadDeviceConfigs()
  } catch (error) {
    if (!current()) return
    cfgMessageIsError.value = true
    cfgMessage.value = error instanceof ImApiError ? error.message : '保存监控设置失败'
  } finally {
    cfgBusy.value = false
  }
}

watch(() => [session.user.id, session.user.tenant], () => {
  ++identityRevision
  ++contextRevision
  ++threadRequest
  ++deviceConfigsRequest
  ++configRequest
  clearSelection()
  drafts.value = {}
  replyResults.value = {}
  busy.value = false
  threads.value = []
  threadsHasMore.value = false
  bucketCounts.value = null
  deviceConfigs.value = new Map()
  cfg.value = null
  cfgDevice.value = ''
  cfgMessage.value = ''
  cfgErrors.value = []
  cfgBusy.value = false
  cfgMessageIsError.value = false
  deviceOptions.value = []
  searchText.value = ''
  deviceFilter.value = ''
  void loadDeviceOptions()
  errorMessage.value = ''
  successMessage.value = ''
  classificationBusy.value = ''
  void refreshThreads(false)
}, { flush: 'sync' })

async function openCollectionSettings() {
  if (!selected.value) return
  cfgDevice.value = selected.value.deviceId
  configOpen.value = true
  void loadConfig()
  await nextTick()
  document.getElementById('im-monitor-config')?.scrollIntoView?.({ block: 'start' })
}

watch(deviceFilter, (value) => {
  if (value && value !== cfgDevice.value) {
    cfgDevice.value = value
    void loadConfig()
  }
})

watch([deviceFilter, unreadOnly, bucket], () => {
  ++contextRevision
  threads.value = []
  threadsHasMore.value = false
  bucketCounts.value = null
  errorMessage.value = ''
  successMessage.value = ''
  void refreshThreads(false)
}, { flush: 'sync' })

watch(configDeviceOptions, (options) => {
  if (cfgDevice.value && options.some((option) => option.id === cfgDevice.value)) return
  const preferred = deviceFilter.value && options.some((option) => option.id === deviceFilter.value)
    ? deviceFilter.value
    : options[0]?.id ?? ''
  if (preferred && preferred !== cfgDevice.value) {
    cfgDevice.value = preferred
    void loadConfig()
  }
})

/* ---------------- 展示辅助 ---------------- */

function timeLabel(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** 值班模式状态徽标（按设备计算，仅 DUTY 设备显示）。 */
const dutyChips = computed(() => {
  const chips = new Map<string, { label: string; state: string }>()
  for (const [id, config] of deviceConfigs.value) {
    const status = imDutyStatus(config)
    if (status !== 'off') chips.set(id, { label: imDutyStatusLabel(status), state: status })
  }
  return chips
})

function deviceShort(id: string): string {
  return id.length > 12 ? `${id.slice(0, 12)}…` : id
}

function deviceLabel(id: string): string {
  const name = deviceNameById.value.get(id)?.trim()
  const shortId = deviceShort(id)
  const shortIdCollision = filterDeviceOptions.value.some((option) => option.id !== id && deviceShort(option.id) === shortId)
  const identifier = shortIdCollision ? id : shortId
  if (!name || name === id || name === '设备 ' + shortId) return '设备 ' + identifier
  const duplicate = filterDeviceOptions.value.some((option) => option.id !== id && option.name.trim() === name)
  return duplicate ? name + '（' + identifier + '）' : name
}

const POLL_INTERVAL_MS = 5_000
let pollTimer: ReturnType<typeof setInterval> | null = null

let pollInFlight = false
async function pollInbox() {
  if (disposed || pollInFlight || threadsLoading.value || moreThreadsLoading.value || classificationBusy.value || document.visibilityState !== 'visible') return
  pollInFlight = true
  try {
    if (await refreshThreads(true)) await refreshSelectedMessages()
  } finally {
    pollInFlight = false
  }
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling() {
  stopPolling()
  if (document.visibilityState !== 'visible') return
  pollTimer = setInterval(() => { void pollInbox() }, POLL_INTERVAL_MS)
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    void pollInbox()
    startPolling()
  } else {
    stopPolling()
  }
}

onMounted(() => {
  void refreshThreads(false)
  void loadDeviceOptions()
  document.addEventListener('visibilitychange', onVisibilityChange)
  startPolling()
})

onBeforeUnmount(() => {
  disposed = true
  ++threadRequest
  ++messageRequest
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <section class="yy-panel im-inbox">
    <header class="yy-page-head">
      <div>
        <h1>消息聚合</h1>
        <p class="yy-sub im-scope">{{ deviceFilter ? '当前筛选：' + deviceLabel(deviceFilter) : '汇总全部设备已上报的会话，无需逐台查看' }} · 页面可见时每 5 秒自动刷新</p>
      </div>
      <div class="yy-actions">
        <button v-if="configDeviceOptions.length" class="yy-btn" type="button" :aria-expanded="configOpen" aria-controls="im-monitor-config" @click="configOpen = !configOpen">设备监控设置</button>
        <label class="yy-field">
          <span>筛选设备</span>
          <select v-model="deviceFilter" :title="deviceFilter || '全部设备'">
            <option value="">全部设备</option>
            <option v-for="option in filterDeviceOptions" :key="option.id" :value="option.id" :title="option.id">
              {{ deviceLabel(option.id) }}
            </option>
          </select>
        </label>
        <label class="yy-check">
          <input v-model="unreadOnly" type="checkbox" />
          <span>只看未读</span>
        </label>
        <button class="yy-btn im-refresh" type="button" title="刷新收件箱" aria-label="刷新收件箱" :disabled="!!classificationBusy || threadsLoading || moreThreadsLoading" @click="refreshInbox">
          <RefreshCw :size="16" aria-hidden="true" />
        </button>
      </div>
    </header>

    <p v-if="errorMessage" class="yy-error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="yy-ok">{{ successMessage }}</p>
    <p v-if="classificationError" class="yy-error" role="alert">{{ classificationError }}</p>
    <p v-if="classificationNotice" class="yy-ok" role="status">{{ classificationNotice }}</p>

    <p v-if="cfgMessageIsError && !configOpen" class="yy-error" role="alert">{{ cfgMessage }}，请展开设备监控设置处理。</p>
    <section v-if="configDeviceOptions.length > 0" v-show="configOpen" id="im-monitor-config" class="yy-panel im-config" aria-label="设备监控设置">
      <header class="im-config-head">
        <div>
          <h2>设备监控设置</h2>
          <p class="yy-sub">仅设置所选设备的监听方式，不影响上方消息筛选。保存后随手机下一轮同步生效。</p>
        </div>
        <label class="yy-field">
          <span>设置设备</span>
          <select v-model="cfgDevice" :title="cfgDevice" @change="loadConfig">
            <option value="" disabled>选择设备</option>
            <option v-for="option in configDeviceOptions" :key="option.id" :value="option.id" :title="option.id">
              {{ deviceLabel(option.id) }}
            </option>
          </select>
        </label>
      </header>
      <template v-if="cfg">
        <div class="im-config-row">
          <label class="yy-check"><input v-model="cfg.enabled" type="checkbox" :disabled="!canEditConfig || cfgBusy" /><span>监听总开关</span></label>
          <label v-for="option in IM_PLATFORM_OPTIONS" :key="option.key" class="yy-check">
            <input
              :checked="cfg.platforms.includes(option.key)"
              type="checkbox"
              :disabled="!canEditConfig || cfgBusy"
              @change="togglePlatform(option.key)"
            />
            <span>{{ option.label }}</span>
          </label>
        </div>
        <div class="im-config-row">
          <label class="yy-check">
            <input v-model="cfg.mode" type="radio" value="NOTIFICATION" :disabled="!canEditConfig || cfgBusy" /><span>通知监听（后台，不占手机）</span>
          </label>
          <label class="yy-check">
            <input v-model="cfg.mode" type="radio" value="DUTY" :disabled="!canEditConfig || cfgBusy" /><span>值班模式（驻守消息页）</span>
          </label>
          <template v-if="cfg.mode === 'DUTY'">
            <label class="yy-field"><span>值班起</span><input v-model="cfg.dutyStart" type="time" :disabled="!canEditConfig || cfgBusy" /></label>
            <label class="yy-field"><span>值班止</span><input v-model="cfg.dutyEnd" type="time" :disabled="!canEditConfig || cfgBusy" /></label>
            <span class="im-duty" :data-state="cfgDutyStatus">{{ imDutyStatusLabel(cfgDutyStatus) }}</span>
            <span class="yy-sub">跨零点窗口自动顺延（如 22:00–06:00）</span>
          </template>
        </div>
        <details class="im-config-note">
          <summary>监听范围与过滤说明</summary>
          <p class="yy-sub">
            通道过滤：闲鱼上报全部通知；小红书 / 抖音 / 微信只上报私信类通知通道（message / msg / im / chat / 私信），信息流推送由手机端过滤。
            <template v-if="dmFilteredPlatforms.length > 0">当前受过滤平台：{{ dmFilteredPlatforms.join('、') }}。</template>
          </p>
        </details>
        <p v-if="cfg.updatedAt" class="yy-sub">设置保存时间：{{ timeLabel(cfg.updatedAt) }}</p>
        <p v-if="!canEditConfig" class="yy-sub im-readonly">当前角色只读，仅能查看监控设置。</p>
        <ul v-if="cfgErrors.length > 0" class="yy-error im-config-errors">
          <li v-for="error in cfgErrors" :key="error">{{ error }}</li>
        </ul>
        <div class="im-config-row">
          <button v-if="canEditConfig" class="yy-btn primary" type="button" :disabled="cfgBusy" @click="saveConfig">
            {{ cfgBusy ? '保存中…' : '保存设置' }}
          </button>
        </div>
      </template>
      <p v-if="cfgMessage" class="im-config-feedback" :class="{ error: cfgMessageIsError }" :role="cfgMessageIsError ? 'alert' : 'status'">{{ cfgMessage }}</p>
      <button v-if="cfgMessageIsError && !cfg" class="yy-btn" type="button" @click="loadConfig">重试加载设置</button>
    </section>

    <div class="yy-tabs im-buckets" role="tablist" aria-label="消息分类">
      <button
        v-for="item in IM_BUCKETS"
        :id="`im-tab-${item.key}`"
        :key="item.key"
        type="button"
        role="tab"
        class="yy-tab"
        :class="{ active: bucket === item.key }"
        :aria-selected="bucket === item.key"
        aria-controls="im-inbox-panel"
        @click="bucket = item.key"
      >
        {{ item.label }}
        <span :title="bucketCounts ? '匹配会话数' : '服务端未提供分类计数'">{{ bucketCounts?.[item.key] ?? '—' }}</span>
      </button>
    </div>
    <label class="yy-field im-search"><span>搜索已加载会话</span><input v-model="searchText" type="search" placeholder="昵称、设备、最近消息" /></label>
    <p class="yy-sub">搜索仅覆盖已加载会话及最近消息，不搜索完整聊天历史。</p>
    <p class="yy-sub im-bucket-hint">默认看用户消息；未分类内容在「待确认」，查看所有分类请选「全部」。</p>
    <div id="im-inbox-panel" class="im-layout" role="tabpanel" :aria-labelledby="`im-tab-${bucket}`">
      <aside class="im-threads" aria-label="会话列表" :aria-busy="threadsLoading">
        <p v-if="threadsLoading" class="yy-sub" role="status">加载会话中…</p>
        <p v-else-if="visibleThreads.length === 0 && !errorMessage" class="yy-sub">当前分类暂无会话。</p>
        <button
          v-for="thread in visibleThreads"
          :key="thread.id"
          type="button"
          class="im-thread"
          :class="{ active: selected?.id === thread.id }"
          @click="openThread(thread)"
        >
          <span class="im-peer">
            {{ thread.peerName }}
            <em v-if="thread.unreadCount > 0" class="im-badge" title="整个会话未读数">{{ thread.unreadCount }}</em>
            <span class="im-platform" :data-platform="thread.platform">{{ imPlatformLabel(thread.platform) }}</span>
            <span v-if="thread.lastDirection === 'IN'" class="im-platform">{{ categoryLabel(thread.lastMessageClassification?.category) }}</span>
            <span v-if="dutyChips.get(thread.deviceId)" class="im-duty" :data-state="dutyChips.get(thread.deviceId)?.state">
              {{ dutyChips.get(thread.deviceId)?.label }}
            </span>
          </span>
          <span class="im-summary" :class="{ pending: !threadSummary(thread) }">
            {{ isNotificationPreview(thread.lastMessageText) ? '通知提示 · 正文待采集' : threadSummary(thread) || '暂无正文' }}
          </span>
          <span class="im-meta im-thread-meta">
            <span>{{ thread.lastDirection === 'IN' ? '收到' : '回复任务' }} · {{ timeLabel(thread.lastMessageAt) }}</span>
            <span class="im-device-name" :title="deviceLabel(thread.deviceId) + ' · ' + thread.deviceId">{{ deviceLabel(thread.deviceId) }}</span>
          </span>
        </button>
        <button v-if="threadsHasMore" class="yy-btn" type="button" :disabled="threadsLoading || moreThreadsLoading || !!classificationBusy" @click="loadMoreThreads">
          {{ moreThreadsLoading ? '加载中…' : '加载更多会话' }}
        </button>
      </aside>

      <div class="im-conversation">
        <template v-if="selected">
          <header class="im-conversation-head">
            <strong>{{ selected.peerName }}</strong>
            <span class="im-platform" :data-platform="selected.platform">{{ imPlatformLabel(selected.platform) }}</span>
            <span v-if="dutyChips.get(selected.deviceId)" class="im-duty" :data-state="dutyChips.get(selected.deviceId)?.state">
              {{ dutyChips.get(selected.deviceId)?.label }}
            </span>
            <span class="im-meta im-device-name" :title="deviceLabel(selected.deviceId) + ' · ' + selected.deviceId">{{ deviceLabel(selected.deviceId) }}</span>
          </header>
          <p class="im-context">设备：{{ deviceLabel(selected.deviceId) }} · {{ selected.deviceId }}<br />账号：未核验 · 联系人：{{ selected.peerName }}<br />设备名称不等于登录账号；账号切换后的会话归属需核对。</p>
          <p class="im-context yy-sub">这里只展示已采集消息。通知可能只有提醒；值班采集会在手机进入聊天读取文字，会占用手机界面，也可能标为已读。现有设备能否完整读取仍待验证。</p>
          <div class="im-context"><button class="yy-btn" type="button" @click="openCollectionSettings">查看正文采集设置</button></div>
          <div class="im-stream" :aria-busy="messagesLoading">
            <p v-if="messagesLoading" class="yy-sub" role="status">加载消息中…</p>
            <div
              v-for="message in messages"
              :key="message.id"
              class="im-bubble"
              :class="message.direction === 'IN' ? 'in' : 'out'"
            >
              <template v-if="message.direction === 'IN' && isNotificationPreview(message.text)">
                <strong>通知提示 · 正文待采集</strong>
                <details><summary>原始通知文字</summary><span class="im-text">{{ message.text }}</span><p class="yy-sub">这段文字可能只是提醒，手机通知可能未提供具体内容。</p></details>
              </template>
              <span v-else class="im-text">{{ message.text }}</span>
              <span v-if="message.direction === 'OUT'" class="im-delivery" :data-state="message.deliveryState ?? 'UNKNOWN'">{{ deliveryLabel(message.deliveryState) }}</span>
              <span class="im-time">{{ timeLabel(message.occurredAt) }}</span>
              <MessageClassification
                :message="message"
                :can-edit="canEditConfig"
                :busy="!!classificationBusy"
                @classify="changeClassification(message, $event)"
                @reclassify="changeClassification(message, null, true)"
              />
            </div>
            <p v-if="!messagesLoading && messages.length === 0" class="yy-sub">当前分类暂无消息记录。</p>
          </div>
          <div class="im-reply-panel">
            <p v-if="!canReply" class="im-readonly">只读收件箱 · {{ replyDisabledReason }}</p>
            <p v-else class="yy-sub">回复目标：{{ deviceLabel(selected.deviceId) }} · {{ imPlatformLabel(selected.platform) }} · {{ selected.peerName }}。发送前请确认手机当前账号。</p>
            <p v-if="replyFeedback" :class="replyFeedback.error ? 'yy-error' : 'yy-ok'" :role="replyFeedback.error ? 'alert' : 'status'">{{ replyFeedback.text }}</p>
            <form class="im-composer" @submit.prevent>
              <textarea v-model="replyText" aria-label="回复内容" rows="3" maxlength="500" placeholder="输入回复，Enter 换行；点击按钮后确认提交" :disabled="!canReply || busy || !!replyIntent" />
              <button class="yy-btn primary" type="button" :disabled="!canReply || busy || !replyText.trim() || !!replyIntent" @click="prepareReply">{{ busy ? '提交中…' : '核对回复' }}</button>
            </form>
            <div v-if="replyIntent" class="im-confirm" role="region" aria-label="确认回复">
              <strong>确认提交给 {{ replyIntent.destination }}</strong>
              <p class="im-text">{{ replyIntent.text }}</p>
              <p class="yy-sub">提交后由手机执行，结果以任务记录为准；不会自动重试。</p>
              <button class="yy-btn" type="button" :disabled="busy" @click="replyIntent = null">取消</button>
              <button class="yy-btn primary" type="button" :disabled="busy || !canReply" @click="sendReply">确认提交回复任务</button>
            </div>
          </div>
        </template>
        <p v-else class="yy-sub im-empty">从左侧选择一个会话查看消息。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.im-inbox { color: var(--ink); font-size: 13px; line-height: 1.5; }
.im-inbox h1 { margin: 0 0 4px; font-size: 22px; line-height: 1.3; }
.yy-sub { margin: 6px 0; color: var(--muted); font-size: 12px; }
.yy-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; padding: 6px 11px; border: 1px solid var(--line-strong); border-radius: 5px; color: var(--ink); background: var(--surface); font-size: 12px; font-weight: 600; }
.yy-btn.primary { color: #fff; border-color: var(--accent); background: var(--accent); }
.yy-btn:active:not(:disabled) { transform: scale(.98); }
.im-inbox :is(button, select, input, textarea, summary):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.yy-field { color: var(--muted); font-size: 12px; }
.yy-field select, .yy-field input, .im-composer textarea { padding: 7px 9px; color: var(--ink); background: var(--surface); border: 1px solid var(--line-strong); border-radius: 5px; font: inherit; }
.yy-field select { width: 210px; text-overflow: ellipsis; }
.yy-check { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }
.yy-check input { margin: 0; accent-color: var(--accent); }
.yy-error, .yy-ok { margin: 8px 0; font-size: 12px; }
.yy-error { color: var(--bad); }
.yy-ok { color: var(--good); }
.im-config { padding: 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
.im-config-note summary { color: var(--muted); font-size: 12px; cursor: pointer; }
.im-bucket-hint { margin: 0 0 12px; }
.im-thread-meta { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.im-thread-meta > span:first-child { flex-shrink: 0; }
.im-device-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-conversation-head .im-device-name { width: auto; flex: 1; text-align: right; }
@media (hover: hover) { .yy-btn:hover:not(:disabled) { border-color: var(--accent); } .im-thread:hover { border-color: var(--accent); } }

.yy-page-head { flex-wrap: wrap; align-items: flex-start; }
.yy-page-head > div { min-width: 0; max-width: 100%; }
.yy-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.yy-field { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; }
.yy-field > span { flex-shrink: 0; }
.yy-field select, .yy-field input { min-width: 0; max-width: 100%; }
.im-layout {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
  gap: 16px;
  min-height: 420px;
}
.im-threads {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 560px;
  overflow-y: auto;
}
.im-thread {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--line, #dce1e1);
  border-radius: 10px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}
.im-thread.active {
  border-color: var(--accent, #166b5b);
  background: #f0fbf9;
}
.im-peer {
  font-weight: 600;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.im-badge {
  background: #e11d48;
  color: #fff;
  font-size: 12px;
  border-radius: 999px;
  padding: 0 8px;
  font-style: normal;
}
.im-platform {
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #334155;
  font-size: 11px;
  font-weight: 500;
}
.im-platform[data-platform='xianyu'] { border-color: #fecdd3; background: #fff1f2; color: #9f1239; }
.im-platform[data-platform='xhs'] { border-color: #fecdd3; background: #fff5f6; color: #be123c; }
.im-platform[data-platform='douyin'] { border-color: #cbd5e1; background: #f8fafc; color: #1f2937; }
.im-platform[data-platform='wechat'] { border-color: #bbf7d0; background: #f0fdf4; color: #166534; }
.im-duty {
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
}
.im-duty[data-state='inside'] { border-color: #a7f3d0; background: #ecfdf5; color: #065f46; }
.im-summary {
  max-width: 100%;
  color: #334155;
  font-size: 12.5px;
  overflow: hidden;
  display: block;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.im-summary.pending {
  color: #94a3b8;
  font-style: italic;
}
.im-meta {
  width: 100%;
  color: #64748b;
  font-size: 12px;
}
.im-conversation {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line, #dce1e1);
  border-radius: 12px;
  background: #fff;
  min-height: 420px;
}
.im-conversation-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line, #dce1e1);
}
.im-stream {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  overflow-y: auto;
}
.im-bubble {
  max-width: 70%;
  border-radius: 12px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.im-bubble.in {
  align-self: flex-start;
  background: #f1f5f9;
}
.im-bubble.out {
  align-self: flex-end;
  background: #dcfce9;
}
.im-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.im-time {
  font-size: 11px;
  color: #64748b;
}
.im-context, .im-reply-panel { padding: 0 14px; }
.im-context { margin: 10px 0 0; overflow-wrap: anywhere; }
.im-search { margin-bottom: 4px; }
.im-confirm { padding: 12px; margin-bottom: 12px; background: #f8fafc; border: 1px solid var(--line); border-radius: 8px; overflow-wrap: anywhere; }
.im-delivery { font-size: 11px; color: #475569; }
.im-delivery[data-state="FAILED"] { color: #b91c1c; }
.im-composer {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--line, #dce1e1);
}
.im-composer textarea {
  flex: 1;
  min-width: 0;
  resize: vertical;
}
.im-empty {
  margin: auto;
}
.im-config { margin-bottom: 12px; }
.im-config-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.im-config-head h2 { margin: 0; font-size: 15px; }
.im-config-row { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 10px; }
.im-config-note { margin-top: 10px; }
.im-config-errors { margin: 8px 0 0; padding-left: 18px; }
.im-config-feedback { font-size: 13px; color: #0f766e; }
.im-config-feedback.error { color: #b91c1c; }
.im-readonly { color: #b45309; }
.im-buckets { margin-bottom: 8px; padding-left: 0; background: transparent; }
.im-buckets > button { cursor: pointer; }
.im-buckets > button span { min-width: 2ch; text-align: center; font-variant-numeric: tabular-nums; }
.im-refresh { width: 34px; height: 34px; padding: 0; justify-content: center; }
.im-conversation, .im-threads { min-width: 0; }
.im-conversation-head, .im-peer, .im-meta { overflow-wrap: anywhere; }
@media (max-width: 720px) {
  .im-layout { grid-template-columns: minmax(0, 1fr); }
  .im-threads { max-height: 260px; }
  .im-bubble { max-width: 100%; box-sizing: border-box; }
  .yy-actions { width: 100%; }
  .im-empty { padding: 24px; text-align: center; }
}
</style>
