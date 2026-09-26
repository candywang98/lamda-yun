<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-vue-next'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
import { useSessionStore } from '@/stores/session'
import {
  deviceLabel,
  emptyListingCollectConfig,
  loadListingCollectConfig,
  saveListingCollectConfig,
  type ListingCollectDevice,
} from '@/data/listing-info-collect'
import {
  dispatchListingCollectTask,
  listFleetListings,
} from '@/features/fleet/listings-api'
import {
  listingHistoryRows,
  listingPlatformLabel,
  listingSourceLabel,
  newListingCollectBatch,
  type ListingCollectAttempt,
} from '@/features/fleet/listing-collection'

const router = useRouter()
const session = useSessionStore()
const form = reactive(emptyListingCollectConfig())
const devices = ref<ListingCollectDevice[]>([])
const devicesLoading = ref(false)
const devicesError = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const canCollect = computed(() => controlApiConfigured && session.can('device.control'))
const selectionLocked = computed(() => !canCollect.value || dispatching.value || devicesLoading.value)
const deviceNames = computed(() => new Map(devices.value.map((device) => [device.id, deviceLabel(device)])))
let disposed = false
let deviceRequest = 0

const selectedDevices = computed(() => devices.value.filter((item) => form.deviceIds.includes(item.id)))
const selectedCount = computed(() => selectedDevices.value.length)

async function loadDevices() {
  const request = ++deviceRequest
  devicesError.value = ''
  if (!controlApiConfigured) {
    devices.value = []
    devicesError.value = '未配置 Control API，无法读取执行设备'
    return
  }
  devicesLoading.value = true
  try {
    const api = createControlApiClient()
    const rows = await api.devices()
    if (disposed || request !== deviceRequest) return
    devices.value = rows.map((item) => {
      const mapped = mapControlDevice(item)
      const account = mapped.account && mapped.account !== '通过账号 API 查看' ? mapped.account : ''
      return { id: mapped.id, name: mapped.name, account, online: mapped.presence === 'ONLINE' }
    })
    form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
  } catch (error) {
    if (disposed || request !== deviceRequest) return
    devices.value = []
    devicesError.value = error instanceof Error ? error.message : '执行设备加载失败'
  } finally {
    if (!disposed && request === deviceRequest) devicesLoading.value = false
  }
}

function toggleDevice(id: string) {
  if (selectionLocked.value) return
  form.deviceIds = form.deviceIds.includes(id)
    ? form.deviceIds.filter((item) => item !== id)
    : [...form.deviceIds, id]
}

function selectAllDevices() {
  if (selectionLocked.value) return
  const ids = devices.value.map((item) => item.id)
  form.deviceIds = form.deviceIds.length === ids.length ? [] : ids
}

function selectOnlineDevices() {
  if (selectionLocked.value) return
  form.deviceIds = devices.value.filter((item) => item.online).map((item) => item.id)
}

function clearSelection() {
  if (selectionLocked.value) return
  form.deviceIds = []
}

function saveConfig() {
  if (selectionLocked.value) return
  errorMessage.value = ''
  successMessage.value = ''
  try {
    saveListingCollectConfig({ ...form, schedule: '立即执行' })
    successMessage.value = '配置已保存到当前浏览器'
  } catch {
    errorMessage.value = '当前浏览器无法保存配置'
  }
}

const PAGE_SIZE = 50
const listingResults = ref<ReturnType<typeof listingHistoryRows>>([])
const listingTotal = ref<number | null>(null)
const listingsLoading = ref(false)
const listingsError = ref('')
const historyDevice = ref('')
const cursors = ref<(string | undefined)[]>([undefined])
const nextCursor = ref<string | null>(null)
let listingRequest = 0
const currentCursor = computed(() => cursors.value[cursors.value.length - 1])
const dispatching = ref(false)
const batch = ref<ListingCollectAttempt[]>([])
const unresolved = computed(() => batch.value.filter((item) => item.state !== 'accepted'))
const acceptedCount = computed(() => batch.value.filter((item) => item.state === 'accepted').length)
const stateLabels = { pending: '待派发', dispatching: '派发中', accepted: '已受理', unresolved: '失败 / 未确认' }

