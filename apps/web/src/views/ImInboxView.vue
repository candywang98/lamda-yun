<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import {
  fetchImConfig,
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
  type ImMonitorConfig,
  type ImThread,
} from '@/api/im'
import { useSessionStore } from '@/stores/session'

const threads = ref<ImThread[]>([])
const selected = ref<ImThread | null>(null)
const messages = ref<ImMessage[]>([])
const deviceFilter = ref('')
const unreadOnly = ref(false)

const session = useSessionStore()
/** 设备监控设置是设备侧运维写操作，沿用 device.control 权限；只读角色仅可查看。 */
const canEditConfig = computed(() => session.can('device.control'))

/* ---------------- 会话流 ---------------- */

const visibleThreads = computed(() =>
  deviceFilter.value
    ? threads.value.filter((thread) => thread.deviceId === deviceFilter.value)
    : threads.value,
)
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

const replyText = ref('')
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

let threadRequest = 0
let disposed = false

async function refreshThreads(preserveSelection = true) {
  const request = ++threadRequest
  try {
    const nextThreads = await listImThreads(deviceFilter.value || undefined, unreadOnly.value)
    if (disposed || request !== threadRequest) return false
    threads.value = nextThreads
    if (!preserveSelection || !nextThreads.some((thread) => thread.id === selected.value?.id)) {
      selected.value = null
      messages.value = []
    } else if (selected.value) {
      selected.value = nextThreads.find((thread) => thread.id === selected.value?.id) ?? selected.value
    }
    errorMessage.value = ''
    await loadDeviceConfigs()
    return true
  } catch (error) {
    if (!disposed && request === threadRequest) {
      errorMessage.value = error instanceof ImApiError ? error.message : '会话列表加载失败'
    }
    return false
  }
}

async function refreshSelectedMessages() {
  const thread = selected.value
  if (!thread) return
  try {
    const nextMessages = await listImMessages(thread.id)
    if (disposed || selected.value?.id !== thread.id) return
    messages.value = nextMessages
    cacheThreadSummary(thread)
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = error instanceof ImApiError ? error.message : '消息加载失败'
  }
}

async function openThread(thread: ImThread) {
  selected.value = thread
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const nextMessages = await listImMessages(thread.id)
    if (disposed || selected.value?.id !== thread.id) return
    messages.value = nextMessages
    cacheThreadSummary(thread)
    if (thread.unreadCount > 0) {
      await markImThreadRead(thread.id)
      thread.unreadCount = 0
    }
  } catch (error) {
    errorMessage.value = error instanceof ImApiError ? error.message : '消息加载失败'
  }
}
/** 会话打开后用本地已见正文回填摘要（后端 lastMessageText 字段位优先）。 */
function cacheThreadSummary(thread: ImThread) {
  const last = messages.value[messages.value.length - 1]
  if (!last) return
  thread.lastMessageText = last.text
}

function threadSummary(thread: ImThread): string {
  if (typeof thread.lastMessageText === 'string' && thread.lastMessageText.trim()) return thread.lastMessageText
  return ''
}

async function sendReply() {
  if (!selected.value || !replyText.value.trim()) return
  busy.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const result = await replyImThread(selected.value.id, replyText.value.trim())
    successMessage.value = `已生成回复任务 ${result.taskId.slice(0, 8)}…，手机将自动打开发送`
    replyText.value = ''
    messages.value = await listImMessages(selected.value.id)
    cacheThreadSummary(selected.value)
    selected.value.lastDirection = 'OUT'
  } catch (error) {
    errorMessage.value = error instanceof ImApiError ? error.message : '回复失败'
  } finally {
    busy.value = false
  }
}

/* ---------------- 设备监控设置 ---------------- */

interface ConfigDeviceOption { id: string; name: string }

const deviceOptions = ref<ConfigDeviceOption[]>([])
const cfgDevice = ref('')
const cfgBusy = ref(false)
const cfgMessage = ref('')
const cfgMessageIsError = ref(false)
const cfgErrors = ref<string[]>([])
const cfg = ref<ImMonitorConfig | null>(null)
const deviceConfigs = ref(new Map<string, ImMonitorConfig>())

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
  if (!controlApiConfigured) {
    deviceOptions.value = []
    return
  }
  try {
    const rows = await createControlApiClient().devices()
    deviceOptions.value = rows.map((row) => {
      const mapped = mapControlDevice(row)
      return { id: mapped.id, name: mapped.name }
    })
  } catch {
    deviceOptions.value = []
  }
}

