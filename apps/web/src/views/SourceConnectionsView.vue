<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import type {
  SourceConnectionResponse,
  SyncRunResponse,
  SyncErrorResponse,
} from '@cloudctl/api-contracts'
import { AlertCircle, Check, Clock, Database, RefreshCw, X } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import QueryState from '@/components/QueryState.vue'
import { controlApiConfigured, createControlApiClient } from '@/api/control'

const controlApi = createControlApiClient()
const selectedConnection = ref<string | null>(null)
const activeTab = ref<'runs' | 'errors'>('runs')
const showResolvedErrors = ref(false)

const connectionsQuery = useQuery({
  queryKey: ['source-connections'],
  queryFn: () => controlApi.listSourceConnections(),
  enabled: controlApiConfigured,
  refetchInterval: 30000,
})

const runsQuery = useQuery({
  queryKey: ['sync-runs', selectedConnection],
  queryFn: () => 
    selectedConnection.value 
      ? controlApi.listSyncRuns(selectedConnection.value)
      : Promise.resolve([]),
  enabled: computed(() => controlApiConfigured && selectedConnection.value !== null),
  refetchInterval: 10000,
})

const errorsQuery = useQuery({
  queryKey: ['sync-errors', selectedConnection, showResolvedErrors],
  queryFn: () =>
    selectedConnection.value
      ? controlApi.listSyncErrors(selectedConnection.value, {
          resolved: showResolvedErrors.value ? undefined : false,
        })
      : Promise.resolve([]),
  enabled: computed(() => controlApiConfigured && selectedConnection.value !== null),
  refetchInterval: 15000,
})

function selectConnection(connectionId: string) {
  selectedConnection.value = connectionId
  activeTab.value = 'runs'
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function connectionStatusIcon(status: string) {
  if (status === 'ACTIVE') return Check
  if (status === 'ERROR') return X
  if (status === 'TESTING') return Clock
  return Database
}

function connectionStatusClass(status: string): string {
  if (status === 'ACTIVE') return 'text-green-600'
  if (status === 'ERROR') return 'text-red-600'
  if (status === 'TESTING') return 'text-yellow-600'
  return 'text-gray-500'
}

function syncStatusClass(status: string): string {
  if (status === 'COMPLETED') return 'text-green-600'
  if (status === 'FAILED') return 'text-red-600'
  if (status === 'RUNNING') return 'text-blue-600'
  return 'text-gray-500'
}
</script>

<template>
  <div class="source-connections-view">
    <PageHeader title="数据源连接" subtitle="管理外部数据源同步" />

    <QueryState 
      :loading="connectionsQuery.isLoading.value"
      :error="connectionsQuery.error.value"
    >
      <div class="connections-layout">
        <div class="connections-list">
          <h3 class="section-title">连接列表</h3>
          <div 
            v-for="conn in connectionsQuery.data.value" 
            :key="conn.id"
            class="connection-card"
            :class="{ selected: selectedConnection === conn.id }"
            @click="selectConnection(conn.id)"
          >
            <div class="connection-header">
              <component 
                :is="connectionStatusIcon(conn.status)" 
                :size="16"
                :class="connectionStatusClass(conn.status)"
              />
              <span class="connection-name">{{ conn.connection_name }}</span>
            </div>
            <div class="connection-meta">
              <span class="meta-item">{{ conn.source_kind }}</span>
              <span class="meta-separator">·</span>
              <span class="meta-item">{{ conn.entity_kind }}</span>
            </div>
            <div v-if="conn.last_test_at" class="connection-test">
              <span class="test-time">{{ formatTimestamp(conn.last_test_at) }}</span>
              <span class="test-result">{{ conn.last_test_result }}</span>
            </div>
          </div>
          <div 
            v-if="!connectionsQuery.data.value?.length" 
            class="empty-state"
          >
            <Database :size="48" class="empty-icon" />
            <p>暂无数据源连接</p>
          </div>
        </div>

        <div v-if="selectedConnection" class="connection-detail">
          <div class="tabs">
            <button
              :class="{ active: activeTab === 'runs' }"
              @click="activeTab = 'runs'"
            >
              <RefreshCw :size="16" />同步记录
            </button>
            <button
              :class="{ active: activeTab === 'errors' }"
              @click="activeTab = 'errors'"
            >
              <AlertCircle :size="16" />同步错误
            </button>
          </div>

          <div v-if="activeTab === 'runs'" class="tab-content">
            <QueryState
              :loading="runsQuery.isLoading.value"
              :error="runsQuery.error.value"
            >
              <div class="runs-list">
                <div 
                  v-for="run in runsQuery.data.value" 
                  :key="run.id"
                  class="run-card"
                >
                  <div class="run-header">
                    <StatusBadge :status="run.status" />
                    <span class="run-mode">{{ run.run_mode === 'full' ? '全量' : '增量' }}</span>
                  </div>
                  <div class="run-stats">
                    <div class="stat">
                      <span class="stat-label">读取</span>
                      <span class="stat-value">{{ run.records_read }}</span>
                    </div>
                    <div class="stat">
                      <span class="stat-label">创建</span>
                      <span class="stat-value">{{ run.records_created }}</span>
                    </div>
                    <div class="stat">
                      <span class="stat-label">更新</span>
                      <span class="stat-value">{{ run.records_updated }}</span>
                    </div>
                    <div class="stat">
                      <span class="stat-label">失败</span>
                      <span 
                        class="stat-value"
                        :class="{ 'text-red-600': run.records_failed > 0 }"
                      >
                        {{ run.records_failed }}
                      </span>
                    </div>
                  </div>
                  <div class="run-time">
                    <span>开始: {{ formatTimestamp(run.started_at) }}</span>
                    <span v-if="run.completed_at">
                      完成: {{ formatTimestamp(run.completed_at) }}
                    </span>
                  </div>
                  <div v-if="run.error_summary" class="run-error">
                    {{ run.error_summary }}
                  </div>
                </div>
                <div v-if="!runsQuery.data.value?.length" class="empty-state">
                  <RefreshCw :size="48" class="empty-icon" />
                  <p>暂无同步记录</p>
                </div>
              </div>
            </QueryState>
          </div>

          <div v-if="activeTab === 'errors'" class="tab-content">
            <div class="error-controls">
              <label>
                <input 
                  v-model="showResolvedErrors" 
                  type="checkbox"
                >
                显示已解决错误
              </label>
            </div>
            <QueryState
              :loading="errorsQuery.isLoading.value"
              :error="errorsQuery.error.value"
            >
              <div class="errors-list">
                <div 
                  v-for="error in errorsQuery.data.value" 
                  :key="error.id"
                  class="error-card"
                  :class="{ resolved: error.resolved_at }"
                >
                  <div class="error-header">
                    <AlertCircle :size="16" class="error-icon" />
                    <span class="error-id">{{ error.external_id }}</span>
                    <span v-if="error.resolved_at" class="resolved-badge">
                      已解决
                    </span>
                  </div>
                  <div v-if="error.error_code" class="error-code">
                    {{ error.error_code }}
                  </div>
                  <div class="error-message">
                    {{ error.error_message }}
                  </div>
                  <div v-if="error.field_name" class="error-field">
                    字段: {{ error.field_name }}
                  </div>
                  <div class="error-meta">
                    <span>重试: {{ error.retry_count }} 次</span>
                    <span>发生时间: {{ formatTimestamp(error.created_at) }}</span>
                  </div>
                  <details class="error-snapshot">
                    <summary>查看记录快照</summary>
                    <pre>{{ JSON.stringify(error.record_snapshot, null, 2) }}</pre>
                  </details>
                </div>
                <div v-if="!errorsQuery.data.value?.length" class="empty-state">
                  <Check :size="48" class="empty-icon" />
                  <p>{{ showResolvedErrors ? '暂无错误记录' : '暂无未解决错误' }}</p>
                </div>
              </div>
            </QueryState>
          </div>
        </div>

        <div v-else class="connection-detail empty">
          <Database :size="64" class="placeholder-icon" />
          <p>请从左侧选择一个连接查看详情</p>
        </div>
      </div>
    </QueryState>
  </div>
</template>

<style scoped>
.source-connections-view {
  padding: 1.5rem;
  max-width: 1400px;
  margin: 0 auto;
}

.connections-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.connections-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.5rem;
}