async function loadListings(targetCursors = [...cursors.value]) {
  const request = ++listingRequest
  const deviceId = historyDevice.value || undefined
  listingsLoading.value = true
  listingsError.value = ''
  try {
    const cursor = targetCursors[targetCursors.length - 1]
    const result = await listFleetListings({ deviceId, limit: PAGE_SIZE, ...(cursor ? { cursor } : {}) })
    if (disposed || request !== listingRequest) return
    listingResults.value = listingHistoryRows(result.items, request)
    listingTotal.value = result.total
    nextCursor.value = result.nextCursor
    cursors.value = targetCursors
  } catch (error) {
    if (!disposed && request === listingRequest) {
      listingsError.value = error instanceof Error ? error.message : '采集历史加载失败'
    }
  } finally {
    if (!disposed && request === listingRequest) listingsLoading.value = false
  }
}

function nextPage() {
  if (listingsLoading.value || !nextCursor.value || nextCursor.value === currentCursor.value) return
  void loadListings([...cursors.value, nextCursor.value])
}

function previousPage() {
  if (listingsLoading.value || cursors.value.length <= 1) return
  void loadListings(cursors.value.slice(0, -1))
}

watch(historyDevice, () => {
  listingResults.value = []
  listingTotal.value = null
  nextCursor.value = null
  cursors.value = [undefined]
  void loadListings()
}, { flush: 'sync' })

async function dispatchUnresolved() {
  if (dispatching.value || !canCollect.value || disposed) return
  dispatching.value = true
  errorMessage.value = ''
  successMessage.value = ''
  // Snapshot the unresolved attempt objects, never the live device selection.
  const attempts = unresolved.value.slice()
  try {
    for (const attempt of attempts) {
      if (disposed) return
      if (!canCollect.value) {
        attempt.state = 'unresolved'
        attempt.error = '当前身份缺少 device.control 权限，未派发'
        continue
      }
      attempt.state = 'dispatching'
      attempt.error = ''
      try {
        const { taskId } = await dispatchListingCollectTask({
          deviceId: attempt.deviceId,
          idempotencyKey: attempt.idempotencyKey,
        })
        if (disposed) return
        attempt.taskId = taskId
        attempt.state = 'accepted'
      } catch (error) {
        if (disposed) return
        attempt.state = 'unresolved'
        attempt.error = error instanceof Error ? error.message : '派发结果未确认'
      }
    }
  } finally {
    if (!disposed) dispatching.value = false
  }
}

async function createTask() {
  if (selectionLocked.value || unresolved.value.length > 0 || disposed) return
  errorMessage.value = ''
  successMessage.value = ''
  if (selectedDevices.value.length === 0) {
    errorMessage.value = '请先选择执行设备'
    return
  }
  try {
    batch.value = newListingCollectBatch(selectedDevices.value)
  } catch {
    errorMessage.value = '无法生成采集批次标识，未派发任务'
    return
  }
  await dispatchUnresolved()
}

onMounted(() => {
  const saved = loadListingCollectConfig()
  Object.assign(form, saved, { deviceIds: Array.isArray(saved.deviceIds) ? saved.deviceIds : [], schedule: '立即执行' })
  void loadDevices()
  void loadListings()
})