/** 会话列表按设备拉取监控配置：值班徽标 + 配置面板共用，失败静默（徽标缺失不阻塞收件箱）。 */
async function loadDeviceConfigs() {
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
  deviceConfigs.value = new Map(entries.filter((entry): entry is readonly [string, ImMonitorConfig] => entry !== null))
}

async function loadConfig() {
  if (!cfgDevice.value) return
  cfgMessage.value = ''
  cfgMessageIsError.value = false
  cfgErrors.value = []
  try {
    cfg.value = await fetchImConfig(cfgDevice.value)
    await loadDeviceConfigs()
  } catch (error) {
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
  if (!cfg.value || !cfgDevice.value) return
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
    cfg.value = await saveImConfig(cfgDevice.value, draft)
    cfgMessageIsError.value = false
    cfgMessage.value = '已保存，手机下一轮同步生效（约 1 分钟内）'
    await loadDeviceConfigs()
  } catch (error) {
    cfgMessageIsError.value = true
    cfgMessage.value = error instanceof ImApiError ? error.message : '保存监控设置失败'
  } finally {
    cfgBusy.value = false
  }
}

watch(deviceFilter, (value) => {
  if (value && value !== cfgDevice.value) {
    cfgDevice.value = value
    void loadConfig()
  }
})

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
  return `${deviceNameById.value.get(id) ?? '设备'}（${deviceShort(id)}）`
}

const POLL_INTERVAL_MS = 5_000
let pollTimer: ReturnType<typeof setInterval> | null = null

