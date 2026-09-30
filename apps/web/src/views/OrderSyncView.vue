<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { RefreshCw } from 'lucide-vue-next'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import { useSessionStore } from '@/stores/session'
import { ORDER_DELIVERY_PROTOCOL, deliveryLabel, deliveryProgress, deliveryReason } from '@/features/orders/delivery'
import {
  ORDER_DIRECTION_OPTIONS,
  fetchXianyuOrderRun,
  orderDirectionLabel,
  OrdersApiError,
  OrdersProtocolError,
  startXianyuOrderCollect,
  type OrderDirection,
  type OrderRunIdentity,
  type XianyuOrderCollectInput,
  type XianyuOrderCollectResult,
  type XianyuOrderRunView,
} from '@/api/orders'

const session = useSessionStore()
let disposed = false
interface DeviceOption { id: string; name: string }
const deviceOptions = ref<DeviceOption[]>([])
const selectedDevice = ref('')
const deviceLoading = ref(false)
const deviceError = ref('')

async function loadDeviceOptions() {
  if (!controlApiConfigured) {
    deviceOptions.value = []
    deviceError.value = '未配置 Control API，无法加载设备。'
    return
  }
  if (deviceLoading.value) return
  deviceLoading.value = true
  deviceError.value = ''
  try {
    const rows = await createControlApiClient().devices()
    if (disposed) return
    deviceOptions.value = rows.map((row) => {
      const mapped = mapControlDevice(row)
      return { id: mapped.id, name: mapped.name }
    })
  } catch {
    if (!disposed) {
      deviceOptions.value = []
      deviceError.value = '设备加载失败，请重试。'
    }
  } finally {
    if (!disposed) deviceLoading.value = false
  }
}

/** 契约 slice2 §2：max_rows 为每屏上限（1..10），采集取上限读满一屏。 */
const COLLECT_MAX_ROWS_PER_SCREEN = 10
const RUN_POLL_INTERVAL_MS = 2000
const RUN_POLL_MAX_INTERVAL_MS = 10000
const RUN_POLL_TIMEOUT_MS = 60000

const collectDirection = ref<OrderDirection>('SOLD')
const collectScreens = ref<1 | 2 | 3>(1)
const collectBusy = ref(false)
const collectNote = ref('')
const collectError = ref('')
const collectRun = ref<XianyuOrderRunView | XianyuOrderCollectResult | null>(null)
const statusReading = ref(false)
const polling = ref(false)
const attempt = ref<{
  input: XianyuOrderCollectInput
  key: string
  ambiguous: boolean
  identity: OrderRunIdentity | null
} | null>(null)
const canCollect = computed(() => controlApiConfigured && session.can('device.control'))
const delivery = computed(() => collectRun.value?.delivery)
const settled = computed(() => delivery.value?.state === 'SYNCED' || delivery.value?.state === 'BLOCKED')
const collectionLocked = computed(() => collectBusy.value || statusReading.value || (!!attempt.value && !settled.value))
const collectionLabel = computed(() => {
  const tasks = collectRun.value?.tasks ?? []
  if (!tasks.length) return '采集状态未确认'
  if (tasks.every((task) => task.state === 'SUCCEEDED')) return '采集步骤完成'
  if (tasks.some((task) => ['FAILED', 'CANCELLED', 'EXPIRED', 'RECONCILING'].includes(task.state ?? ''))) return '采集未全部成功'
  return '采集尚未完成'
})

let runPollTimer: number | undefined
let pollDeadlineTimer: number | undefined
let runRequest = 0
let runAbort: AbortController | undefined

function clearRunPoll() {
  if (runPollTimer !== undefined) window.clearTimeout(runPollTimer)
  if (pollDeadlineTimer !== undefined) window.clearTimeout(pollDeadlineTimer)
  runPollTimer = undefined
  pollDeadlineTimer = undefined
  ++runRequest
  runAbort?.abort()
  runAbort = undefined
  polling.value = false
  statusReading.value = false
}

function showRun(run: XianyuOrderRunView | XianyuOrderCollectResult) {
  collectRun.value = run
}

function pausePolling() {
  clearRunPoll()
  collectNote.value = '自动查询已暂停，同步状态以上次查询为准。'
}