onBeforeUnmount(() => {
  disposed = true
  ++listingRequest
  ++deviceRequest
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>宝贝信息</h2>
      <div class="row top">
        <span class="label">执行设备</span>
        <div>
          <p v-if="devicesLoading" class="hint" role="status">加载设备中…</p>
          <p v-else-if="devicesError" class="flash error" role="alert">{{ devicesError }}</p>
          <div v-else-if="devices.length === 0" class="hint">当前没有已接入设备。接入 Companion 后会出现在这里。</div>
          <label v-for="device in devices" :key="device.id" class="chip">
            <input type="checkbox" :checked="form.deviceIds.includes(device.id)" :disabled="selectionLocked" @change="toggleDevice(device.id)" />
            {{ deviceLabel(device) }}
            <small :class="device.online ? 'on' : 'off'">{{ device.online ? '在线' : '离线' }}</small>
          </label>
          <div class="links">
            <button type="button" :disabled="selectionLocked" @click="selectAllDevices">全选/反选设备</button>
            <button type="button" :disabled="selectionLocked" @click="selectOnlineDevices">全选在线设备</button>
            <button type="button" :disabled="selectionLocked" @click="clearSelection">全部取消选择</button>
            <span class="count">{{ selectedCount }}</span>
            <button type="button" class="icon-button" aria-label="刷新设备" title="刷新设备" :disabled="devicesLoading || dispatching" @click="loadDevices">
              <RefreshCw :size="14" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
      <div class="row">
        <span class="label">执行应用</span>
        <div>
          <label class="radio" for="listing-app-main"><input id="listing-app-main" v-model="form.app" type="radio" value="main" :disabled="selectionLocked" /> 主闲鱼</label>
          <p class="hint">一期每设备仅绑定一个闲鱼账号，副闲鱼/先主后副已禁用。</p>
        </div>
      </div>
      <div class="row"><span class="label">执行时间</span><span>立即执行</span></div>
      <p v-if="!session.can('device.control')" class="hint">当前角色只读，不能创建采集任务。</p>
      <p v-if="errorMessage" class="flash error" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok" role="status">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" :disabled="selectionLocked || selectedCount === 0 || unresolved.length > 0" @click="createTask">
          {{ dispatching ? '派发中…' : batch.length > 0 ? '新建采集任务' : '创建任务' }}
        </button>
        <button v-if="unresolved.length > 0" class="primary" type="button" :disabled="dispatching || !canCollect" @click="dispatchUnresolved">
          <RefreshCw :size="14" aria-hidden="true" />重试未确认设备
        </button>
        <button class="primary" type="button" :disabled="selectionLocked" @click="saveConfig">保存配置</button>
      </div>
      <div v-if="batch.length > 0" class="batch-results" aria-label="采集派发结果" :aria-busy="dispatching">
        <p role="status">本批次 {{ batch.length }} 台设备：已受理 {{ acceptedCount }} 台，未确认 {{ unresolved.length }} 台</p>
        <ul>
          <li v-for="attempt in batch" :key="attempt.deviceId">
            <strong>{{ attempt.deviceName }}</strong> <span class="hint">{{ attempt.deviceId }}</span>
            <span :class="attempt.state === 'unresolved' ? 'error' : ''">{{ stateLabels[attempt.state] }}</span>
            <code v-if="attempt.taskId">{{ attempt.taskId }}</code>
            <span v-if="attempt.error" class="error">{{ attempt.error }}</span>
          </li>
        </ul>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>该任务用来采集您闲鱼的宝贝信息如：宝贝标题、曝光量、浏览量、想要数，采集后可在 <button class="link" type="button" @click="router.push('/operations/analytics/analytics-02')">统计分析-&gt;宝贝流量变化</button> 查看数据</li>
      </ol>
    </div>
    <div class="card" aria-label="采集历史" :aria-busy="listingsLoading">
      <header class="history-head">
        <h2>采集结果<span v-if="listingTotal !== null">（共 {{ listingTotal }} 条）</span></h2>
        <div class="history-controls">
          <label for="listing-history-device">来源设备</label>
          <select id="listing-history-device" v-model="historyDevice">
            <option value="">全部设备</option>
            <option v-for="device in devices" :key="device.id" :value="device.id">{{ deviceLabel(device) }}</option>
            <option v-if="historyDevice && !deviceNames.has(historyDevice)" :value="historyDevice">{{ historyDevice }}</option>
          </select>
          <button class="icon-button" type="button" aria-label="刷新采集历史" title="刷新采集历史" @click="loadListings([undefined])">
            <RefreshCw :size="16" aria-hidden="true" />
          </button>
        </div>
      </header>
      <p v-if="listingsLoading" class="hint" role="status">加载采集历史中…</p>
      <p v-if="listingsError" class="error" role="alert">{{ listingsError }}</p>
      <p v-if="!listingsLoading && !listingsError && listingResults.length === 0" class="hint">暂无采集结果。</p>
      <div v-if="listingResults.length > 0" class="table-scroll">
        <table class="table">
          <thead>
            <tr><th>来源设备</th><th>平台</th><th>宝贝</th><th>价格</th><th>曝光</th><th>浏览</th><th>想要</th><th>状态</th><th>快照数</th><th>最近采集</th></tr>
          </thead>
          <tbody>
            <tr v-for="{ item, key } in listingResults" :key="key">
              <td>{{ listingSourceLabel(item, deviceNames) }}</td>
              <td>{{ listingPlatformLabel(item) }}</td>
              <td>{{ item.title ?? item.itemKey }}</td>
              <td>{{ item.priceText ?? (item.priceCents !== null ? (item.priceCents / 100).toFixed(2) : '—') }}</td>
              <td>{{ item.exposureCount ?? '—' }}</td>
              <td>{{ item.viewsCount ?? '—' }}</td>
              <td>{{ item.wantsCount ?? '—' }}</td>
              <td>{{ item.statusText ?? '—' }}</td>
              <td>{{ item.snapshotCount }}</td>
              <td>{{ item.lastSeenAt?.replace('T', ' ').slice(0, 19) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="history-pager">
        <span>第 {{ cursors.length }} 页</span>
        <button class="icon-button" type="button" title="上一页" aria-label="上一页" :disabled="listingsLoading || cursors.length <= 1" @click="previousPage">
          <ChevronLeft :size="16" aria-hidden="true" />
        </button>
        <button class="icon-button" type="button" title="下一页" aria-label="下一页" :disabled="listingsLoading || !nextCursor || nextCursor === currentCursor" @click="nextPage">
          <ChevronRight :size="16" aria-hidden="true" />
        </button>
      </footer>
    </div>
  </section>
</template>

<style scoped>
.page { display: grid; gap: 10px; color: #334155; }
.card, .help { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.card { padding: 16px 18px 20px; display: grid; gap: 16px; }
h2 { margin: 0; font-size: 15px; }
.row { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 12px; align-items: center; }
.row.top { align-items: start; }
.label { color: #64748b; font-size: 13px; padding-top: 6px; }
select { width: min(280px, 100%); height: 34px; padding: 0 10px; border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
.radio, .chip { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 8px 0; }
.chip { padding: 4px 8px; border: 1px solid #e5e7eb; border-radius: 6px; }
.chip small { padding: 0 6px; border-radius: 4px; font-size: 11px; background: #f1f5f9; }
.chip small.on { background: #dcfce7; color: #166534; }
.chip small.off { color: #64748b; }
.links { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 6px; color: #0f766e; font-size: 13px; }
.links button, .link { border: 0; background: none; color: #0f766e; padding: 0; }
.count { min-width: 22px; height: 22px; padding: 0 6px; border-radius: 4px; background: #f1f5f9; color: #334155; text-align: center; }
.hint { color: #94a3b8; font-size: 12px; }
.footer { padding-left: 100px; display: flex; gap: 10px; }
.primary { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: #0f766e; color: #fff; }
.flash { margin: 0; padding-left: 100px; font-size: 13px; }
.flash.error { color: #b91c1c; }
.flash.ok { color: #166534; }
.help { padding: 12px 14px 16px; }
.help h3 { margin: 0 0 8px; font-size: 14px; }
.help ol { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.primary { display: inline-flex; align-items: center; gap: 6px; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.footer, .history-head, .history-controls, .history-pager { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.history-head { justify-content: space-between; }
.history-pager { justify-content: flex-end; }
.icon-button { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; border: 1px solid #d1d5db; border-radius: 4px; background: #fff; color: #0f766e; }
.table-scroll { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: left; overflow-wrap: anywhere; min-width: 56px; }
.table td:first-child { min-width: 140px; }
.batch-results ul { margin: 0; padding-left: 18px; }
.batch-results li { padding: 4px 0; display: flex; flex-wrap: wrap; gap: 8px; overflow-wrap: anywhere; }
.error { color: #b91c1c; }
.card { min-width: 0; }
@media (max-width: 720px) {
  .row { grid-template-columns: minmax(0, 1fr); }
  .footer, .flash { padding-left: 0; }
}
</style>