.connection-card {
  padding: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}

.connection-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.connection-card.selected {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.connection-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.connection-name {
  font-weight: 600;
  color: #111827;
}

.connection-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.meta-separator {
  color: #d1d5db;
}

.connection-test {
  font-size: 0.75rem;
  color: #6b7280;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.test-result {
  color: #374151;
}

.connection-detail {
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}

.connection-detail.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: #9ca3af;
}

.placeholder-icon {
  margin-bottom: 1rem;
  color: #d1d5db;
}

.tabs {
  display: flex;
  border-bottom: 1px solid #e5e7eb;
  background-color: #f9fafb;
}

.tabs button {
  flex: 1;
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: none;
  background: none;
  cursor: pointer;
  color: #6b7280;
  font-weight: 500;
  transition: all 0.2s;
}

.tabs button:hover {
  background-color: #f3f4f6;
}

.tabs button.active {
  color: #3b82f6;
  border-bottom: 2px solid #3b82f6;
}

.tab-content {
  padding: 1.5rem;
}

.runs-list,
.errors-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.run-card,
.error-card {
  padding: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background-color: #fff;
}

.run-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.run-mode {
  font-size: 0.75rem;
  color: #6b7280;
  padding: 0.125rem 0.5rem;
  background-color: #f3f4f6;
  border-radius: 0.25rem;
}

.run-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.75rem;
  color: #6b7280;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #111827;
}

.run-time {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #6b7280;
}

.run-error {
  margin-top: 0.75rem;
  padding: 0.75rem;
  background-color: #fef2f2;
  border-left: 3px solid #ef4444;
  font-size: 0.875rem;
  color: #991b1b;
  border-radius: 0.25rem;
}

.error-controls {
  margin-bottom: 1rem;
  display: flex;
  gap: 1rem;
}

.error-controls label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #374151;
  cursor: pointer;
}

.error-card.resolved {
  opacity: 0.6;
}

.error-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.error-icon {
  color: #ef4444;
}

.error-id {
  font-weight: 600;
  color: #111827;
}

.resolved-badge {
  margin-left: auto;
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  background-color: #d1fae5;
  color: #065f46;
  border-radius: 0.25rem;
}

.error-code {
  font-family: monospace;
  font-size: 0.75rem;
  color: #ef4444;
  margin-bottom: 0.5rem;
}

.error-message {
  color: #374151;
  margin-bottom: 0.5rem;
}

.error-field {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.error-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.error-snapshot {
  margin-top: 0.5rem;
}

.error-snapshot summary {
  font-size: 0.875rem;
  color: #3b82f6;
  cursor: pointer;
  user-select: none;
}

.error-snapshot pre {
  margin-top: 0.5rem;
  padding: 0.75rem;
  background-color: #f3f4f6;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  overflow-x: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: #9ca3af;
}

.empty-icon {
  margin-bottom: 1rem;
  color: #d1d5db;
}
</style>