async function pollRun(request: number, reads: number) {
  const current = attempt.value
  if (disposed || request !== runRequest || !current?.identity) return
  statusReading.value = true
  runAbort = new AbortController()
  try {
    const run = await fetchXianyuOrderRun(current.identity.runId, {
      expected: current.identity,
      maxScreens: current.input.screens ?? 1,
      durable: true,
      signal: runAbort.signal,
    })
    if (disposed || request !== runRequest) return
    collectError.value = ''
    showRun(run)
    if (run.delivery?.state !== 'PENDING') {
      clearRunPoll()
      collectNote.value = ''
      return
    }
  } catch (error) {
    if (disposed || request !== runRequest) return
    collectError.value = error instanceof OrdersApiError ? error.message : '采集运行状态读取失败'
    if (error instanceof OrdersProtocolError || (error instanceof OrdersApiError &&
        error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status))) {
      pausePolling()
      return
    }
  } finally {
    if (!disposed && request === runRequest) statusReading.value = false
  }
  if (disposed || request !== runRequest) return
  const delay = Math.min(RUN_POLL_INTERVAL_MS * 2 ** (reads + 1), RUN_POLL_MAX_INTERVAL_MS)
  runPollTimer = window.setTimeout(() => void pollRun(request, reads + 1), delay)
}

function beginPolling(immediate = false) {
  if (disposed || !attempt.value?.identity) return
  clearRunPoll()
  const request = runRequest
  polling.value = true
  collectError.value = ''
  collectNote.value = '正在查询同步状态…'
  // A separate deadline also bounds a stalled GET, not only scheduled retries.
  pollDeadlineTimer = window.setTimeout(pausePolling, RUN_POLL_TIMEOUT_MS)
  if (immediate) void pollRun(request, 0)
  else runPollTimer = window.setTimeout(() => void pollRun(request, 0), RUN_POLL_INTERVAL_MS)
}

function manualRunRefresh() {
  if (disposed || collectBusy.value || !attempt.value?.identity) return
  beginPolling(true)
}

async function submitAttempt() {
  const current = attempt.value
  if (disposed || collectBusy.value || !canCollect.value || !current || current.identity) return
  collectBusy.value = true
  collectError.value = ''
  collectNote.value = '采集任务提交中…'
  try {
    const result = await startXianyuOrderCollect(current.input, current.key)
    if (disposed || attempt.value !== current) return
    current.identity = {
      runId: result.runId, deviceId: result.deviceId, direction: result.direction,
      maxRows: result.maxRows, taskIds: [...result.taskIds],
    }
    showRun(result)
    collectNote.value = ''
    if (result.delivery?.state === 'PENDING') beginPolling()
  } catch (error) {
    if (disposed || attempt.value !== current) return
    collectNote.value = ''
    collectError.value = error instanceof OrdersApiError ? error.message : '采集提交结果未确认'
    if (error instanceof OrdersProtocolError && error.acceptedIdentity) {
      current.identity = error.acceptedIdentity
    } else if (!current.ambiguous && error instanceof OrdersApiError && !(error instanceof OrdersProtocolError) &&
        error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)) {
      attempt.value = null
    } else {
      current.ambiguous = true
    }
  } finally {
    if (!disposed) collectBusy.value = false
  }
}

async function startCollect() {
  if (disposed || !canCollect.value || collectionLocked.value) return
  const deviceId = selectedDevice.value
  if (!deviceOptions.value.some((device) => device.id === deviceId)) {
    collectError.value = '请选择执行同步的设备。'
    return
  }
  let key: string
  try {
    key = crypto.randomUUID()
  } catch {
    collectError.value = '无法生成采集请求标识，未提交任务'
    return
  }
  clearRunPoll()
  collectRun.value = null
  attempt.value = {
    input: {
      deviceId, direction: collectDirection.value, maxRows: COLLECT_MAX_ROWS_PER_SCREEN,
      ...(collectScreens.value === 1 ? {} : { screens: collectScreens.value }),
      orderDeliveryProtocol: ORDER_DELIVERY_PROTOCOL,
    },
    key, ambiguous: false, identity: null,
  }
  await submitAttempt()
}

onMounted(() => { void loadDeviceOptions() })
onUnmounted(() => { disposed = true; clearRunPoll() })
</script>

