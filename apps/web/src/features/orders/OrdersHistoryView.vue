<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { controlApiConfigured } from '@/api/control'
import { ORDER_DIRECTION_OPTIONS, orderDirectionLabel } from '@/api/orders'
import { listFleetOrderHistory, FleetOrdersApiError, type FleetOrderHistoryQuery } from './api'
import {
  dedupeMarkerLabel,
  dedupeMarkerSummary,
  hasNextPage,
  historyAmountLabel,
  historyTimeLabel,
  hasMissingScreens,
  windowAnnotation,
  type FleetOrderHistoryResult,
} from './model'

/**
 * O10 订单历史切片视图：游标分页浏览 + 采集窗口/缺失页标注。
 * 只读：本页没有任何采集/发货/评价动作入口，只有查询。
 */

const PAGE_SIZE = 20

const deviceFilter = ref('')
const directionFilter = ref<'' | 'SOLD' | 'BOUGHT'>('')
const statusFilter = ref('')
const accountFilter = ref('')

const result = ref<FleetOrderHistoryResult | null>(null)
const loading = ref(false)
const loadError = ref('')

/** 游标栈：栈顶是当前页的进入游标（首页无游标）。 */
const cursorStack = ref<(string | undefined)[]>([undefined])

const currentCursor = computed(() => cursorStack.value[cursorStack.value.length - 1])
const canGoPrev = computed(() => cursorStack.value.length > 1)
const canGoNext = computed(() => (result.value ? hasNextPage(result.value) : false))
const rangeLabel = computed(() => {
  if (!result.value || result.value.items.length === 0) return '0 / 0'
  const start = result.value.offset + 1
  const end = result.value.offset + result.value.items.length
  return `${start}-${end} / ${result.value.total}`
})

function baseQuery(cursor?: string): FleetOrderHistoryQuery {
  return {
    deviceId: deviceFilter.value.trim() || undefined,
    direction: directionFilter.value || undefined,
    statusText: statusFilter.value.trim() || undefined,
    accountKey: accountFilter.value.trim() || undefined,
    limit: PAGE_SIZE,
    ...(cursor ? { cursor } : {}),
  }
}

async function load(cursor: string | undefined) {
  loading.value = true
  loadError.value = ''
  try {
    result.value = await listFleetOrderHistory(baseQuery(cursor))
  } catch (error) {
    // fail-closed：后端不可达/报错时如实展示，不渲染占位假数据。
    loadError.value = error instanceof FleetOrdersApiError ? error.message : '订单历史加载失败'
  } finally {
    loading.value = false
  }
}

async function refresh() {
  await load(currentCursor.value)
}

async function applyFilters() {
  cursorStack.value = [undefined]
  await load(undefined)
}

async function goNext() {
  if (!result.value?.nextCursor) return
  cursorStack.value.push(result.value.nextCursor)
  await load(result.value.nextCursor)
}

async function goPrev() {
  if (cursorStack.value.length <= 1) return
  cursorStack.value.pop()
  await load(cursorStack.value[cursorStack.value.length - 1])
}

const showEmpty = computed(() => !loading.value && !loadError.value && (result.value?.items.length ?? 0) === 0)

const emptyText = computed(() => {
  if (!controlApiConfigured) return '未配置 Control API，无法读取订单历史。'
  return '暂无订单历史。手机分屏上报后会出现在这里。'
})

const markerSummary = computed(() =>
  result.value ? dedupeMarkerSummary(result.value.dedupeMarkers) : '',
)

onMounted(() => {
  void load(undefined)
})
</script>

