<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  fetchImConfig,
  ImApiError,
  listImMessages,
  listImThreads,
  markImThreadRead,
  replyImThread,
  saveImConfig,
  type ImMessage,
  type ImMonitorConfig,
  type ImThread,
} from '@/api/im'

const threads = ref<ImThread[]>([])
const selected = ref<ImThread | null>(null)
const messages = ref<ImMessage[]>([])
const deviceFilter = ref('')
const unreadOnly = ref(false)
const cfgDevice = ref('')
const cfgBusy = ref(false)
const cfgMessage = ref('')
const cfg = ref<ImMonitorConfig | null>(null)
const platformOptions = [
  { key: 'xianyu', label: '闲鱼' },
  { key: 'xhs', label: '小红书' },
  { key: 'douyin', label: '抖音' },
  { key: 'wechat', label: '微信（仅收不发）' },
]

async function loadConfig() {
  if (!cfgDevice.value) return
  cfgMessage.value = ''
  try {
    cfg.value = await fetchImConfig(cfgDevice.value)
  } catch (error) {
    cfgMessage.value = error instanceof ImApiError ? error.message : '配置加载失败'
  }
}

function togglePlatform(key: string) {
  if (!cfg.value) return
  const set = new Set(cfg.value.platforms)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  if (set.size > 0) cfg.value.platforms = [...set]
}

async function saveConfig() {
  if (!cfg.value || !cfgDevice.value) return
  cfgBusy.value = true
  cfgMessage.value = ''
  try {
    cfg.value = await saveImConfig(cfgDevice.value, {
      enabled: cfg.value.enabled,
      platforms: cfg.value.platforms,
      mode: cfg.value.mode,
      dutyStart: cfg.value.dutyStart,
      dutyEnd: cfg.value.dutyEnd,
    })
    cfgMessage.value = '已保存，手机下一轮同步生效（约 1 分钟内）'
  } catch (error) {
    cfgMessage.value = error instanceof ImApiError ? error.message : '保存失败'
  } finally {
    cfgBusy.value = false
  }
}
const replyText = ref('')
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const visibleThreads = computed(() =>
  deviceFilter.value
    ? threads.value.filter((thread) => thread.deviceId === deviceFilter.value)
    : threads.value,
)
const deviceIds = computed(() => [...new Set(threads.value.map((thread) => thread.deviceId))])

async function refreshThreads(preserveSelection = true) {
  try {
    threads.value = await listImThreads(deviceFilter.value || undefined, unreadOnly.value)
    if (!preserveSelection || !threads.value.some((t) => t.id === selected.value?.id)) {
      selected.value = null
      messages.value = []
    }
  } catch (error) {
    errorMessage.value = error instanceof ImApiError ? error.message : '会话列表加载失败'
  }
}

async function openThread(thread: ImThread) {
  selected.value = thread
  errorMessage.value = ''
  successMessage.value = ''
  try {
    messages.value = await listImMessages(thread.id)
    if (thread.unreadCount > 0) {
      await markImThreadRead(thread.id)
      thread.unreadCount = 0
    }
  } catch (error) {
    errorMessage.value = error instanceof ImApiError ? error.message : '消息加载失败'
  }
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
    selected.value.lastDirection = 'OUT'
  } catch (error) {
    errorMessage.value = error instanceof ImApiError ? error.message : '回复失败'
  } finally {
    busy.value = false
  }
}

function timeLabel(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  void refreshThreads(false)
})
</script>

<template>
  <section class="yy-panel">
    <header class="yy-page-head">
      <div>
        <h1>消息聚合</h1>
        <p class="yy-sub">手机闲鱼消息自动汇聚到这里；回复会生成受控任务由手机发出。</p>
      </div>
      <div class="yy-actions">
        <label class="yy-field">
          <span>设备</span>
          <select v-model="deviceFilter" @change="refreshThreads(false)">
            <option value="">全部</option>
            <option v-for="id in deviceIds" :key="id" :value="id">{{ id.slice(0, 8) }}</option>
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

    <section v-if="deviceIds.length > 0" class="yy-panel im-config">
      <header class="im-config-head">
        <h2>监听设置</h2>
        <select v-model="cfgDevice" @change="loadConfig">
          <option value="" disabled>选择设备</option>
          <option v-for="id in deviceIds" :key="id" :value="id">{{ id.slice(0, 8) }}</option>
        </select>
      </header>
      <template v-if="cfg">
        <div class="im-config-row">
          <label class="yy-check"><input v-model="cfg.enabled" type="checkbox" /><span>监听总开关</span></label>
          <label v-for="option in platformOptions" :key="option.key" class="yy-check">
            <input
              :checked="cfg.platforms.includes(option.key)"
              type="checkbox"
              @change="togglePlatform(option.key)"
            />
            <span>{{ option.label }}</span>
          </label>
        </div>
        <div class="im-config-row">
          <label class="yy-check">
            <input v-model="cfg.mode" type="radio" value="NOTIFICATION" /><span>通知监听（后台，不占手机）</span>
          </label>
          <label class="yy-check">
            <input v-model="cfg.mode" type="radio" value="DUTY" /><span>值班模式（驻守消息页，全文零漏收）</span>
          </label>
          <template v-if="cfg.mode === 'DUTY'">
            <label class="yy-field"><span>值班起</span><input v-model="cfg.dutyStart" type="time" /></label>
            <label class="yy-field"><span>值班止</span><input v-model="cfg.dutyEnd" type="time" /></label>
          </template>
        </div>
        <div class="im-config-row">
          <button class="yy-btn primary" type="button" :disabled="cfgBusy" @click="saveConfig">
            {{ cfgBusy ? '保存中…' : '保存设置' }}
          </button>
          <span v-if="cfgMessage" class="yy-sub">{{ cfgMessage }}</span>
        </div>
      </template>
    </section>

    <div class="im-layout">
      <aside class="im-threads" aria-label="会话列表">
        <p v-if="visibleThreads.length === 0" class="yy-sub">暂无消息。手机在线收到闲鱼消息后会出现在这里。</p>
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
          </span>
          <span class="im-meta">
            {{ thread.lastDirection === 'IN' ? '收到' : '已回复' }} · {{ timeLabel(thread.lastMessageAt) }}
          </span>
        </button>
      </aside>

      <div class="im-conversation">
        <template v-if="selected">
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
  grid-template-columns: minmax(220px, 300px) 1fr;
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
</style>

<style scoped>
.im-config { margin-bottom: 4px; }
.im-config-head { display: flex; align-items: center; gap: 12px; }
.im-config-head h2 { margin: 0; font-size: 15px; }
.im-config-row { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 10px; }
</style>
