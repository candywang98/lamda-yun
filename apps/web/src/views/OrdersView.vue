<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import {
  ORDER_DIRECTION_OPTIONS,
  fetchOrder,
  fetchXianyuOrderRun,
  formatOrderAmount,
  formatOrderTime,
  isXianyuOrderRunTerminal,
  listOrders,
  orderDirectionLabel,
  OrdersApiError,
  startXianyuOrderCollect,
  type OrderDetail,
  type OrderDirection,
  type OrderRow,
  type XianyuOrderRunView,
} from '@/api/orders'

/** 契约 §4：limit 1..100 默认 20；本页按「加载更多」翻页。 */
const PAGE_SIZE = 20

interface DeviceOption { id: string; name: string }

const deviceOptions = ref<DeviceOption[]>([])
const deviceFilter = ref('')
const directionFilter = ref<'' | 'SOLD' | 'BOUGHT'>('')
const statusFilter = ref('')

const orders = ref<OrderRow[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')

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
  loading.value = true
  loadError.value = ''
  try {
    const result = await listOrders(listQuery(offset))
    orders.value = append ? [...orders.value, ...result.items] : result.items
    total.value = result.total
    if (!append) expandedId.value = null
  } catch (error) {
    // fail-closed：后端不可达或报错时如实展示，不渲染任何占位假数据。
    loadError.value = error instanceof OrdersApiError ? error.message : '订单列表加载失败'
  } finally {
    loading.value = false
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

/** 手动刷新保留已展开行；加载失败时旧数据保留但错误置顶提示。 */
async function manualRefresh() {
  await loadPage(0, false)
}

const hasMore = computed(() => orders.value.length < total.value)

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
    deviceOptions.value = rows.map((row) => {
      const mapped = mapControlDevice(row)
      return { id: mapped.id, name: mapped.name }
    })
  } catch {
    deviceOptions.value = []
  }
}

/* ---------------- 详情展开（raw 仅在详情端点返回，展开时按需拉取） ---------------- */

const expandedId = ref<string | null>(null)
const detail = ref<OrderDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

async function toggleExpanded(id: string) {
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
    if (expandedId.value !== id) return
    detail.value = fetched
  } catch (error) {
    if (expandedId.value !== id) return
    // fail-closed：详情拉取失败如实展示，不渲染占位 raw
    detailError.value = error instanceof OrdersApiError ? error.message : '订单详情加载失败'
  } finally {
    if (expandedId.value === id) detailLoading.value = false
  }
}

function rawJson(row: OrderDetail): string {
  return JSON.stringify(row.raw ?? {}, null, 2)
}

/* ---------------- 采集入口（order-sync slice2 §4：定位器已真机验证，启用） ---------------- */

/** 契约 slice2 §2：max_rows 为每屏上限（1..10），采集取上限读满一屏。 */
const COLLECT_MAX_ROWS_PER_SCREEN = 10
const RUN_POLL_INTERVAL_MS = 2000
const RUN_POLL_TIMEOUT_MS = 60000

const collectDirection = ref<OrderDirection>('SOLD')
const collectScreens = ref<1 | 2 | 3>(1)
const collectBusy = ref(false)
const collectNote = ref('')
const collectError = ref('')
const collectRun = ref<XianyuOrderRunView | null>(null)

let runPollTimer: number | undefined

function clearRunPoll() {
  if (runPollTimer !== undefined) window.clearTimeout(runPollTimer)
  runPollTimer = undefined
}

/** 终态收口：全部任务 SUCCEEDED → 刷新列表；否则逐任务如实展示 state/errorCode（fail-closed，不吞错）。 */
function finishCollect(run: XianyuOrderRunView) {
  collectBusy.value = false
  collectRun.value = run
  const tasks = run.tasks
  if (tasks.length > 0 && tasks.every((task) => task.state === 'SUCCEEDED')) {
    collectNote.value = `采集完成（${tasks.length} 个任务全部成功），已刷新订单列表。`
    void refresh()
    return
  }
  const problems = tasks
    .filter((task) => task.state !== 'SUCCEEDED')
    .map((task) => `${task.state ?? 'UNKNOWN'}${task.errorCode ? `（${task.errorCode}）` : ''}`)
    .join('；')
  collectError.value = `采集未全部成功：${problems || '未返回任务状态'}`
}

