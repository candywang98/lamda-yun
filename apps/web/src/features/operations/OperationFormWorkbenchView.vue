<script setup lang="ts">
import { computed, onMounted, reactive, ref, watchEffect } from 'vue'
import { ClipboardCheck, ListChecks, Send } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { controlApiConfigured, operationsMockEnabled } from '@/api/control'
import { operationsCatalog } from '@/data/operations-catalog'
import type { OperationDefinition } from '@/data/operations-catalog'
import type { JsonObject, OperationTask } from '@cloudctl/api-contracts'
import BusinessOperationSnapshot from './BusinessOperationSnapshot.vue'
import {
  canonicalOperationRequestHash,
  freezeBusinessOperationRequest,
  resolveBusinessOperationAvailability,
  type BusinessOperationRequestSnapshot,
} from './business-operation'
import {
  fetchOperationTaskDetail,
  loadOperationDirectory,
  mintBusinessOperation,
  operationsUnconfiguredMessage,
  unavailableDirectory,
} from './api'

const directory = ref(unavailableDirectory(controlApiConfigured ? 'connecting' : operationsMockEnabled ? 'mock' : 'unavailable'))
const directoryError = ref('')
const selectedId = ref('')
const formError = ref('')
const requestHash = ref('')
const submitting = ref(false)
const mintResult = ref<OperationTask | null>(null)
const mintError = ref('')
const hashMatch = ref<boolean | null>(null)

const form = reactive({
  resourceIdsText: '',
  executionApp: '',
  deviceScope: '',
  schedule: 'immediate',
  pageValues: {} as Record<string, string | number | boolean>,
})

const selectable = computed(() => operationsCatalog)
const operation = computed<OperationDefinition | null>(
  () => operationsCatalog.find((item) => item.id === selectedId.value) ?? null,
)
const catalogEntry = computed(() => {
  const key = operation.value?.backendOperationKey
  if (!key) return null
  return directory.value.catalogs.find((entry) => entry.key === key) ?? null
})
const featureEntry = computed(() => {
  const current = operation.value
  if (!current) return null
  return directory.value.features.find((entry) => entry.featureId === current.id) ?? null
})
const availability = computed(() =>
  operation.value
    ? resolveBusinessOperationAvailability({
        operation: operation.value,
        connection: directory.value.connection,
        catalog: catalogEntry.value ?? undefined,
        feature: featureEntry.value ?? undefined,
      })
    : { state: 'PENDING' as const, reason: '先选择一个业务功能', canMint: false },
)

const resourceIds = computed(() =>
  form.resourceIdsText
    .split(/[\n,，;；\s]+/)
    .map((value) => value.trim())
    .filter(Boolean),
)

const snapshot = ref<BusinessOperationRequestSnapshot | null>(null)

watchEffect(() => {
  const current = operation.value
  formError.value = ''
  snapshot.value = null
  requestHash.value = ''
  if (!current) return
  for (const field of current.pageProfile.fields) {
    if (!(field.id in form.pageValues)) form.pageValues[field.id] = field.defaultValue
  }
  if (!form.executionApp) form.executionApp = 'com.taobao.idlefish'
  if (!form.deviceScope) form.deviceScope = ''
  if (resourceIds.value.length === 0) {
    formError.value = '至少填写一个资源 ID（商品 / 目标）'
    return
  }
  if (!catalogEntry.value) {
    formError.value =
      directory.value.connection === 'live'
        ? '后端操作目录未返回该 operationKey，不能构造提交快照'
        : '等待 Control API 操作目录确认后才能冻结快照'
    return
  }
  try {
    snapshot.value = freezeBusinessOperationRequest({
      operation: current,
      catalog: catalogEntry.value,
      pageParameters: { ...form.pageValues },
      resourceIds: resourceIds.value,
      context: {
        deviceScope: form.deviceScope || '未指定设备',
        executionApp: form.executionApp,
        schedule: form.schedule,
        snapshot: current.pageProfile.key,
        reason: current.pageProfile.purpose,
        source: 'web',
        mode: current.mode,
        sourcePage: current.sourcePage,
        sourceRoute: current.sourceRoute,
      },
    })
  } catch (error) {
    formError.value = error instanceof Error ? error.message : String(error)
  }
})

