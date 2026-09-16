<script setup lang="ts">
import { computed } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { Status } from '@/types'
import {
  gateLabel,
  offlineReasonOf,
  permissionGapSummary,
  type FleetDeviceCard,
} from '@/features/fleet/model'

const props = defineProps<{ device: FleetDeviceCard; selectable?: boolean; selected?: boolean }>()
defineEmits<{ toggle: [deviceId: string] }>()

const offlineReason = computed(() => offlineReasonOf(props.device))
const permissionGaps = computed(() => permissionGapSummary(props.device))
const eligibilityTone = computed(() => {
  if (!props.device.online) return 'tag-danger'
  return props.device.executable === true ? 'tag-ok' : 'tag-warn'
})
const eligibilityLabel = computed(() => {
  if (!props.device.online) return '离线'
  if (props.device.executable === true) return '可执行'
  if (props.device.executable === false) return '不可执行'
  return '可执行性未回传'
})
const settledFailure = computed(() =>
  props.device.settledTask && ['FAILED', 'EXPIRED'].includes(props.device.settledTask.state)
    ? props.device.settledTask
    : null,
)

function taskStatus(state: string): Status {
  if (state === 'SUCCEEDED') return 'SUCCEEDED'
  if (state === 'FAILED' || state === 'EXPIRED') return 'FAILED'
  if (state === 'CANCELLED') return 'CANCELED'
  if (state === 'RUNNING' || state === 'CLAIMED' || state === 'PREFLIGHT') return 'RUNNING'
  if (state === 'RECONCILING' || state === 'PAUSED_WAITING_USER') return 'PAUSED'
  return 'QUEUED'
}
</script>

<template>
  <article class="panel fleet-card" :data-device-id="device.deviceId">
    <div class="fleet-card-head">
      <label v-if="selectable" class="chip-select">
        <input
          type="checkbox"
          :checked="selected"
          :disabled="!device.online"
          @change="$emit('toggle', device.deviceId)"
        />
      </label>
      <div class="fleet-card-title">
        <strong>{{ device.name }}</strong>
        <span class="mono cell-sub">{{ device.deviceId }}</span>
      </div>
      <span class="tag" :class="eligibilityTone">{{ eligibilityLabel }}</span>
      <span class="tag">{{ device.online ? '在线' : '离线' }}</span>
    </div>

    <div v-if="offlineReason" class="notice notice-danger fleet-gap" role="note">
      离线原因：{{ offlineReason }}
    </div>
    <div v-if="permissionGaps.length > 0" class="notice notice-info fleet-gap" role="note">
      <strong>权限缺口</strong>
      <ul class="fleet-gap-list">
        <li v-for="gap in permissionGaps" :key="gap">{{ gap }}</li>
      </ul>
    </div>

    <div class="definition-grid">
      <div class="definition-item"><span>绑定账号</span><strong class="mono">{{ device.accountId ?? '未回传（账号 API）' }}</strong></div>
      <div class="definition-item"><span>绑定版本</span><strong class="mono">{{ device.bindingVersion ?? '未回传' }}</strong></div>
      <div class="definition-item">
        <span>持有者</span>
        <strong class="mono">{{ device.holderSessionId ?? '无持有会话' }}</strong>
      </div>
      <div class="definition-item"><span>最后心跳</span><strong class="mono">{{ device.lastSeenAt ?? '未上报' }}</strong></div>
    </div>

    <div class="fleet-card-section">
      <h4>能力表（{{ device.capabilities.length }}/{{ 6 }} 键已回传）</h4>
      <div class="tag-list">
        <span
          v-for="capability in device.capabilities"
          :key="capability.key"
          class="tag"
          :class="capability.supported ? '' : 'tag-danger'"
        >
          {{ capability.key }}{{ capability.supported ? '' : ' 不支持' }}{{ capability.engineMin != null ? ` · min ${capability.engineMin}` : '' }}
        </span>
        <span v-if="device.executableGates.length > 0" class="tag tag-ok">门禁已过：{{ device.executableGates.map(gateLabel).join(' / ') }}</span>
      </div>
    </div>

    <div class="fleet-card-section" data-section="current-task">
      <h4>当前任务（仅本设备）</h4>
      <p v-if="device.currentTask" class="fleet-task">
        <StatusBadge :status="taskStatus(device.currentTask.state)" />
        <span class="mono">{{ device.currentTask.taskId.slice(0, 8) }}</span>
        <span>{{ device.currentTask.commandType }}</span>
        <span v-if="device.currentTask.detail" class="cell-sub">{{ device.currentTask.detail }}</span>
      </p>
      <p v-else class="cell-sub">无进行中任务</p>
      <p v-if="settledFailure" class="fleet-task fleet-task-failed" data-failure="own">
        最近失败（本设备）：{{ settledFailure.commandType }} · {{ settledFailure.errorCode ?? 'UNKNOWN' }} · {{ settledFailure.detail ?? '无详情' }}
      </p>
      <p v-else-if="device.settledTask" class="cell-sub">
        最近终态：{{ device.settledTask.state }} · {{ device.settledTask.commandType }}
      </p>
    </div>
  </article>
</template>

<style scoped>
.fleet-card { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.fleet-card-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.fleet-card-title { display: flex; flex-direction: column; min-width: 0; margin-right: auto; }
.fleet-card-section h4 { margin: 0 0 6px; font-size: 13px; color: #475569; }
.fleet-gap { margin: 0; }
.fleet-gap-list { margin: 4px 0 0; padding-left: 18px; }
.fleet-task { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0; }
.fleet-task-failed { color: #b91c1c; font-weight: 600; width: 100%; }
.chip-select input { width: 16px; height: 16px; accent-color: #0f766e; }
.tag-ok { background: #dcfce7; color: #15803d; }
.tag-warn { background: #fef9c3; color: #a16207; }
.tag-danger { background: #fee2e2; color: #b91c1c; }
</style>
