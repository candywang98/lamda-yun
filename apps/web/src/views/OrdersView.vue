<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import { useSessionStore } from '@/stores/session'
import { ORDER_DELIVERY_PROTOCOL, deliveryLabel, deliveryProgress, deliveryReason } from '@/features/orders/delivery'
import {
  ORDER_DIRECTION_OPTIONS,
  fetchOrder,
  fetchXianyuOrderRun,
  formatOrderAmount,
  formatOrderTime,
  listOrders,
  orderDirectionLabel,
  OrdersApiError,
  OrdersProtocolError,
  startXianyuOrderCollect,
  type OrderDetail,
  type OrderDirection,
  type OrderRow,
  type OrderRunIdentity,
  type XianyuOrderCollectInput,
  type XianyuOrderCollectResult,
  type XianyuOrderRunView,
} from '@/api/orders'

/** 契约 §4：limit 1..100 默认 20；本页按「加载更多」翻页。 */
const PAGE_SIZE = 20
const session = useSessionStore()
let disposed = false
let listRequest = 0
let detailRequest = 0

interface DeviceOption { id: string; name: string }

const deviceOptions = ref<DeviceOption[]>([])
const deviceFilter = ref('')
const directionFilter = ref<'' | 'SOLD' | 'BOUGHT'>('')
const statusFilter = ref('')

const orders = ref<OrderRow[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const loadedFilterKey = ref<string | null>(null)
const currentFilterKey = computed(() => JSON.stringify([deviceFilter.value, directionFilter.value, statusFilter.value.trim()]))

/** 列表请求参数（设备/方向/状态过滤 + 翻页偏移）。 */
function listQuery(offset: number) {
  return {
    deviceId: deviceFilter.value || undefined,
    direction: directionFilter.value || undefined,
    statusText: statusFilter.value.trim() || undefined,
    limit: PAGE_SIZE,
    offset,
  }
}

async function loadPage(offset: number, append: boolean) {
  const filterKey = currentFilterKey.value
  if (append && loadedFilterKey.value !== filterKey) {
    await loadPage(0, false)
    return
  }
  if (!append && loadedFilterKey.value !== filterKey) {
    orders.value = []
    total.value = 0
    expandedId.value = null
    ++detailRequest
    loadedFilterKey.value = null
  }
  const request = ++listRequest
  loading.value = true
  loadError.value = ''
  try {
    const result = await listOrders(listQuery(offset))
    if (disposed || request !== listRequest) return
    orders.value = append ? [...orders.value, ...result.items] : result.items
    total.value = result.total
    loadedFilterKey.value = filterKey
    if (!append) expandedId.value = null
  } catch (error) {
    if (disposed || request !== listRequest) return
    // fail-closed：后端不可达或报错时如实展示，不渲染任何占位假数据。
    loadError.value = error instanceof OrdersApiError ? error.message : '订单列表加载失败'
  } finally {
    if (!disposed && request === listRequest) loading.value = false
  }
}

async function refresh() {
  await loadPage(0, false)
}

/** 过滤条件变化后从头加载。 */
async function reload() {
  await loadPage(0, false)
}

async function loadMore() {
  await loadPage(orders.value.length, true)
}

/** List refresh is independent of the collection/delivery query. */
async function manualRefresh() {
  await loadPage(0, false)
}

const hasMore = computed(() => loadedFilterKey.value === currentFilterKey.value && !loadError.value && orders.value.length < total.value)

/** 空态只在成功加载且确认无数据时出现；有错误时绝不显示「暂无订单」。 */
const showEmpty = computed(() => !loading.value && !loadError.value && orders.value.length === 0)

const emptyText = computed(() => {
  if (!controlApiConfigured) return '未配置 Control API，无法读取订单。'
  return '暂无订单。手机采集任务上报后会出现在这里。'
})

/* ---------------- 设备下拉（复用 im 的 loadDeviceOptions 模式） ---------------- */

async function loadDeviceOptions() {
  if (!controlApiConfigured) {
    deviceOptions.value = []
    return
  }
  try {
    const rows = await createControlApiClient().devices()
    if (disposed) return
    deviceOptions.value = rows.map((row) => {
      const mapped = mapControlDevice(row)
      return { id: mapped.id, name: mapped.name }
    })
  } catch {
    if (!disposed) deviceOptions.value = []
  }
}

/* ---------------- 详情展开（raw 仅在详情端点返回，展开时按需拉取） ---------------- */

const expandedId = ref<string | null>(null)
const detail = ref<OrderDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

async function toggleExpanded(id: string) {
  const request = ++detailRequest
  if (expandedId.value === id) {
    expandedId.value = null
    return
  }
  expandedId.value = id
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const fetched = await fetchOrder(id)
    // 展开行已切换时丢弃过期响应
    if (disposed || request !== detailRequest || expandedId.value !== id) return
    detail.value = fetched
  } catch (error) {
    if (disposed || request !== detailRequest || expandedId.value !== id) return
    // fail-closed：详情拉取失败如实展示，不渲染占位 raw
    detailError.value = error instanceof OrdersApiError ? error.message : '订单详情加载失败'
  } finally {
    if (!disposed && request === detailRequest && expandedId.value === id) detailLoading.value = false
  }
}