watchEffect(() => {
  const current = snapshot.value
  if (!current) return
  canonicalOperationRequestHash(current).then((hash) => {
    requestHash.value = hash
  })
})

const snapshotReady = computed(() => snapshot.value !== null)
const canSubmit = computed(
  () => snapshotReady.value && requestHash.value.length > 0 && availability.value.canMint && !submitting.value,
)

onMounted(async () => {
  if (!controlApiConfigured) return
  try {
    directory.value = await loadOperationDirectory()
  } catch (error) {
    directoryError.value = error instanceof Error ? error.message : String(error)
    directory.value = unavailableDirectory('unavailable')
  }
})

async function submit() {
  if (!canSubmit.value) return
  const current = JSON.parse(JSON.stringify(snapshot.value)) as BusinessOperationRequestSnapshot
  submitting.value = true
  mintError.value = ''
  hashMatch.value = null
  try {
    const request: Parameters<typeof mintBusinessOperation>[0] = {
      operationKey: current.operationKey,
      featureId: current.featureId,
      resourceIds: [...current.resourceIds],
      parameters: JSON.parse(JSON.stringify(current.parameters)) as JsonObject,
      context: JSON.parse(JSON.stringify(current.context)) as JsonObject,
      batch: current.batch,
      idempotencyKey: crypto.randomUUID(),
    }
    const task = await mintBusinessOperation(request)
    const detail = await fetchOperationTaskDetail(task.id).catch(() => task)
    mintResult.value = detail
    hashMatch.value = detail.requestSha256 === requestHash.value
  } catch (error) {
    mintError.value = error instanceof Error ? error.message : String(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="operation-forms">
    <PageHeader
      kicker="F13 / 业务表单薄层"
      title="业务操作表单"
      description="表单由 operation catalog 生成，提交快照冻结并显示六字段哈希；不可用能力只显示原因，绝不铸造任务。"
    >
      <template #actions>
        <StatusBadge
          :status="directory.connection === 'live' ? 'ONLINE' : directory.connection === 'mock' ? 'CANDIDATE' : 'BLOCKED'"
          :label="{ live: 'Control API 已连接', mock: 'Mock 模式（只读展示）', connecting: '正在连接 Control API', unavailable: 'Control API 不可用' }[directory.connection]"
        />
      </template>
    </PageHeader>

    <p v-if="directoryError" class="alert" role="alert">{{ directoryError }}</p>
    <p v-if="!controlApiConfigured" class="alert" role="alert">{{ operationsUnconfiguredMessage() }}</p>

    <div class="workbench-grid">
      <section class="panel">
        <header><ListChecks :size="18" /><h3>选择业务功能</h3></header>
        <label>功能
          <select v-model="selectedId">
            <option value="" disabled>请选择</option>
            <option v-for="item in selectable" :key="item.id" :value="item.id">
              {{ item.moduleLabel }} · {{ item.title }}
            </option>
          </select>
        </label>
        <p v-if="operation" class="hint">
          {{ operation.pageProfile.purpose }}（{{ operation.pageProfile.category }}）
        </p>
        <label>资源 ID（商品 / 目标，多个用换行或逗号分隔）
          <textarea v-model="form.resourceIdsText" rows="3" placeholder="每行一个资源 ID" />
        </label>
        <div class="field-pair">
          <label>执行应用<input v-model="form.executionApp" /></label>
          <label>定时<input v-model="form.schedule" /></label>
        </div>
        <label>设备范围<input v-model="form.deviceScope" placeholder="设备 ID 或范围说明" /></label>
        <template v-if="operation">
          <label v-for="field in operation.pageProfile.fields" :key="field.id">
            {{ field.label }}
            <select v-if="field.control === 'select'" v-model="form.pageValues[field.id]">
              <option v-for="option in field.options ?? []" :key="option" :value="option">{{ option }}</option>
            </select>
            <input
              v-else-if="field.control === 'toggle'"
              type="checkbox"
              :checked="Boolean(form.pageValues[field.id])"
              @change="form.pageValues[field.id] = ($event.target as HTMLInputElement).checked"
            />
            <input
              v-else-if="field.control === 'number'"
              type="number"
              :value="Number(form.pageValues[field.id])"
              @input="form.pageValues[field.id] = Number(($event.target as HTMLInputElement).value)"
            />
            <input v-else v-model="form.pageValues[field.id]" :placeholder="field.placeholder" />
          </label>
        </template>
        <p v-if="formError" class="hint error">{{ formError }}</p>
        <button type="button" class="primary" :disabled="!canSubmit" @click="submit">
          <Send :size="16" />{{ availability.canMint ? '提交业务操作' : '不可提交（' + availability.state + '）' }}
        </button>
      </section>

      <section class="panel">
        <header><ClipboardCheck :size="18" /><h3>冻结快照与可用性</h3></header>
        <BusinessOperationSnapshot
          :availability="availability"
          :snapshot="snapshot"
          :request-hash="requestHash"
          :title="operation?.title ?? ''"
          :module-label="operation?.moduleLabel ?? ''"
        />
      </section>
    </div>

    <section v-if="mintResult" class="result-band">
      <div class="result-heading">
        <h3>提交结果</h3>
        <StatusBadge :status="mintResult.status" />
        <span v-if="hashMatch !== null" class="hint" :class="{ ok: hashMatch }">
          {{ hashMatch ? '服务端 requestSha256 与页面哈希一致' : '哈希不一致，请勿重试，先核对快照' }}
        </span>
      </div>
      <p class="mono checksum">task {{ mintResult.id }} · {{ mintResult.totalCount }} 目标 · 成功 {{ mintResult.succeededCount }} / 失败 {{ mintResult.failedCount }} / 阻断 {{ mintResult.blockedCount }}</p>
      <table v-if="mintResult.items?.length" class="row-table">
        <thead><tr><th>资源 / 目标</th><th>状态</th><th>错误码</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="item in mintResult.items" :key="item.id">
            <td class="mono">{{ item.resourceId }}</td>
            <td><StatusBadge :status="item.status" /></td>
            <td class="mono">{{ item.errorCode ?? '—' }}</td>
            <td>{{ item.detail ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <p v-if="mintError" class="alert" role="alert">{{ mintError }}</p>
  </section>
</template>

<style scoped>
.operation-forms { display: grid; gap: 16px; color: #24313d; }
.alert { margin: 0; padding: 10px 12px; border-left: 3px solid #b42318; background: #fff3f2; color: #8a1c13; font-size: 13px; }
.workbench-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: start; }
.panel { min-width: 0; padding: 14px; border: 1px solid #dce3e8; border-radius: 6px; background: #fff; display: grid; gap: 12px; align-content: start; }
.panel header, .result-heading { display: flex; align-items: center; gap: 8px; min-height: 28px; }
h3 { margin: 0; font-size: 14px; color: #17232c; }
label { display: grid; gap: 5px; color: #60717e; font-size: 12px; }
input, select, textarea { width: 100%; min-width: 0; box-sizing: border-box; padding: 7px 9px; border: 1px solid #cbd5dc; border-radius: 4px; background: #fff; color: #17232c; font: inherit; font-size: 13px; }
input[type='checkbox'] { width: auto; justify-self: start; }
textarea { resize: vertical; }
.field-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
button.primary { height: 36px; padding: 0 12px; border: 0; border-radius: 4px; background: #116466; color: #fff; display: inline-flex; justify-content: center; align-items: center; gap: 7px; font: inherit; cursor: pointer; }
button.primary:disabled { cursor: not-allowed; opacity: .5; }
.hint { margin: 0; color: #71818d; font-size: 12px; }
.hint.error { color: #8a1c13; }
.hint.ok { color: #116434; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.checksum { overflow-wrap: anywhere; color: #475866; }
.result-band { padding: 14px; border-top: 1px solid #dce3e8; background: #f8fafb; display: grid; gap: 10px; }
.result-heading { flex-wrap: wrap; }
.row-table { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }
.row-table th { text-align: left; padding: 7px 8px; border-bottom: 1px solid #dce3e8; color: #60717e; }
.row-table td { padding: 7px 8px; border-bottom: 1px solid #e4e9ed; vertical-align: top; }
@media (max-width: 1050px) { .workbench-grid { grid-template-columns: 1fr; } }
</style>