let pollInFlight = false
async function pollInbox() {
  if (disposed || pollInFlight || document.visibilityState !== 'visible') return
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
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <section class="yy-panel">
    <header class="yy-page-head">
      <div>
        <h1>消息聚合</h1>
        <p class="yy-sub">手机消息自动汇聚到这里；回复会生成受控任务由手机发出。</p>
      </div>
      <div class="yy-actions">
        <label class="yy-field">
          <span>设备</span>
          <select v-model="deviceFilter" @change="refreshThreads(false)">
            <option value="">全部设备</option>
            <option v-for="option in filterDeviceOptions" :key="option.id" :value="option.id">
              {{ option.name }}（{{ deviceShort(option.id) }}）
            </option>
          </select>
        </label>
        <label class="yy-check">
          <input v-model="unreadOnly" type="checkbox" @change="refreshThreads(false)" />
          <span>只看未读</span>
        </label>
        <button class="yy-btn" type="button" @click="refreshThreads()">刷新</button>
      </div>
    </header>

    <p v-if="errorMessage" class="yy-error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="yy-ok">{{ successMessage }}</p>

    <section v-if="configDeviceOptions.length > 0" class="yy-panel im-config">
      <header class="im-config-head">
        <div>
          <h2>设备监控设置</h2>
          <p class="yy-sub">按设备选择监听平台与值班模式；保存后随手机下一轮同步生效（约 1 分钟内）。</p>
        </div>
        <label class="yy-field">
          <span>设备</span>
          <select v-model="cfgDevice" :disabled="!canEditConfig" @change="loadConfig">
            <option value="" disabled>选择设备</option>
            <option v-for="option in configDeviceOptions" :key="option.id" :value="option.id">
              {{ option.name }}（{{ option.id.slice(0, 8) }}）
            </option>
          </select>
        </label>
      </header>
      <template v-if="cfg">
        <div class="im-config-row">
          <label class="yy-check"><input v-model="cfg.enabled" type="checkbox" :disabled="!canEditConfig" /><span>监听总开关</span></label>
          <label v-for="option in IM_PLATFORM_OPTIONS" :key="option.key" class="yy-check">
            <input
              :checked="cfg.platforms.includes(option.key)"
              type="checkbox"
              :disabled="!canEditConfig"
              @change="togglePlatform(option.key)"
            />
            <span>{{ option.label }}</span>
          </label>
        </div>
        <div class="im-config-row">
          <label class="yy-check">
            <input v-model="cfg.mode" type="radio" value="NOTIFICATION" :disabled="!canEditConfig" /><span>通知监听（后台，不占手机）</span>
          </label>
          <label class="yy-check">
            <input v-model="cfg.mode" type="radio" value="DUTY" :disabled="!canEditConfig" /><span>值班模式（驻守消息页，全文零漏收）</span>
          </label>
          <template v-if="cfg.mode === 'DUTY'">
            <label class="yy-field"><span>值班起</span><input v-model="cfg.dutyStart" type="time" :disabled="!canEditConfig" /></label>
            <label class="yy-field"><span>值班止</span><input v-model="cfg.dutyEnd" type="time" :disabled="!canEditConfig" /></label>
            <span class="im-duty" :data-state="cfgDutyStatus">{{ imDutyStatusLabel(cfgDutyStatus) }}</span>
            <span class="yy-sub">跨零点窗口自动顺延（如 22:00–06:00）</span>
          </template>
        </div>
        <p class="yy-sub im-config-note">
          通道过滤：闲鱼上报全部通知；小红书 / 抖音 / 微信只上报私信类通知通道（message / msg / im / chat / 私信），信息流推送由手机端过滤。
          <template v-if="dmFilteredPlatforms.length > 0">当前受过滤平台：{{ dmFilteredPlatforms.join('、') }}。</template>
        </p>
        <p v-if="cfg.updatedAt" class="yy-sub">上次同步：{{ timeLabel(cfg.updatedAt) }}前保存</p>
        <p v-if="!canEditConfig" class="yy-sub im-readonly">当前角色只读，仅能查看监控设置。</p>
        <ul v-if="cfgErrors.length > 0" class="yy-error im-config-errors">
          <li v-for="error in cfgErrors" :key="error">{{ error }}</li>
        </ul>
        <div class="im-config-row">
          <button v-if="canEditConfig" class="yy-btn primary" type="button" :disabled="cfgBusy" @click="saveConfig">
            {{ cfgBusy ? '保存中…' : '保存设置' }}
          </button>
          <span v-if="cfgMessage" class="im-config-feedback" :class="{ error: cfgMessageIsError }">{{ cfgMessage }}</span>
        </div>
      </template>
    </section>

    <div class="im-layout">
      <aside class="im-threads" aria-label="会话列表">
        <p v-if="visibleThreads.length === 0" class="yy-sub">暂无消息。手机在线收到消息后会出现在这里。</p>
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
            <em v-if="thread.unreadCount > 0" class="im-badge">{{ thread.unreadCount }}</em>
            <span class="im-platform" :data-platform="thread.platform">{{ imPlatformLabel(thread.platform) }}</span>
            <span v-if="dutyChips.get(thread.deviceId)" class="im-duty" :data-state="dutyChips.get(thread.deviceId)?.state">
              {{ dutyChips.get(thread.deviceId)?.label }}
            </span>
          </span>
          <span class="im-summary" :class="{ pending: !threadSummary(thread) }">
            {{ threadSummary(thread) || '暂无正文' }}
          </span>
          <span class="im-meta">
            {{ thread.lastDirection === 'IN' ? '收到' : '已回复' }} · {{ timeLabel(thread.lastMessageAt) }} · {{ deviceLabel(thread.deviceId) }}
          </span>
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
            <span class="im-meta">{{ deviceLabel(selected.deviceId) }}</span>
          </header>
          <div class="im-stream">
            <div
              v-for="message in messages"
              :key="message.id"
              class="im-bubble"
              :class="message.direction === 'IN' ? 'in' : 'out'"
            >
              <span class="im-text">{{ message.text }}</span>
              <span class="im-time">{{ timeLabel(message.occurredAt) }}</span>
            </div>
            <p v-if="messages.length === 0" class="yy-sub">该会话暂无消息记录。</p>
          </div>
          <form class="im-composer" @submit.prevent="sendReply">
            <textarea
              v-model="replyText"
              rows="2"
              maxlength="500"
              placeholder="输入回复（≤500 字），发送后生成手机任务"
              :disabled="busy"
            />
            <button class="yy-btn primary" type="submit" :disabled="busy || !replyText.trim()">
              {{ busy ? '发送中…' : '发送回复' }}
            </button>
          </form>
        </template>
        <p v-else class="yy-sub im-empty">从左侧选择一个会话查看消息。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.im-layout {
  display: grid;
  grid-template-columns: minmax(240px, 320px) 1fr;
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
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--yy-line, #d8dee6);
  border-radius: 10px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}
.im-thread.active {
  border-color: var(--yy-primary, #0f766e);
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
  color: #64748b;
  font-size: 12px;
}
.im-conversation {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--yy-line, #d8dee6);
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
  border-bottom: 1px solid var(--yy-line, #d8dee6);
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
.im-composer {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--yy-line, #d8dee6);
}
.im-composer textarea {
  flex: 1;
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
</style>