<template>
  <section class="yy-panel">
    <header class="yy-page-head">
      <div><h1>同步闲鱼订单</h1><p class="yy-sub">选择设备和订单方向，创建手机页面采集任务。确认入库后，可在商品管理的「已同步订单」中查看结果。</p></div>
      <RouterLink to="/operations/product-management/product-management-01?tab=orders">前往商品管理</RouterLink>
    </header>
    <p v-if="deviceError" class="yy-error" role="alert">{{ deviceError }} <button v-if="controlApiConfigured" class="yy-btn" type="button" :disabled="deviceLoading" @click="loadDeviceOptions">重新加载设备</button></p>
    <p v-else-if="deviceLoading" class="yy-sub" role="status">正在加载设备…</p>
    <p v-else-if="deviceOptions.length === 0" class="yy-sub">暂无可选设备，请先在设备列表中接入设备。</p>
    <form class="orders-collect" @submit.prevent="startCollect">
      <label class="yy-field">
        <span>设备</span>
        <select v-model="selectedDevice" :disabled="!canCollect || collectionLocked">
          <option value="">请选择设备</option>
          <option v-for="option in deviceOptions" :key="option.id" :value="option.id">{{ option.name }}（{{ option.id.slice(0, 8) }}）</option>
        </select>
      </label>
      <label class="yy-field">
        <span>订单方向</span>
        <select v-model="collectDirection" :disabled="!canCollect || collectionLocked">
          <option v-for="option in ORDER_DIRECTION_OPTIONS" :key="option.key" :value="option.key">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="yy-field">
        <span>采集屏数</span>
        <select v-model="collectScreens" :disabled="!canCollect || collectionLocked">
          <option :value="1">1 屏</option>
          <option :value="2">2 屏</option>
          <option :value="3">3 屏</option>
        </select>
      </label>
      <button
        class="yy-btn"
        type="submit"
        :disabled="!selectedDevice || !canCollect || collectionLocked"
      >
        {{ collectBusy ? '提交中…' : attempt?.identity ? '创建新的同步任务' : '创建同步任务' }}
      </button>
      <button v-if="attempt && !attempt.identity" class="yy-btn" type="button" :disabled="collectBusy || !canCollect" @click="submitAttempt">
        <RefreshCw :size="14" aria-hidden="true" />重试提交
      </button>
      <button v-if="attempt?.identity" class="yy-btn" type="button" :disabled="collectBusy" @click="manualRunRefresh">
        <RefreshCw :size="14" aria-hidden="true" />刷新同步状态
      </button>
      <span v-if="!selectedDevice" class="yy-sub">请选择执行同步的设备。</span>
      <span v-if="collectNote" class="yy-sub" role="status">{{ collectNote }}</span>
    </form>

    <p v-if="!canCollect" class="yy-sub">当前身份不可创建采集任务。</p>
    <p v-if="collectError" class="yy-error" role="alert">{{ collectError }}</p>

    <div v-if="attempt" class="orders-delivery" :aria-busy="statusReading">
      <p class="yy-sub">设备 {{ attempt.input.deviceId }} · {{ orderDirectionLabel(attempt.input.direction) }}</p>
      <p v-if="collectRun" role="status">{{ collectionLabel }}</p>
      <p role="status" :data-delivery-state="delivery?.state ?? 'UNKNOWN'">{{ deliveryLabel(delivery) }}</p>
      <p v-if="delivery && delivery.state !== 'LEGACY_UNVERIFIED'" class="yy-sub">{{ deliveryProgress(delivery) }}</p>
      <p v-if="delivery?.stopReason" :class="delivery.state === 'BLOCKED' ? 'yy-error' : 'yy-sub'">{{ deliveryReason(delivery.stopReason) }}</p>
      <span v-if="polling" class="yy-sub">自动查询中</span>
    </div>
    <p v-if="delivery?.state === 'SYNCED'"><RouterLink class="yy-btn" to="/operations/product-management/product-management-01?tab=orders">查看已同步订单</RouterLink></p>
    <details v-if="attempt?.identity" class="orders-diagnostics">
      <summary>任务诊断信息</summary>
      <p class="orders-identity">run {{ attempt.identity.runId }} · task {{ attempt.identity.taskIds.join('、') }}</p>
      <div v-if="collectRun" class="orders-collect-run">
        <span class="yy-sub">采集任务状态：</span>
        <span
          v-for="task in collectRun.tasks"
          :key="task.taskId"
          class="orders-task-state"
          :data-state="task.state ?? 'UNKNOWN'"
        >
          {{ task.state ?? 'UNKNOWN' }}<template v-if="task.errorCode">（{{ task.errorCode }}）</template>
        </span>
      </div>

    </details>
  </section>
</template>

<style scoped>
.yy-page-head { flex-wrap: wrap; align-items: flex-start; }
.yy-page-head > div { min-width: 0; max-width: 100%; }
.yy-field { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; }
.yy-field > span { flex-shrink: 0; }
.yy-field select, .yy-field input { min-width: 0; max-width: 100%; }
.orders-collect {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 0;
  margin-bottom: 12px;
}
.orders-collect .yy-btn { display: inline-flex; align-items: center; gap: 6px; }
.orders-delivery { margin-bottom: 12px; overflow-wrap: anywhere; }
.orders-delivery p { margin: 4px 0; }
.orders-identity { font-family: monospace; font-size: 12px; }
[data-delivery-state='SYNCED'] { color: #166534; }
[data-delivery-state='BLOCKED'] { color: #991b1b; }
.orders-collect-run {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: -4px 0 12px;
}
.orders-task-state {
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.orders-task-state[data-state='SUCCEEDED'] { border-color: #bbf7d0; background: #f0fdf4; color: #166534; }
.orders-task-state[data-state='FAILED'] { border-color: #fecaca; background: #fef2f2; color: #991b1b; }

.orders-collect .yy-field { display: grid; grid-template-columns: 80px minmax(180px, 320px); }
.orders-diagnostics { margin-top: 16px; }
</style>
