<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import PageHeader from '@/components/PageHeader.vue'
import QueryState from '@/components/QueryState.vue'
import FleetDeviceCardView from '@/features/fleet/FleetDeviceCardView.vue'
import { controlApiConfigured, operationsMockEnabled } from '@/api/control'
import {
  cancelFleetTask,
  fetchFleetSnapshot,
  fleetVersionLine,
  mockFleetSnapshot,
  resolveFleetDataMode,
  type FleetSnapshot,
} from '@/features/fleet/api'
import {
  cancellableTask,
  expandDeviceTargets,
  targetStatusLabel,
  type FleetDeviceTarget,
} from '@/features/fleet/batch'
import type { FleetDeviceCard } from '@/features/fleet/model'

const session = useSessionStore()
const mode = resolveFleetDataMode(controlApiConfigured, operationsMockEnabled)
const versionLine = fleetVersionLine(mode)

const loading = ref(false)
const loadError = ref('')
const snapshot = ref<FleetSnapshot | null>(null)
const selectedIds = ref<string[]>([])
const expanded = ref(false)
const detailDeviceId = ref<string | null>(null)
const cancelBusyId = ref('')
const cancelErrorByDevice = ref<Record<string, string>>({})
const cancelDoneByDevice = ref<Record<string, string>>({})

const devices = computed<FleetDeviceCard[]>(() => snapshot.value?.devices ?? [])
const selectedDevices = computed(() => devices.value.filter((device) => selectedIds.value.includes(device.deviceId)))
const batchCommand = { commandType: 'xianyu.publish_listing.steps.v1', requiredCapabilities: ['accessibility', 'ime'] }
const targets = computed<FleetDeviceTarget[]>(() =>
  expandDeviceTargets(selectedDevices.value, batchCommand),
)
const canCancel = computed(() => session.can('task.create'))
const selectDisabled = computed(() => mode === 'unavailable')
const expandDisabled = computed(() => mode === 'unavailable' || selectedDevices.value.length === 0)

function toggleDevice(deviceId: string) {
  selectedIds.value = selectedIds.value.includes(deviceId)
    ? selectedIds.value.filter((id) => id !== deviceId)
    : [...selectedIds.value, deviceId]
}

function toggleDetail(deviceId: string) {
  detailDeviceId.value = detailDeviceId.value === deviceId ? null : deviceId
}