function rawJson(row: OrderDetail): string {
  return JSON.stringify(row.raw ?? {}, null, 2)
}

/* ---------------- order-delivery/1 collection and independent delivery reads ---------------- */

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
let refreshedRunId: string | undefined

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
  if (run.delivery?.state === 'SYNCED' && refreshedRunId !== run.runId) {
    refreshedRunId = run.runId
    void refresh()
  }
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
  const deviceId = deviceFilter.value
  if (!deviceOptions.value.some((device) => device.id === deviceId)) {
    collectError.value = '请先在上方「设备」下拉选择具体设备后再发起采集。'
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

onMounted(() => {
  void refresh()
  void loadDeviceOptions()
})

onUnmounted(() => {
  disposed = true
  ++listRequest
  ++detailRequest
  clearRunPoll()
})
</script>

<template>
  <section class="yy-panel">
    <header class="yy-page-head">
      <div>
        <h1>订单同步</h1>
        <p class="yy-sub">闲鱼订单只读同步（我卖出的 / 我买到的），数据来自手机页面采集快照。</p>
      </div>
      <div class="yy-actions">
        <label class="yy-field">
          <span>设备</span>
          <select v-model="deviceFilter" @change="reload">
            <option value="">全部</option>
            <option v-for="option in deviceOptions" :key="option.id" :value="option.id">
              {{ option.name }}（{{ option.id.slice(0, 8) }}）
            </option>
          </select>
        </label>
        <label class="yy-field">
          <span>方向</span>
          <select v-model="directionFilter" @change="reload">
            <option value="">全部</option>
            <option v-for="option in ORDER_DIRECTION_OPTIONS" :key="option.key" :value="option.key">
              {{ option.label }}
            </option>
          </select>
        </label>
        <label class="yy-field">
          <span>状态</span>
          <input
            v-model="statusFilter"
            type="text"
            maxlength="64"
            placeholder="如：待发货"
            @change="reload"
          />
        </label>
        <button class="yy-btn" type="button" :disabled="loading" @click="manualRefresh">
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </div>
    </header>

    <p v-if="loadError" class="yy-error">{{ loadError }}</p>

    <div class="orders-collect">
      <label class="yy-field">
        <span>采集方向</span>
        <select v-model="collectDirection" :disabled="!canCollect || collectionLocked">
          <option v-for="option in ORDER_DIRECTION_OPTIONS" :key="option.key" :value="option.key">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="yy-field">
        <span>屏数</span>
        <select v-model="collectScreens" :disabled="!canCollect || collectionLocked">
          <option :value="1">1 屏</option>
          <option :value="2">2 屏</option>
          <option :value="3">3 屏</option>
        </select>
      </label>
      <button
        class="yy-btn"
        type="button"
        :disabled="!deviceFilter || !canCollect || collectionLocked"
        @click="startCollect"
      >
        {{ collectBusy ? '提交中…' : attempt?.identity ? '新建采集' : '开始采集' }}
      </button>
      <button v-if="attempt && !attempt.identity" class="yy-btn" type="button" :disabled="collectBusy || !canCollect" @click="submitAttempt">
        <RefreshCw :size="14" aria-hidden="true" />重试提交
      </button>
      <button v-if="attempt?.identity" class="yy-btn" type="button" :disabled="collectBusy" @click="manualRunRefresh">
        <RefreshCw :size="14" aria-hidden="true" />刷新同步状态
      </button>
      <span v-if="!deviceFilter" class="yy-sub">请先在上方「设备」下拉选择具体设备（「全部」不能发起采集）。</span>
      <span v-if="collectNote" class="yy-sub" role="status">{{ collectNote }}</span>
    </div>

    <p v-if="!canCollect" class="yy-sub">当前身份不可创建采集任务。</p>
    <p v-if="collectError" class="yy-error" role="alert">{{ collectError }}</p>

    <div v-if="attempt" class="orders-delivery" :aria-busy="statusReading">
      <p class="yy-sub">设备 {{ attempt.input.deviceId }} · {{ orderDirectionLabel(attempt.input.direction) }}</p>
      <p v-if="attempt.identity" class="orders-identity">run {{ attempt.identity.runId }} · task {{ attempt.identity.taskIds.join('、') }}</p>
      <p v-if="collectRun" role="status">{{ collectionLabel }}</p>
      <p role="status" :data-delivery-state="delivery?.state ?? 'UNKNOWN'">{{ deliveryLabel(delivery) }}</p>
      <p v-if="delivery && delivery.state !== 'LEGACY_UNVERIFIED'" class="yy-sub">{{ deliveryProgress(delivery) }}</p>
      <p v-if="delivery?.stopReason" :class="delivery.state === 'BLOCKED' ? 'yy-error' : 'yy-sub'">{{ deliveryReason(delivery.stopReason) }}</p>
      <span v-if="polling" class="yy-sub">自动查询中</span>
    </div>
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

    <table class="orders-table">
      <thead>
        <tr>
          <th>订单号</th>
          <th>商品</th>
          <th>对方</th>
          <th>金额</th>
          <th>状态</th>
          <th>时间</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in orders" :key="row.id">
          <tr
            class="orders-row"
            :class="{ expanded: expandedId === row.id }"
            @click="toggleExpanded(row.id)"
          >
            <td class="orders-key">{{ row.orderKey }}</td>
            <td class="orders-title">{{ row.itemTitle ?? '—' }}</td>
            <td>{{ row.buyerName ?? '—' }}</td>
            <td class="orders-amount">{{ formatOrderAmount(row.amountCents) }}</td>
            <td>
              <span class="orders-status">{{ row.statusText ?? '—' }}</span>
              <span class="orders-direction" :data-direction="row.direction">{{ orderDirectionLabel(row.direction) }}</span>
            </td>
            <td>{{ formatOrderTime(row.occurredAt) }}</td>
          </tr>
          <tr v-if="expandedId === row.id" class="orders-detail">
            <td colspan="6">
              <p v-if="detailLoading" class="yy-sub">详情加载中…</p>
              <p v-else-if="detailError" class="yy-error">{{ detailError }}</p>
              <template v-else-if="detail">
                <dl class="orders-fields">
                  <div><dt>订单号</dt><dd>{{ detail.orderKey }}</dd></div>
                  <div><dt>平台 / 方向</dt><dd>{{ detail.platform }} / {{ orderDirectionLabel(detail.direction) }}</dd></div>
                  <div><dt>商品标题</dt><dd>{{ detail.itemTitle ?? '—' }}</dd></div>
                  <div><dt>对方昵称</dt><dd>{{ detail.buyerName ?? '—' }}</dd></div>
                  <div><dt>金额（分）</dt><dd>{{ detail.amountCents ?? '—' }}（{{ formatOrderAmount(detail.amountCents) }}）</dd></div>
                  <div><dt>页面状态</dt><dd>{{ detail.statusText ?? '—' }}</dd></div>
                  <div><dt>页面时间</dt><dd>{{ detail.occurredAt ?? '—' }}</dd></div>
                  <div><dt>上报设备</dt><dd>{{ detail.deviceId }}</dd></div>
                  <div><dt>入库 / 更新</dt><dd>{{ detail.createdAt }} / {{ detail.updatedAt }}</dd></div>
                </dl>
                <p class="yy-sub orders-raw-label">行原文快照（raw，最小化保存）：</p>
                <pre class="orders-raw">{{ rawJson(detail) }}</pre>
              </template>
            </td>
          </tr>
        </template>
        <tr v-if="showEmpty">
          <td colspan="6" class="orders-empty">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer v-if="orders.length > 0 || total > 0" class="orders-foot">
      <span class="yy-sub">已加载 {{ orders.length }} / 共 {{ total }} 条</span>
      <button
        v-if="hasMore"
        class="yy-btn"
        type="button"
        :disabled="loading"
        @click="loadMore"
      >
        加载更多
      </button>
    </footer>
  </section>
</template>

<style scoped>
.orders-collect {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
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
.orders-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
}
.orders-table th,
.orders-table td {
  border: 1px solid var(--yy-line, #d8dee6);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}
.orders-table th {
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
}
.orders-row {
  cursor: pointer;
}
.orders-row:hover {
  background: #f8fafc;
}
.orders-row.expanded {
  background: #f0fbf9;
}
.orders-key {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
.orders-title {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.orders-amount {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.orders-status {
  margin-right: 6px;
}
.orders-direction {
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #334155;
  font-size: 11px;
  font-weight: 500;
}
.orders-direction[data-direction='SOLD'] { border-color: #bbf7d0; background: #f0fdf4; color: #166534; }
.orders-direction[data-direction='BOUGHT'] { border-color: #bfdbfe; background: #eff6ff; color: #1e40af; }
.orders-detail td {
  background: #f8fafc;
}
.orders-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px 18px;
  margin: 0 0 10px;
}
.orders-fields div {
  display: flex;
  gap: 8px;
  font-size: 12.5px;
}
.orders-fields dt {
  color: #64748b;
  flex-shrink: 0;
}
.orders-fields dd {
  margin: 0;
  word-break: break-all;
}
.orders-raw-label {
  margin: 4px 0;
}
.orders-raw {
  max-height: 260px;
  overflow: auto;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
  margin: 0;
}
.orders-empty {
  color: #64748b;
  text-align: center;
  padding: 26px 0;
}
.orders-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}
</style>
