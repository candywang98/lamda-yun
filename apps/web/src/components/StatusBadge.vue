<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, Check, Circle, CircleDashed, Clock3, Pause, X } from 'lucide-vue-next'
import type { Status } from '@/types'

const props = defineProps<{ status: Status | string; label?: string }>()
const labels: Record<string, string> = {
  ONLINE: '在线', OFFLINE: '离线', MAINTENANCE: '维护中', PENDING_APPROVAL: '待审批', APPROVED: '已审批', QUEUED: '排队中', RUNNING: '运行中', SUCCEEDED: '成功', PARTIAL: '部分成功', FAILED: '失败', UNKNOWN: '结果未知', CANCELED: '已取消', PAUSED: '已暂停', BLOCKED: '已阻断', SUPPORTED: '支持', CANDIDATE: '候选',
}
const icon = computed(() => {
  if (['SUCCEEDED', 'ONLINE', 'APPROVED', 'SUPPORTED'].includes(props.status)) return Check
  if (props.status === 'UNKNOWN') return AlertTriangle
  if (['FAILED', 'OFFLINE', 'BLOCKED'].includes(props.status)) return X
  if (props.status === 'CANCELED') return Circle
  if (props.status === 'PAUSED') return Pause
  if (['PENDING_APPROVAL', 'QUEUED'].includes(props.status)) return Clock3
  return CircleDashed
})
const tone = computed(() => props.status.toLowerCase().replace('_', '-'))
</script>

<template>
  <span class="status-badge" :class="`status-${tone}`" :data-status="status">
    <component :is="icon" :size="12" />{{ label ?? labels[status] ?? status }}
  </span>
</template>