async function refresh() {
  if (mode === 'unavailable') {
    loadError.value = '未配置 VITE_CONTROL_API_URL，设备工作台不允许自动回退 Mock 数据。'
    return
  }
  if (mode === 'mock') {
    snapshot.value = mockFleetSnapshot()
    loadError.value = ''
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    snapshot.value = await fetchFleetSnapshot()
  } catch (error) {
    // fail-closed：API 失败不回退 Mock，保持错误态。
    snapshot.value = null
    loadError.value = `Control API 请求失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

async function cancelTarget(target: FleetDeviceTarget) {
  const task = target.currentTask
  if (!task || !canCancel.value || !cancellableTask(task).cancellable) return
  cancelBusyId.value = target.deviceId
  cancelErrorByDevice.value[target.deviceId] = ''
  cancelDoneByDevice.value[target.deviceId] = ''
  try {
    const updated = await cancelFleetTask(task.taskId, `operator canceled from fleet workbench (${target.deviceId})`)
    cancelDoneByDevice.value[target.deviceId] = `已请求取消：${updated.state}`
    await refresh()
  } catch (error) {
    // 服务端负例（409 对账/终态、404、403 等）按设备渲染错误态，不显示成功。
    cancelErrorByDevice.value[target.deviceId] = error instanceof Error ? error.message : '取消失败'
  } finally {
    cancelBusyId.value = ''
  }
}

onMounted(() => { void refresh() })
</script>

<template>
  <div>
    <PageHeader title="设备工作台" description="真实设备舰队：在线/可执行分离、权限缺口、绑定账号与按设备任务。" :kicker="versionLine" />

    <div v-if="mode === 'mock'" class="notice fleet-mock-banner" role="status" data-testid="fleet-mock-banner">
      <strong>Mock 数据（开发模式）</strong>
      <p>当前显示冻结 fixture 形状的演示数据，不会触发真实设备或外部平台动作。正式模式必须配置 VITE_CONTROL_API_URL。</p>
    </div>
    <div v-if="mode === 'unavailable'" class="notice notice-danger" role="alert">
      <strong>Control API 未配置</strong>
      <p>未配置 VITE_CONTROL_API_URL，设备工作台保持关闭（fail-closed），不会自动回退 Mock 数据。</p>
    </div>
    <div v-if="snapshot?.taskLoadError" class="notice notice-info">{{ snapshot.taskLoadError }}</div>
    <div v-if="loadError" class="notice notice-danger" role="alert" data-testid="fleet-load-error">{{ loadError }}</div>

    <QueryState :loading="loading" :error="null" :empty="devices.length === 0 && !loading && !loadError" empty-text="当前租户还没有已接入的设备。">
      <div class="fleet-toolbar page-actions">
        <button class="button" type="button" :disabled="mode === 'unavailable' || loading" @click="refresh">刷新设备状态</button>
        <button class="button button-primary" type="button" :disabled="expandDisabled" @click="expanded = !expanded">
          {{ expanded ? '收起逐设备目标' : `展开为逐设备目标（${selectedDevices.length} 台）` }}
        </button>
        <button v-if="mode === 'unavailable'" class="button" type="button" disabled title="未配置 Control API，生产操作已关闭">Control API 不可用</button>
        <span class="cell-sub">已选 {{ selectedDevices.length }} 台 · 在线 {{ devices.filter((item) => item.online).length }} 台</span>
      </div>

      <section v-if="expanded" class="panel fleet-targets" data-testid="fleet-targets">
        <h3>批量选择已展开为显式逐设备目标</h3>
        <p class="cell-sub">每台设备独立判定与操作；离线/门禁未过/能力缺口均表示「不派发」，不是任务失败。</p>
        <div v-for="target in targets" :key="target.deviceId" class="fleet-target-row" :data-target-device="target.deviceId">
          <div class="fleet-target-main">
            <span class="tag" :class="target.status === 'ELIGIBLE' ? 'tag-ok' : 'tag-danger'">{{ targetStatusLabel(target.status) }}</span>
            <strong>{{ target.deviceName }}</strong>
            <span class="mono cell-sub">{{ target.deviceId }}</span>
            <span v-if="target.reason" class="cell-sub">{{ target.reason }}</span>
            <span v-if="target.currentTask" class="cell-sub">当前任务 {{ target.currentTask.commandType }} · {{ target.currentTask.state }}</span>
          </div>
          <div class="fleet-target-actions">
            <button class="button" type="button" :disabled="selectDisabled" @click="toggleDetail(target.deviceId)">{{ detailDeviceId === target.deviceId ? '收起' : '查看' }}</button>
            <button
              class="button button-danger"
              type="button"
              :disabled="!canCancel || !cancellableTask(target.currentTask).cancellable || cancelBusyId === target.deviceId"
              :title="!canCancel ? '当前身份缺少 task.create 权限' : (cancellableTask(target.currentTask).reason ?? '取消该设备当前任务')"
              @click="cancelTarget(target)"
            >
              {{ cancelBusyId === target.deviceId ? '取消中…' : '取消任务' }}
            </button>
          </div>
          <p v-if="cancelErrorByDevice[target.deviceId]" class="cell-sub fleet-target-error" role="alert" data-testid="fleet-cancel-error" :data-cancel-error="target.deviceId">
            取消失败：{{ cancelErrorByDevice[target.deviceId] }}
          </p>
          <p v-if="cancelDoneByDevice[target.deviceId]" class="cell-sub fleet-target-done">{{ cancelDoneByDevice[target.deviceId] }}</p>
        </div>
      </section>

      <section v-if="detailDeviceId" class="fleet-detail">
        <FleetDeviceCardView :device="devices.find((item) => item.deviceId === detailDeviceId)!" />
      </section>

      <div class="fleet-grid">
        <FleetDeviceCardView
          v-for="device in devices"
          :key="device.deviceId"
          :device="device"
          :selectable="!selectDisabled"
          :selected="selectedIds.includes(device.deviceId)"
          @toggle="toggleDevice"
        />
      </div>
    </QueryState>
  </div>
</template>

<style scoped>
.fleet-mock-banner { border: 2px dashed #d97706; font-weight: 600; }
.fleet-toolbar { margin-bottom: 12px; align-items: center; }
.fleet-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; margin-top: 12px; }
.fleet-targets { margin-bottom: 12px; padding: 14px 16px; }
.fleet-targets h3 { margin: 0 0 4px; }
.fleet-target-row { display: flex; flex-direction: column; gap: 6px; padding: 10px 0; border-top: 1px solid #e2e8f0; }
.fleet-target-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.fleet-target-actions { display: flex; gap: 8px; }
.fleet-target-error { color: #b91c1c; font-weight: 600; }
.fleet-target-done { color: #15803d; }
.fleet-detail { margin-bottom: 12px; }
.tag-ok { background: #dcfce7; color: #15803d; }
.tag-danger { background: #fee2e2; color: #b91c1c; }
</style>
