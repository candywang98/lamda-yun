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
import { heartbeatLabel, readinessOf, shortDeviceIds } from '@/features/fleet/presentation'

const props = defineProps<{ device: FleetDeviceCard; shortId?: string; selectable?: boolean; selected?: boolean }>()
defineEmits<{ toggle: [deviceId: string] }>()

const offlineReason = computed(() => offlineReasonOf(props.device))
const executionIssues = computed(() => permissionGapSummary(props.device))
const readiness = computed(() => readinessOf(props.device))
const heartbeat = computed(() => heartbeatLabel(props.device.lastSeenAt))
const displayId = computed(() => props.shortId ?? shortDeviceIds([props.device]).get(props.device.deviceId))
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
          :aria-label="`选择设备 ${device.name}（${device.deviceId}）`"
          @change="$emit('toggle', device.deviceId)"
        />
      </label>
      <div class="fleet-card-title">
        <strong :title="device.name">{{ device.name }}</strong>
        <span class="mono cell-sub fleet-short-id" :title="device.deviceId" :aria-label="`设备 ID：${device.deviceId}`">ID {{ displayId }}</span>
      </div>
      <span class="tag fleet-connection" :class="device.online ? 'tag-ok' : ''">{{ device.online ? '在线' : '离线' }}</span>
    </div>
    <span v-if="readiness" class="tag fleet-readiness" :class="readiness.tone">{{ readiness.label }}</span>

    <div v-if="offlineReason" class="cell-sub fleet-gap" role="note">
      离线原因：{{ offlineReason }}
    </div>
    <div v-if="executionIssues.length > 0" class="cell-sub fleet-gap" role="note">
      {{ executionIssues.join('；') }}
    </div>

    <dl class="fleet-facts">
      <div><dt>应用版本</dt><dd>{{ device.appVersion ?? '未上报' }}</dd></div>
      <div><dt>最后心跳<span class="fleet-timezone">Asia/Shanghai</span></dt><dd :title="device.lastSeenAt ?? '未上报'">{{ heartbeat }}</dd></div>
    </dl>

    <div class="fleet-card-section" data-section="current-task">
      <h4>当前任务（仅本设备）</h4>
      <p v-if="device.currentTask" class="fleet-task">
        <StatusBadge :status="taskStatus(device.currentTask.state)" />
        <span class="mono" :title="device.currentTask.taskId">{{ device.currentTask.taskId.slice(0, 8) }}</span>
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

    <details class="fleet-technical">
      <summary>技术详情</summary>
      <dl class="fleet-facts">
        <div><dt>设备 UUID</dt><dd class="mono">{{ device.deviceId }}</dd></div>
        <div><dt>绑定账号</dt><dd class="mono">{{ device.accountId ?? '未上报' }}</dd></div>
        <div><dt>绑定版本（修订号）</dt><dd>{{ device.bindingVersion ?? '未上报' }}</dd></div>
        <div><dt>持有会话</dt><dd class="mono">{{ device.holderSessionId ?? '未上报' }}</dd></div>
        <div><dt>启动 ID</dt><dd class="mono">{{ device.holderBootId ?? '未上报' }}</dd></div>
        <div><dt>原始心跳</dt><dd class="mono">{{ device.lastSeenAt ?? '未上报' }}</dd></div>
        <div><dt>执行判定</dt><dd>{{ device.executable === null ? '未上报' : String(device.executable) }}</dd></div>
        <div><dt>未满足门禁</dt><dd>{{ device.blockingGates === null ? '未上报' : device.blockingGates.join(' / ') || '空列表' }}</dd></div>
        <div><dt>已通过门禁</dt><dd>{{ device.executableGates.map(gateLabel).join(' / ') || '未上报通过项' }}</dd></div>
        <div><dt>已上报能力键</dt><dd>{{ device.capabilityKeys.join(' / ') || '未上报' }}</dd></div>
        <div v-if="device.currentTask"><dt>当前任务 ID</dt><dd class="mono">{{ device.currentTask.taskId }}</dd></div>
      </dl>
      <div class="fleet-card-section">
        <h4>能力表（{{ device.capabilities.length }}/6 键已回传）</h4>
        <div class="tag-list">
          <span v-for="capability in device.capabilities" :key="capability.key" class="tag" :class="capability.supported ? '' : 'tag-danger'">
            {{ capability.key }}{{ capability.supported ? '' : ' 不支持' }}{{ capability.engineMin != null ? ` · min ${capability.engineMin}` : '' }}
          </span>
        </div>
      </div>
    </details>
  </article>
</template>

<style scoped>
.fleet-card { min-width: 0; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; overflow-wrap: anywhere; }
.fleet-card-head { display: flex; align-items: flex-start; gap: 8px; }
.fleet-card-title { display: flex; flex: 1; flex-direction: column; min-width: 0; gap: 3px; }
.fleet-card-title strong { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.fleet-connection { flex-shrink: 0; }
.fleet-readiness { align-self: flex-start; }
.fleet-card-section h4 { margin: 0 0 6px; font-size: 12px; color: var(--muted); }
.fleet-gap { margin: 0; }
.fleet-facts { margin: 0; font-size: 12px; }
.fleet-facts > div { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 8px; padding: 4px 0; }
.fleet-facts dt { color: var(--muted); }
.fleet-facts dd { min-width: 0; margin: 0; font-variant-numeric: tabular-nums; }
.fleet-timezone { display: block; font-size: 10px; }
.fleet-technical { border-top: 1px solid var(--line); padding-top: 8px; font-size: 12px; }
.fleet-technical summary { cursor: pointer; color: var(--muted); }
.fleet-technical summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.fleet-technical[open] summary { margin-bottom: 8px; }
.fleet-task { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0; }
.fleet-task > * { min-width: 0; max-width: 100%; }
.fleet-task-failed { color: var(--bad); font-weight: 600; width: 100%; }
.chip-select { flex-shrink: 0; }
.chip-select input { width: 16px; height: 16px; accent-color: var(--accent); }
.tag-ok { background: #dcfce7; color: #15803d; }
.tag-warn { background: #fef9c3; color: #a16207; }
.tag-info { background: #eef7fb; color: var(--info); }
.tag-danger { background: #fee2e2; color: #b91c1c; }
</style>
