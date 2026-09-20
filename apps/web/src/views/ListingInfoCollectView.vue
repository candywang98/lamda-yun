<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import ScheduleEditor, { type ScheduleDraft } from '@/components/ScheduleEditor.vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'
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
  type FleetListingItem,
} from '@/features/fleet/listings-api'

const router = useRouter()
const form = reactive(emptyListingCollectConfig())
const devices = ref<ListingCollectDevice[]>([])
const errorMessage = ref('')
const successMessage = ref('')
const schedule = ref<ScheduleDraft>({
  kind: 'IMMEDIATE',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
  onceAt: '',
  rrule: 'FREQ=DAILY;INTERVAL=1',
  missPolicy: 'QUEUE_ONE',
  startDeadlineMinutes: 30,
})

const selectedCount = computed(() => form.deviceIds.filter((id) => devices.value.some((item) => item.id === id)).length)
const selectedDevices = computed(() => devices.value.filter((item) => form.deviceIds.includes(item.id)))

async function loadDevices() {
  if (!controlApiConfigured) {
    devices.value = []
    return
  }
  try {
    const api = createControlApiClient()
    devices.value = (await api.devices()).map((item) => {
      const mapped = mapControlDevice(item)
      const account = mapped.account && mapped.account !== '通过账号 API 查看' ? mapped.account : ''
      return { id: mapped.id, name: mapped.name, account, online: mapped.presence === 'ONLINE' }
    })
  } catch {
    devices.value = []
  }
}

function toggleDevice(id: string) {
  form.deviceIds = form.deviceIds.includes(id)
    ? form.deviceIds.filter((item) => item !== id)
    : [...form.deviceIds, id]
}

function selectAllDevices() {
  const ids = devices.value.map((item) => item.id)
  form.deviceIds = form.deviceIds.length === ids.length ? [] : ids
}

function selectOnlineDevices() {
  form.deviceIds = devices.value.filter((item) => item.online).map((item) => item.id)
}

function saveConfig() {
  saveListingCollectConfig(form)
  errorMessage.value = ''
  successMessage.value = '配置已保存到当前浏览器'
}

const listingResults = ref<FleetListingItem[]>([])
const listingTotal = ref(0)
const dispatching = ref(false)

async function loadListings() {
  try {
    const result = await listFleetListings({ limit: 50 })
    listingResults.value = result.items
    listingTotal.value = result.total
  } catch (error) {
    listingResults.value = []
    listingTotal.value = 0
  }
}

async function createTask() {
  errorMessage.value = ''
  successMessage.value = ''
  if (form.deviceIds.length === 0) {
    errorMessage.value = '请先选择执行设备'
    return
  }
  saveListingCollectConfig(form)
  dispatching.value = true
  try {
    const dispatched: string[] = []
    for (const device of selectedDevices.value) {
      const key = `listing-collect-${device.id}-${new Date().toISOString().slice(0, 10)}`
      const { taskId } = await dispatchListingCollectTask({ deviceId: device.id, idempotencyKey: key })
      dispatched.push(taskId)
    }
    successMessage.value = `已向 ${dispatched.length} 台设备派发只读采集任务（taskId: ${dispatched.join('、')}）。采集结果见下方列表。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    dispatching.value = false
  }
}

onMounted(async () => {
  Object.assign(form, loadListingCollectConfig())
  await loadDevices()
  form.deviceIds = form.deviceIds.filter((id) => devices.value.some((item) => item.id === id))
  await loadListings()
})
</script>

<template>
  <section class="page">
    <div class="card">
      <h2>宝贝信息</h2>
      <div class="row top">
        <span class="label">执行设备</span>
        <div>
          <div v-if="devices.length === 0" class="hint">当前没有已接入设备。接入 Companion 后会出现在这里。</div>
          <label v-for="device in devices" :key="device.id" class="chip">
            <input type="checkbox" :checked="form.deviceIds.includes(device.id)" @change="toggleDevice(device.id)" />
            {{ deviceLabel(device) }}
            <small :class="device.online ? 'on' : 'off'">{{ device.online ? '在线' : '离线' }}</small>
          </label>
          <div class="links">
            <button type="button" @click="selectAllDevices">全选/反选设备</button>
            <button type="button" @click="selectOnlineDevices">全选在线设备</button>
            <button type="button" @click="form.deviceIds = []">全部取消选择</button>
            <span class="count">{{ selectedCount }}</span>
          </div>
        </div>
      </div>
      <div class="row">
        <span class="label">执行应用</span>
        <div>
          <label class="radio" for="listing-app-main"><input id="listing-app-main" v-model="form.app" type="radio" value="main" /> 主闲鱼</label>
          <p class="hint">一期每设备仅绑定一个闲鱼账号，副闲鱼/先主后副已禁用。</p>
        </div>
      </div>
      <ScheduleEditor v-model="schedule" :device-count="form.deviceIds.length" :offline-queued="true" />
      <p v-if="errorMessage" class="flash error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="flash ok">{{ successMessage }}</p>
      <div class="footer">
        <button class="primary" type="button" @click="createTask">创建任务</button>
        <button class="primary" type="button" @click="saveConfig">保存配置</button>
      </div>
    </div>
    <div class="help">
      <h3>使用说明</h3>
      <ol>
        <li>该任务用来采集您闲鱼的宝贝信息如：宝贝标题、曝光量、浏览量、想要数，采集后可在 <button class="link" type="button" @click="router.push('/operations/analytics/analytics-02')">统计分析-&gt;宝贝流量变化</button> 查看数据</li>
        <li>请勿发布相同标题的宝贝，相同标题的宝贝系统仅统计一个</li>
        <li>仅当设备在线时，才能创建定时执行任务和每天重复执行的任务</li>
      </ol>
    </div>
      <div v-if="listingResults.length > 0 || listingTotal > 0" class="card">
      <h2>采集结果（最新 {{ listingTotal }} 条）</h2>
      <table class="table">
        <thead>
          <tr><th>宝贝</th><th>价格</th><th>状态</th><th>快照数</th><th>最近采集</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in listingResults" :key="item.itemKey">
            <td>{{ item.title ?? item.itemKey }}</td>
            <td>{{ item.priceText ?? (item.priceCents !== null ? (item.priceCents / 100).toFixed(2) : '—') }}</td>
            <td>{{ item.statusText ?? '—' }}</td>
            <td>{{ item.snapshotCount }}</td>
            <td>{{ item.lastSeenAt?.replace('T', ' ').slice(0, 19) ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
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
</style>
