<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { PlatformTaskView } from '@cloudctl/api-contracts'
import PageHeader from '@/components/PageHeader.vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice, presenceLabel } from '@/api/devices'
import { useSessionStore } from '@/stores/session'
const api = createControlApiClient()
const session = useSessionStore()
const tasks = ref<PlatformTaskView[]>([])
const devices = ref<ReturnType<typeof mapControlDevice>[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const state = ref('')
const device = ref('')
const command = ref('')
const page = ref(1)
const labels: Record<string, string> = {
  QUEUED: '排队中', WAITING_MATERIALS: '等待素材', PREFLIGHT: '执行前检查', RUNNING: '执行中',
  PAUSE_REQUESTED: '已请求暂停', PAUSED_WAITING_USER: '已暂停，等待用户处理', RESUME_CHECK: '恢复检查中',
  RECONCILING: '对账中', CANCEL_REQUESTED: '已请求取消', SUCCEEDED: '执行成功', FAILED: '执行失败',
  CANCELLED: '已取消', EXPIRED: '已过期',
}
const states = computed(() => [...new Set([...Object.keys(labels), ...tasks.value.map(t => t.state)])])
const commands = computed(() => [...new Set(tasks.value.map(t => t.commandType))].sort())
const deviceOptions = computed(() => [...new Set([...devices.value.map(d => d.id), ...tasks.value.map(t => t.deviceId)])])
const deviceName = (id: string) => devices.value.find(d => d.id === id)?.name ?? id
const devicePresence = (id: string) => {
  const found = devices.value.find(d => d.id === id)
  return found?.presence ? presenceLabel(found.presence) : '未取得设备状态'
}
const stateLabel = (value: string) => (labels[value] ?? '未识别状态') + ' · ' + value
const timestamp = (value: string | null) => value || '未回传'
const filtered = computed(() => tasks.value.filter(t => {
  const term = search.value.trim().toLowerCase()
  return (!state.value || t.state === state.value) && (!device.value || t.deviceId === device.value)
    && (!command.value || t.commandType === command.value)
    && (!term || [t.id, t.taskId, deviceName(t.deviceId), t.deviceId, t.commandType, t.detail, t.stallReason, t.errorCode].join(' ').toLowerCase().includes(term))
}))
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / 20)))
const rows = computed(() => filtered.value.slice((page.value - 1) * 20, page.value * 20))
watch([search, state, device, command], () => { page.value = 1 })
function reset() { search.value = ''; state.value = ''; device.value = ''; command.value = ''; page.value = 1 }
const message = (e: unknown) => e instanceof Error ? e.message : String(e)
let listGeneration = 0
let detailGeneration = 0
async function refresh() {
  if (loading.value) return
  if (!controlApiConfigured) { error.value = '未配置 Control API，无法读取真实任务。'; return }
  const generation = ++listGeneration
  loading.value = true; error.value = ''
  try {
    const [payload, deviceRows] = await Promise.all([api.listPlatformTasks({ limit: 100 }), api.devices()])
    const raw: unknown = payload
    const items = Array.isArray(raw) ? raw : raw && typeof raw === 'object' && 'items' in raw ? raw.items : null
    if (!Array.isArray(items) || items.some(t => !t || typeof t.id !== 'string' || typeof t.state !== 'string')) throw new Error('任务列表响应格式不正确')
    if (generation !== listGeneration) return
    tasks.value = items; devices.value = deviceRows.map(mapControlDevice)
    page.value = Math.min(page.value, pages.value)
  } catch (e) { if (generation === listGeneration) error.value = '任务加载失败：' + message(e) }
  finally { if (generation === listGeneration) loading.value = false }
}
const detailId = ref('')
const detail = ref<PlatformTaskView | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const verified = ref(false)
const reason = ref('')
const resuming = ref(false)
const feedback = ref('')
const dialog = ref<HTMLElement | null>(null)
let detailTrigger: HTMLElement | null = null
function dialogKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); closeDetail(); return }
  if (event.key !== 'Tab' || !dialog.value) return
  const controls = [...dialog.value.querySelectorAll<HTMLElement>('button, input, textarea, select, summary, [tabindex="0"]')]
    .filter(element => !element.matches(':disabled'))
  const first = controls[0]
  const last = controls.at(-1)
  if (!first) { event.preventDefault(); dialog.value.focus(); return }
  if (!controls.includes(document.activeElement as HTMLElement)) {
    event.preventDefault(); (event.shiftKey ? last : first)?.focus(); return
  }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.value)) {
    event.preventDefault(); last?.focus()
  } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.value)) {
    event.preventDefault(); first.focus()
  }
}
function closeDetail() {
  if (resuming.value) return
  ++detailGeneration
  detailId.value = ''; detail.value = null; verified.value = false; reason.value = ''; detailError.value = ''
  void nextTick(() => { if (detailTrigger?.isConnected) detailTrigger.focus() })
}
async function openDetail(task: PlatformTaskView) {
  if (resuming.value) return
  if (!detailId.value) detailTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const generation = ++detailGeneration
  detailId.value = task.id; detail.value = null; detailLoading.value = true
  detailError.value = ''; verified.value = false; reason.value = ''; feedback.value = ''
  void nextTick(() => { if (generation === detailGeneration) dialog.value?.focus() })
  try {
    const result = await api.getPlatformTask(task.id)
    if (generation !== detailGeneration) return
    if (result.id !== task.id) throw new Error('任务详情标识不匹配')
    detail.value = result
  } catch (e) { if (generation === detailGeneration) detailError.value = '详情加载失败：' + message(e) }
  finally { if (generation === detailGeneration) detailLoading.value = false }
}
const canResume = computed(() => controlApiConfigured && session.can('device.control') && detail.value?.state === 'PAUSED_WAITING_USER')
function retryDetail() {
  const task = tasks.value.find(item => item.id === detailId.value)
  if (task) void openDetail(task)
}
async function resume() {
  if (!canResume.value || !detail.value || resuming.value || !verified.value || reason.value.trim().length < 2) return
  const id = detail.value.id
  const generation = detailGeneration
  resuming.value = true; detailError.value = ''
  try {
    const updated = await api.resumePlatformTask(id, { reason: reason.value.trim(), pageVerified: verified.value })
    if (generation !== detailGeneration) return
    if (updated.id !== id) throw new Error('恢复响应标识不匹配，请重新读取详情')
    detail.value = updated; tasks.value = tasks.value.map(t => t.id === id ? updated : t)
    feedback.value = '恢复请求已提交；当前状态以服务端回执为准。'
  } catch (e) { if (generation === detailGeneration) detailError.value = '恢复失败：' + message(e) }
  finally { resuming.value = false; verified.value = false; reason.value = '' }
}
function exportCsv() {
  const cell = (value: unknown) => {
    const raw = String(value ?? '')
    const safe = /^[\s]*[=+@-]/.test(raw) ? "'" + raw : raw
    return '"' + safe.replaceAll('"', '""') + '"'
  }
  const values = [['任务ID', '设备名', '设备ID', '任务类型', '状态', '详情', '停滞原因', '错误码', '计划时间', '添加时间'],
    ...filtered.value.map(t => [t.id, deviceName(t.deviceId), t.deviceId, t.commandType, t.state, t.detail, t.stallReason, t.errorCode, t.scheduledFor, t.createdAt])]
  const url = URL.createObjectURL(new Blob(['\uFEFF' + values.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = 'platform-tasks.csv'; link.click(); URL.revokeObjectURL(url)
}
onMounted(() => { void refresh() })
onUnmounted(() => { ++listGeneration; ++detailGeneration })
</script>

<template>
  <section class="task-queue">
    <PageHeader title="任务队列" description="查看平台任务与设备执行状态">
      <template #actions><button class="button" :disabled="loading || resuming" @click="refresh">{{ loading ? '刷新中…' : '刷新任务' }}</button><button class="button" :disabled="loading || !!error || !filtered.length" @click="exportCsv">导出筛选结果</button></template>
    </PageHeader>
    <p class="queue-note">仅读取最近最多 100 条任务；筛选、分页和导出仅覆盖已加载范围。设备状态来自本次设备查询。批量删除、批量运行及重试不在本页开放。</p>
    <div class="queue-filters">
      <label>查找<input v-model="search" placeholder="任务 ID、设备名、类型、详情或错误" /></label>
      <label>设备<select v-model="device"><option value="">全部设备</option><option v-for="id in deviceOptions" :key="id" :value="id">{{ deviceName(id) }} · {{ id }}</option></select></label>
      <label>任务状态<select v-model="state"><option value="">全部状态</option><option v-for="value in states" :key="value" :value="value">{{ stateLabel(value) }}</option></select></label>
      <label>任务类型<select v-model="command"><option value="">全部类型</option><option v-for="value in commands" :key="value">{{ value }}</option></select></label>
      <button class="button" @click="reset">还原筛选</button>
    </div>
    <p v-if="loading" role="status">正在加载任务与设备…</p>
    <p v-if="error" role="alert">{{ error }}{{ tasks.length ? ' 下方为上次成功读取的数据。' : '' }}</p>
    <p v-if="!loading && !error && !tasks.length">暂无任务</p>
    <p v-else-if="!loading && !error && !filtered.length">没有符合筛选条件的任务</p>
    <div v-if="rows.length" class="queue-table"><table><thead><tr><th>设备名 / 状态</th><th>任务类型 / ID</th><th>任务状态</th><th>详情 / 停滞 / 错误</th><th>执行时间（计划）</th><th>添加时间</th><th>操作</th></tr></thead><tbody>
      <tr v-for="task in rows" :key="task.id"><td>{{ deviceName(task.deviceId) }}<small>{{ devicePresence(task.deviceId) }} · {{ task.deviceId }}</small></td><td>{{ task.commandType }}<small>{{ task.id }}</small></td><td>{{ stateLabel(task.state) }}</td><td>{{ task.detail || '未回传详情' }}<small v-if="task.stallReason">停滞：{{ task.stallReason }}</small><small v-if="task.errorCode">错误：{{ task.errorCode }}</small></td><td>{{ timestamp(task.scheduledFor) }}</td><td>{{ timestamp(task.createdAt) }}</td><td><button class="button" :disabled="resuming" @click="openDetail(task)">详情</button></td></tr>
    </tbody></table></div>
    <div class="queue-pagination"><span>已加载 {{ tasks.length }} 条 · 筛选 {{ filtered.length }} 条 · 第 {{ page }} / {{ pages }} 页</span><button class="button" :disabled="page <= 1" @click="page--">上一页</button><button class="button" :disabled="page >= pages" @click="page++">下一页</button></div>
    <div v-if="detailId" class="modal-backdrop" @click.self="closeDetail"><section ref="dialog" class="modal queue-detail" role="dialog" aria-modal="true" aria-label="任务详情" tabindex="-1" @keydown="dialogKeydown">
      <div class="modal-header"><h3>任务详情 · {{ detailId }}</h3><button class="button" :disabled="resuming" @click="closeDetail">关闭详情</button></div>
      <div class="modal-body"><p v-if="detailLoading" role="status">正在读取任务详情…</p><p v-if="detailError" role="alert">{{ detailError }}</p><button v-if="detailError && !detail" class="button" :disabled="detailLoading" @click="retryDetail">重试详情</button><p v-if="feedback" role="status">{{ feedback }}</p>
        <template v-if="detail"><p>{{ deviceName(detail.deviceId) }} · {{ stateLabel(detail.state) }}</p><p>任务类型：{{ detail.commandType }} · 执行器状态：{{ detail.runnerStatus }} · 控制模式：{{ detail.controlMode }}</p><p>计划：{{ timestamp(detail.scheduledFor) }} · 开始：{{ timestamp(detail.startedAt) }} · 完成：{{ timestamp(detail.completedAt) }}</p><p>详情：{{ detail.detail || '未回传' }} · 停滞：{{ detail.stallReason || '无' }} · 错误：{{ detail.errorCode || '无' }}</p>
          <details><summary>服务端任务原始字段（参数、结果与对账信息）</summary><pre>{{ JSON.stringify(detail, null, 2) }}</pre></details>
          <fieldset v-if="detail.state === 'PAUSED_WAITING_USER'" :disabled="resuming || !canResume"><legend>交还控制权并继续原任务</legend><p>请先检查设备当前页面；恢复请求可能继续执行原任务。</p><label><input v-model="verified" type="checkbox" />我已核验设备当前页面，可以交还控制权</label><label>恢复理由<textarea v-model="reason" placeholder="至少 2 个字符，将写入审计" /></label><button class="button button-primary" :disabled="!canResume || !verified || reason.trim().length < 2 || resuming" @click="resume">{{ resuming ? '正在提交…' : '交还控制权并继续' }}</button></fieldset>
          <p v-if="detail.state === 'PAUSED_WAITING_USER' && !canResume">当前登录身份没有设备控制权限，无法恢复任务。</p>
        </template>
      </div>
    </section></div>
  </section>
</template>

<style scoped>
.task-queue, .queue-filters label, .queue-detail .modal-header h3, .queue-detail .modal-body, fieldset { min-width: 0; overflow-wrap: anywhere; }
.queue-filters label { max-width: 100%; }
.queue-detail .modal-header h3 { flex: 1; }
.queue-detail .modal-header .button { flex-shrink: 0; }
.queue-note { color: var(--text-secondary, #64748b); margin: 12px 0; }
.queue-filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin: 16px 0; }
.queue-filters label, fieldset label { display: grid; gap: 6px; }
.queue-filters input, .queue-filters select, textarea { padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; max-width: min(320px, 100%); min-width: 0; box-sizing: border-box; }
.queue-table { overflow: auto; } table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; vertical-align: top; } small { display: block; color: #64748b; overflow-wrap: anywhere; }
.queue-pagination { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 16px 0; }
.queue-detail { max-width: 900px; width: 95vw; max-height: 90vh; overflow: auto; } pre { white-space: pre-wrap; overflow-wrap: anywhere; } fieldset { display: grid; gap: 12px; margin-top: 16px; } fieldset label:has(input) { display: flex; align-items: center; }
</style>
