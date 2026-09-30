<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import {
  ORDER_DIRECTION_OPTIONS,
  fetchOrder,
  formatOrderAmount,
  formatOrderTime,
  listOrders,
  orderDirectionLabel,
  OrdersApiError,
  type OrderDetail,
  type OrderRow,
} from '@/api/orders'

/** 契约 §4：limit 1..100 默认 20；本页按「加载更多」翻页。 */
const PAGE_SIZE = 20
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

onMounted(() => { void refresh(); void loadDeviceOptions() })
onUnmounted(() => { disposed = true; ++listRequest; ++detailRequest })
</script>

<template>
  <section class="panel orders-panel">
    <header class="yy-page-head">
      <div>
        <h1>已同步订单</h1>
        <p class="yy-sub">查看已入库的闲鱼订单快照，支持筛选和详情查询。</p>
      </div>
      <div class="yy-actions">
        <RouterLink class="button" to="/operations/orders/orders-01">创建同步任务</RouterLink>
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
        <button class="button" type="button" :disabled="loading" @click="manualRefresh">
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </div>
    </header>

    <p v-if="loadError" class="yy-error">{{ loadError }}</p>

    <div class="table-wrap" role="region" aria-label="订单列表" tabindex="0">
      <table class="orders-table">
        <thead>
          <tr>
            <th>订单标识</th>
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
                    <div><dt>订单标识</dt><dd>{{ detail.orderKey }}</dd></div>
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
    </div>

    <footer v-if="orders.length > 0 || total > 0" class="orders-foot">
      <span class="yy-sub">已加载 {{ orders.length }} / 共 {{ total }} 条</span>
      <button
        v-if="hasMore"
        class="button"
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
.orders-panel { min-width: 0; padding: 18px; }
.yy-page-head { flex-wrap: wrap; align-items: flex-start; gap: 16px; }
.yy-page-head > div { min-width: 0; max-width: 100%; }
.yy-page-head h1 { margin: 0; color: var(--ink); font-size: 18px; }
.yy-sub { margin: 6px 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.yy-error { color: var(--bad); font-size: 13px; overflow-wrap: anywhere; }
.button { text-decoration: none; }
.yy-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.yy-field { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; color: var(--muted); font-size: 13px; }
.yy-field > span { flex-shrink: 0; }
.yy-field select, .yy-field input { width: 160px; min-width: 0; max-width: 100%; min-height: 36px; padding: 7px 9px; color: var(--ink); background: var(--surface); border: 1px solid var(--line-strong); border-radius: 4px; font: inherit; text-overflow: ellipsis; }
.yy-field select:focus-visible, .yy-field input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.table-wrap { max-width: 100%; overflow-x: auto; }
@media (max-width: 600px) {
  .orders-panel { padding: 14px; }
  .yy-actions { width: 100%; }
  .yy-field { width: 100%; }
  .yy-field select, .yy-field input { flex: 1; }
}
.orders-table {
  width: 100%;
  min-width: 720px;
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
  max-width: 240px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
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