async function pollRun(runId: string, startedAt: number) {
  let run: XianyuOrderRunView
  try {
    run = await fetchXianyuOrderRun(runId)
  } catch (error) {
    // fail-closed：轮询读状态失败如实展示并停止，不吞错也不假装成功。
    collectBusy.value = false
    collectError.value = error instanceof OrdersApiError ? error.message : '采集运行状态读取失败'
    return
  }
  collectRun.value = run
  if (isXianyuOrderRunTerminal(run)) {
    finishCollect(run)
    return
  }
  if (Date.now() - startedAt >= RUN_POLL_TIMEOUT_MS) {
    // 超时不算失败也不算成功：任务可能仍在真机执行，如实提示后停止本页轮询。
    collectBusy.value = false
    collectNote.value = `采集仍在运行（已轮询超过 ${RUN_POLL_TIMEOUT_MS / 1000} 秒），结果请稍后手动刷新确认。`
    return
  }
  runPollTimer = window.setTimeout(() => void pollRun(runId, startedAt), RUN_POLL_INTERVAL_MS)
}

async function startCollect() {
  // 设备复用上方「设备」过滤下拉：未选具体设备（=全部）时按钮已禁用，此处兜底校验。
  const deviceId = deviceFilter.value
  if (!deviceId) {
    collectError.value = '请先在上方「设备」下拉选择具体设备后再发起采集。'
    return
  }
  clearRunPoll()
  collectBusy.value = true
  collectError.value = ''
  collectNote.value = '采集任务提交中…'
  collectRun.value = null
  try {
    const result = await startXianyuOrderCollect(
      {
        deviceId,
        direction: collectDirection.value,
        maxRows: COLLECT_MAX_ROWS_PER_SCREEN,
        // 契约 slice2 §4：屏数为 1 时不发 screens 字段（后端默认 1，走 v1 入参兼容）。
        ...(collectScreens.value === 1 ? {} : { screens: collectScreens.value }),
      },
      crypto.randomUUID(),
    )
    collectNote.value = `采集已提交（run ${result.runId.slice(0, 8)}…），每 ${RUN_POLL_INTERVAL_MS / 1000} 秒轮询运行状态…`
    const startedAt = Date.now()
    runPollTimer = window.setTimeout(() => void pollRun(result.runId, startedAt), RUN_POLL_INTERVAL_MS)
  } catch (error) {
    collectBusy.value = false
    collectNote.value = ''
    collectError.value = error instanceof OrdersApiError ? error.message : '采集任务提交失败'
  }
}

onMounted(() => {
  void refresh()
  void loadDeviceOptions()
})

onUnmounted(clearRunPoll)
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
        <select v-model="collectDirection">
          <option v-for="option in ORDER_DIRECTION_OPTIONS" :key="option.key" :value="option.key">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="yy-field">
        <span>屏数</span>
        <select v-model="collectScreens">
          <option :value="1">1 屏</option>
          <option :value="2">2 屏</option>
          <option :value="3">3 屏</option>
        </select>
      </label>
      <button
        class="yy-btn"
        type="button"
        :disabled="!deviceFilter || collectBusy"
        @click="startCollect"
      >
        {{ collectBusy ? '采集运行中…' : '开始采集' }}
      </button>
      <span v-if="!deviceFilter" class="yy-sub">请先在上方「设备」下拉选择具体设备（「全部」不能发起采集）。</span>
      <span v-else-if="collectNote" class="yy-sub">{{ collectNote }}</span>
    </div>

    <p v-if="collectError" class="yy-error">{{ collectError }}</p>

    <div v-if="collectRun" class="orders-collect-run">
      <span class="yy-sub">run {{ collectRun.runId.slice(0, 8) }}… 任务状态：</span>
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