<template>
  <section class="orders-history" data-testid="orders-history">
    <header class="orders-history__header">
      <div>
        <h2>订单历史切片</h2>
        <p class="orders-history__hint">
          按采集游标分页浏览；每个采集批次注明采集窗口与缺失页。本页为只读查询，不包含任何发货、评价或交易操作。
        </p>
      </div>
    </header>

    <form class="orders-history__filters" @submit.prevent="applyFilters">
      <label>
        设备 ID
        <input v-model="deviceFilter" type="text" placeholder="按设备过滤" data-testid="filter-device" />
      </label>
      <label>
        方向
        <select v-model="directionFilter" data-testid="filter-direction">
          <option value="">全部</option>
          <option v-for="option in ORDER_DIRECTION_OPTIONS" :key="option.key" :value="option.key">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label>
        状态
        <input v-model="statusFilter" type="text" placeholder="如 待发货" data-testid="filter-status" />
      </label>
      <label>
        账号
        <input v-model="accountFilter" type="text" placeholder="按采集账号过滤窗口" data-testid="filter-account" />
      </label>
      <button type="submit" :disabled="loading" data-testid="apply-filters">应用过滤</button>
      <button type="button" :disabled="loading" data-testid="refresh" @click="refresh">刷新</button>
    </form>

    <p v-if="loadError" class="orders-history__error" role="alert" data-testid="history-error">{{ loadError }}</p>

    <p v-if="markerSummary" class="orders-history__markers" data-testid="dedupe-markers">
      去重口径：{{ markerSummary }}
    </p>

    <div v-if="result && result.windows.length > 0" class="orders-history__windows" data-testid="collection-windows">
      <h3>采集窗口</h3>
      <ul>
        <li
          v-for="window in result.windows"
          :key="`${window.runKey}-${window.accountKey}`"
          :data-testid="`window-${window.runKey}`"
        >
          <strong>{{ window.runKey }}</strong>
          <span class="orders-history__window-account">{{ window.accountKey }} · {{ orderDirectionLabel(window.direction) }}</span>
          <span v-if="hasMissingScreens(window)" class="orders-history__missing" data-testid="missing-badge">缺失页</span>
          <span class="orders-history__window-annotation">{{ windowAnnotation(window) }}</span>
        </li>
      </ul>
    </div>

    <table v-if="result && result.items.length > 0" class="orders-history__table" data-testid="history-table">
      <thead>
        <tr>
          <th>订单键</th>
          <th>去重标记</th>
          <th>商品</th>
          <th>对手</th>
          <th>金额</th>
          <th>状态</th>
          <th>时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in result.items" :key="item.id" :data-testid="`history-row-${item.orderKey}`">
          <td class="orders-history__key">{{ item.orderKey }}</td>
          <td>{{ dedupeMarkerLabel(item.dedupeMarker) }}</td>
          <td>{{ item.itemTitle ?? '—' }}</td>
          <td>{{ item.buyerName ?? '—' }}</td>
          <td>{{ historyAmountLabel(item.amountCents) }}</td>
          <td>{{ item.statusText ?? '—' }}</td>
          <td>{{ historyTimeLabel(item.occurredAt) }}</td>
        </tr>
      </tbody>
    </table>

    <p v-if="showEmpty" class="orders-history__empty" data-testid="history-empty">{{ emptyText }}</p>

    <footer class="orders-history__pager" data-testid="history-pager">
      <span class="orders-history__range">{{ rangeLabel }}</span>
      <button type="button" :disabled="!canGoPrev || loading" data-testid="pager-prev" @click="goPrev">上一页</button>
      <button type="button" :disabled="!canGoNext || loading" data-testid="pager-next" @click="goNext">下一页</button>
    </footer>
  </section>
</template>

<style scoped>
.orders-history__header h2 {
  margin: 0 0 4px;
}
.orders-history__hint {
  margin: 0 0 12px;
  color: var(--color-text-secondary, #6b7280);
  font-size: 13px;
}
.orders-history__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 12px;
}
.orders-history__filters label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.orders-history__error {
  color: #b91c1c;
}
.orders-history__markers {
  font-size: 13px;
  color: var(--color-text-secondary, #6b7280);
}
.orders-history__windows {
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.orders-history__windows h3 {
  margin: 4px 0 8px;
  font-size: 14px;
}
.orders-history__windows ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.orders-history__window-account {
  margin-left: 8px;
  font-size: 12px;
  color: var(--color-text-secondary, #6b7280);
}
.orders-history__missing {
  margin-left: 8px;
  font-size: 12px;
  color: #b45309;
  border: 1px solid #f59e0b;
  border-radius: 4px;
  padding: 0 4px;
}
.orders-history__window-annotation {
  display: block;
  font-size: 13px;
  margin-top: 2px;
}
.orders-history__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.orders-history__table th,
.orders-history__table td {
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  padding: 6px 8px;
  text-align: left;
}
.orders-history__key {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.orders-history__empty {
  color: var(--color-text-secondary, #6b7280);
}
.orders-history__pager {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.orders-history__range {
  font-size: 13px;
  color: var(--color-text-secondary, #6b7280);
  margin-right: auto;
}
</style>
