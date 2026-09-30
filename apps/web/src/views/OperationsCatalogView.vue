<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import { isRetiredOperation, operationModules, operationPath } from '@/data/operations-catalog'
import { moduleDescriptions, operationPageStatus, pageStatusLabels, quickPaths, type PageStatus } from '@/data/operation-page-availability'

const search = ref('')
const status = ref<'all' | PageStatus>('all')
const directory = operationModules.map((module) => ({ ...module, operations: module.operations.filter((operation) => !isRetiredOperation(operation.id)) }))
const total = directory.reduce((count, module) => count + module.operations.length, 0)
const filteredModules = computed(() => directory.map((module) => ({ ...module,
  operations: module.operations.filter((operation) => {
    const text = [module.label, moduleDescriptions[module.id], operation.title, ...operation.pageProfile.fields.map((field) => field.label)].join(' ').toLowerCase()
    return text.includes(search.value.trim().toLowerCase()) && (status.value === 'all' || operationPageStatus(operation) === status.value)
  }),
})).filter((module) => module.operations.length))
const visibleCount = computed(() => filteredModules.value.reduce((count, module) => count + module.operations.length, 0))
</script>

<template>
  <PageHeader title="运营功能目录" :description="directory.length + ' 个业务模块 · ' + total + ' 个目录入口。从设备准备开始，整理内容、发布任务，再查看结果。'" />
  <nav class="catalog-quick-paths" aria-label="常用操作链路">
    <RouterLink v-for="(item, index) in quickPaths" :key="item.to" :to="item.to">
      <span class="cell-sub">{{ index + 1 }}</span><strong>{{ item.title }}</strong><small>{{ item.description }}</small>
    </RouterLink>
  </nav>
  <p class="catalog-status-note">页面接入状态仅说明当前页面形式，不代表执行权限、设备就绪或任务可运行。<RouterLink to="/im">进入消息聚合</RouterLink></p>
  <div class="filter-bar operations-catalog-filter">
    <label class="catalog-search"><Search :size="15" /><input v-model="search" aria-label="搜索运营功能" placeholder="搜索模块、功能或配置字段" /></label>
    <label class="catalog-status-select">页面状态 <select v-model="status" aria-label="筛选页面接入状态"><option value="all">全部状态</option><option v-for="(label, value) in pageStatusLabels" :key="value" :value="value">{{ label }}</option></select></label>
    <span class="filter-spacer" /><span class="cell-sub" role="status">{{ visibleCount }} / {{ total }} 项</span>
  </div>
  <div class="operations-module-grid">
    <section v-for="module in filteredModules" :key="module.id" class="operation-module-card">
      <header><div><span>{{ module.stage }}</span><h3>{{ module.label }}</h3><p class="catalog-module-description">{{ moduleDescriptions[module.id] }}</p></div><strong>{{ module.operations.length }}</strong></header>
      <div class="operation-link-list">
        <RouterLink v-for="operation in module.operations" :key="operation.id" :to="operationPath(operation)">
          <span class="operation-link-copy"><span class="operation-link-title">{{ operation.title }}</span></span>
          <span class="catalog-page-status" :class="'status-' + operationPageStatus(operation)">{{ pageStatusLabels[operationPageStatus(operation)] }}</span>
        </RouterLink>
      </div>
    </section>
  </div>
  <div v-if="!filteredModules.length" class="panel query-state"><Search :size="22" /><span>没有符合当前筛选的功能</span><button class="button" @click="search = ''; status = 'all'">清除筛选</button></div>
</template>

<style scoped>
.catalog-quick-paths { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.catalog-quick-paths a { display: grid; gap: 6px; padding: 14px; background: var(--panel, #fff); border: 1px solid var(--yy-line, #d8dee6); border-radius: 8px; color: inherit; text-decoration: none; min-width: 0; }
.catalog-quick-paths small, .catalog-module-description, .catalog-status-note { color: var(--text-muted, #64748b); font-size: 12px; line-height: 1.6; }
.catalog-status-note a { margin-left: 8px; }
.catalog-module-description { margin: 5px 0 0; }
.catalog-status-select { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.catalog-status-select select { padding: 7px; border: 1px solid var(--yy-line, #d8dee6); border-radius: 5px; background: white; }
.catalog-page-status { flex-shrink: 0; font-size: 11px; color: #64748b; }
.status-dedicated { color: #0f766e; }
.operation-link-copy { min-width: 0; overflow-wrap: anywhere; }
.operation-link-title { white-space: normal; }
@media (max-width: 1000px) { .catalog-quick-paths { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 600px) { .catalog-quick-paths { grid-template-columns: repeat(2, minmax(0, 1fr)); } .operations-module-grid { grid-template-columns: minmax(0, 1fr); } .catalog-search { min-width: 0; width: 100%; } }
</style>
