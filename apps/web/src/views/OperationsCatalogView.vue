<script setup lang="ts">
import { computed, ref } from 'vue'
import { LayoutGrid, Route, Search, ShieldAlert, Workflow } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import MetricCard from '@/components/MetricCard.vue'
import { firstOperationPath, isRetiredOperation, operationModules, operationPath, operationsCatalog, riskLabel, type OperationRisk } from '@/data/operations-catalog'

const search = ref('')
const risk = ref<'all' | OperationRisk>('all')
const stage = ref<'all' | (typeof operationModules)[number]['stage']>('all')
const stages = ['资产准备', '内容生产', '分发执行', '互动交易', '数据复盘'] as const

const uniqueRouteCount = new Set(operationsCatalog.map((operation) => operation.sourceRoute)).size
const riskCounts = {
  standard: operationsCatalog.filter((operation) => operation.risk === 'standard').length,
  approval: operationsCatalog.filter((operation) => operation.risk === 'approval').length,
  blocked: operationsCatalog.filter((operation) => operation.risk === 'blocked').length,
}

const filteredModules = computed(() => operationModules.map((module) => ({
  ...module,
  operations: module.operations.filter((operation) => {
    const profileFields = operation.pageProfile.fields.map((field) => field.label).join(' ')
    const haystack = `${module.label}${operation.title}${operation.description}${operation.sourceRoute}${operation.sourceSummary}${operation.pageProfile.category}${profileFields}`.toLowerCase()
    if (isRetiredOperation(operation.id)) return false
    const matchesSearch = haystack.includes(search.value.trim().toLowerCase())
    const matchesRisk = risk.value === 'all' || operation.risk === risk.value
    const matchesStage = stage.value === 'all' || module.stage === stage.value
    return matchesSearch && matchesRisk && matchesStage
  }),
})).filter((module) => module.operations.length > 0))

const visibleCount = computed(() => filteredModules.value.reduce((count, module) => count + module.operations.length, 0))
</script>

<template>
  <PageHeader title="运营功能目录" description="15 个业务模块、134 个菜单入口。采集 → 编辑 → 发布 → 聊天 → 订单 → 复盘；执行走授权设备与 Control API。" />

  <div class="metrics-grid operations-catalog-metrics">
    <MetricCard label="业务模块" :value="String(operationModules.length)" detail="侧栏按竞品 15 组展开，点模块进入对应功能" tone="good" :icon="LayoutGrid" />
    <MetricCard label="菜单入口" :value="String(operationsCatalog.length)" detail="一项一页，重复路由仍按独立入口收录" :icon="Workflow" />
    <MetricCard label="原始页面路由" :value="String(uniqueRouteCount)" detail="来自竞品调研截图中的真实前端路由" :icon="Route" />
    <MetricCard label="风险分层" :value="`${riskCounts.blocked}`" :detail="`可模拟 ${riskCounts.standard} · 需审批 ${riskCounts.approval} · 策略阻断 ${riskCounts.blocked}`" tone="warn" :icon="ShieldAlert" />
  </div>

  <div class="filter-bar operations-catalog-filter">
    <label class="catalog-search"><Search :size="15" /><input v-model="search" aria-label="搜索运营功能" placeholder="搜索模块、功能、原始路由或页面字段" /></label>
    <div class="segmented-control" aria-label="链路筛选">
      <button :class="{ active: stage === 'all' }" @click="stage = 'all'">全部链路</button>
      <button v-for="item in stages" :key="item" :class="{ active: stage === item }" @click="stage = item">{{ item }}</button>
    </div>
    <div class="segmented-control" aria-label="风险筛选">
      <button v-for="item in [{ value: 'all', label: '全部' }, { value: 'standard', label: '可模拟' }, { value: 'approval', label: '需审批' }, { value: 'blocked', label: '策略阻断' }]" :key="item.value" :class="{ active: risk === item.value }" @click="risk = item.value as typeof risk">{{ item.label }}</button>
    </div>
    <span class="filter-spacer" /><span class="cell-sub">{{ visibleCount }} / {{ operationsCatalog.length }} 项</span>
  </div>

  <div class="operations-module-grid">
    <section v-for="module in filteredModules" :key="module.id" class="operation-module-card">
      <header>
        <RouterLink :to="firstOperationPath(module)">
          <span>{{ module.stage }}</span>
          <h3>{{ module.label }}</h3>
        </RouterLink>
        <strong>{{ module.operations.length }} / {{ module.titles.length }}</strong>
      </header>
      <div class="operation-link-list">
        <RouterLink v-for="operation in module.operations" :key="operation.id" :to="operationPath(operation)">
          <span class="operation-sequence">{{ String(operation.index).padStart(3, '0') }}</span>
          <span class="operation-link-copy">
            <span class="operation-link-title">{{ operation.title }}</span>
            <small>{{ operation.sourceRoute }}</small>
          </span>
          <span class="catalog-risk" :class="`risk-${operation.risk}`">{{ riskLabel(operation.risk) }}</span>
        </RouterLink>
      </div>
    </section>
  </div>

  <div v-if="filteredModules.length === 0" class="panel query-state"><Search :size="22" /><span>没有符合当前筛选的功能</span><button class="button" @click="search = ''; risk = 'all'; stage = 'all'">清除筛选</button></div>

  <div class="notice operations-source-note">
    <div>
      <strong>原始页面路由对照竞品登录后可见菜单</strong>
      <p>同一路由若从不同菜单出现，仍按独立入口收录。采集、养号、鱼币等能力保留页面规格，生产策略保持阻断；可执行入口走 LAMDA Control API。</p>
    </div>
  </div>
</template>
