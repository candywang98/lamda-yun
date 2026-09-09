<script setup lang="ts">
import { computed, ref, watch } from 'vue'

export type ScheduleKind = 'IMMEDIATE' | 'ONCE' | 'RECURRING'
export type MissPolicy = 'QUEUE_ONE' | 'SKIP'

export interface ScheduleDraft {
  kind: ScheduleKind
  timezone: string
  onceAt: string
  rrule: string
  missPolicy: MissPolicy
  startDeadlineMinutes: number
}

const props = withDefaults(
  defineProps<{
    accountLabel?: string
    deviceCount?: number
    templateVersion?: string
    waitingUser?: boolean
    offlineQueued?: boolean
  }>(),
  {
    accountLabel: '',
    deviceCount: 1,
    templateVersion: '1',
    waitingUser: false,
    offlineQueued: false,
  },
)

const model = defineModel<ScheduleDraft>({
  default: () => ({
    kind: 'IMMEDIATE',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
    onceAt: '',
    rrule: 'FREQ=DAILY;INTERVAL=1',
    missPolicy: 'QUEUE_ONE',
    startDeadlineMinutes: 30,
  }),
})

const error = ref('')

const nextOccurrences = computed(() => {
  if (model.value.kind !== 'RECURRING' || !model.value.rrule.startsWith('FREQ=')) return []
  const now = Date.now()
  const stepMs = model.value.rrule.includes('HOURLY') ? 60 * 60 * 1000 : 24 * 60 * 60 * 1000
  return [1, 2, 3].map((index) => new Date(now + index * stepMs).toISOString())
})

function validate(): boolean {
  error.value = ''
  if (model.value.kind === 'ONCE') {
    if (!model.value.onceAt) {
      error.value = '预约时间不能为空'
      return false
    }
    if (new Date(model.value.onceAt).getTime() <= Date.now()) {
      error.value = '预约时间必须是未来时间'
      return false
    }
  }
  if (model.value.kind === 'RECURRING' && !model.value.rrule.startsWith('FREQ=')) {
    error.value = '周期规则必须以 FREQ= 开头'
    return false
  }
  return true
}

watch(
  () => [model.value.kind, model.value.onceAt, model.value.rrule],
  () => {
    if (error.value) validate()
  },
)

defineExpose({ validate, nextOccurrences })
</script>

<template>
  <section class="schedule-editor" data-testid="schedule-editor">
    <label>
      执行方式
      <select v-model="model.kind" data-testid="schedule-kind">
        <option value="IMMEDIATE">立即</option>
        <option value="ONCE">预约一次</option>
        <option value="RECURRING">周期</option>
      </select>
    </label>
    <label>
      时区
      <input v-model="model.timezone" data-testid="schedule-timezone" />
    </label>
    <label v-if="model.kind === 'ONCE'">
      预约时间
      <input v-model="model.onceAt" type="datetime-local" data-testid="schedule-once-at" />
    </label>
    <label v-if="model.kind === 'RECURRING'">
      RRULE
      <input v-model="model.rrule" data-testid="schedule-rrule" />
    </label>
    <p>账号：{{ accountLabel || '未选择' }}</p>
    <p>设备数：{{ deviceCount }}（批量只是便捷创建独立任务，没有优先级）</p>
    <p>模板版本：{{ templateVersion }}</p>
    <p>错过触发：{{ model.missPolicy === 'QUEUE_ONE' ? '只补最新一期' : '跳过' }}</p>
    <p>发布过期窗口：到点后 {{ model.startDeadlineMinutes }} 分钟</p>
    <p v-if="offlineQueued">离线设备会进入排队，不会被当成等待人工。</p>
    <p v-if="waitingUser">等待人工与离线排队不是同一状态。</p>
    <ul v-if="model.kind === 'RECURRING'" data-testid="schedule-next">
      <li v-for="item in nextOccurrences" :key="item">{{ item }}</li>
    </ul>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
