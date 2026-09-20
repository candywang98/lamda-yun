<script setup lang="ts">
import { computed } from 'vue'
import type { AvailabilityResult, BusinessOperationRequestSnapshot } from './business-operation'

const props = defineProps<{
  availability: AvailabilityResult
  snapshot: Readonly<BusinessOperationRequestSnapshot> | null
  requestHash: string
  title: string
  moduleLabel: string
}>()

const parameterCount = computed(() => {
  const page = props.snapshot?.parameters.pageParameters
  return page && typeof page === 'object' && !Array.isArray(page) ? Object.keys(page).length : 0
})

const budget = computed(() => {
  const page = props.snapshot?.parameters.pageParameters
  if (!page || typeof page !== 'object' || Array.isArray(page)) return '未设置'
  const item = Object.entries(page).find(([key]) => /budget|price|cost|amount|预算|价格/i.test(key))
  return item ? String(item[1]) : '未设置'
})
</script>

<template>
  <div class="business-operation-snapshot" data-testid="business-operation-snapshot">
    <div class="notice" :class="availability.state === 'ENABLED' ? 'notice-info' : 'notice-danger'" role="status">
      <div>
        <strong>{{ availability.state }}</strong>
        <p>{{ availability.reason }}</p>
      </div>
    </div>
    <ul v-if="snapshot" class="preview-list">
      <li><span>平台 / 模块</span><strong>{{ moduleLabel }}</strong></li>
      <li><span>商品 / 目标</span><strong class="mono">{{ snapshot.resourceIds.join(', ') }}</strong></li>
      <li><span>账号 / 应用</span><strong>{{ snapshot.context.executionApp }}</strong></li>
      <li><span>设备范围</span><strong>{{ snapshot.context.deviceScope }}</strong></li>
      <li><span>业务字段</span><strong>{{ title }} · {{ parameterCount }} 项</strong></li>
      <li><span>预算 / 价格</span><strong>{{ budget }}</strong></li>
      <li><span>定时</span><strong>{{ snapshot.context.schedule }}</strong></li>
      <li><span>operationKey</span><strong class="mono">{{ snapshot.operationKey }}</strong></li>
      <li><span>featureId</span><strong class="mono">{{ snapshot.featureId }}</strong></li>
      <li><span>resourceIds</span><strong class="mono">{{ JSON.stringify(snapshot.resourceIds) }}</strong></li>
      <li><span>parameters</span><strong class="mono">{{ JSON.stringify(snapshot.parameters) }}</strong></li>
      <li><span>context</span><strong class="mono">{{ JSON.stringify(snapshot.context) }}</strong></li>
      <li><span>batch</span><strong class="mono">{{ snapshot.batch }}</strong></li>
      <li><span>requestSha256</span><strong class="mono">{{ requestHash || '计算中' }}</strong></li>
    </ul>
  </div>
</template>
