<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ArrowDownToLine, FileInput, History } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { controlApiConfigured } from '@/api/control'
import {
  downloadProductCsv,
  fetchProductRevisions,
  runContentImport,
  type ContentImportResult,
  type RevisionHistory,
} from './api'
import { parseImportPayload, rowErrorText, rowStatusLabel, rowStatusTone } from './model'

const busy = ref<'import' | 'export' | 'revisions' | null>(null)
const errorMessage = ref('')
const importResult = ref<ContentImportResult | null>(null)
const exportNote = ref('')
const history = ref<RevisionHistory | null>(null)
const historyOffset = ref(0)

const importer = reactive({
  payload: '',
  importKey: '',
  confirmed: false,
})
const revisions = reactive({ productId: '' })
const HISTORY_LIMIT = 10

async function execute<T>(request: 'import' | 'export' | 'revisions', action: () => Promise<T>) {
  busy.value = request
  errorMessage.value = ''
  try {
    return await action()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
    return null
  } finally {
    busy.value = null
  }
}

async function submitImport(apply: boolean) {
  let items
  try {
    items = parseImportPayload(importer.payload)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
    return
  }
  if (apply && !importer.confirmed) {
    errorMessage.value = '请先勾选「我确认写入」再执行导入'
    return
  }
  const result = await execute('import', () =>
    runContentImport(items, {
      apply,
      ...(importer.importKey.trim() ? { importKey: importer.importKey.trim() } : {}),
    }),
  )
  if (result) importResult.value = result
}

async function submitExport() {
  const result = await execute('export', () => downloadProductCsv())
  if (result) exportNote.value = `已导出 ${result.rowCount} 行 → ${result.fileName}（公式注入已转义）`
}

async function loadRevisions(offset: number) {
  const productId = revisions.productId.trim()
  if (!productId) {
    errorMessage.value = '商品 ID 不能为空'
    return
  }
  const result = await execute('revisions', () =>
    fetchProductRevisions(productId, HISTORY_LIMIT, offset),
  )
  if (result) {
    history.value = result
    historyOffset.value = offset
  }
}
</script>

<template>
  <section class="content-io">
    <PageHeader
      kicker="F11 / 内容导入导出"
      title="导入导出与修订历史"
      description="默认只验证不写库；显式确认才导入；修订历史只读且不可被后续编辑改写。"
    >
      <template #actions>
        <StatusBadge
          :status="controlApiConfigured ? 'ONLINE' : 'BLOCKED'"
          :label="controlApiConfigured ? 'Control API 已连接' : 'Control API 未配置'"
        />
      </template>
    </PageHeader>

    <p v-if="errorMessage" class="alert" role="alert">{{ errorMessage }}</p>

    <div class="panel-grid">
      <section class="panel">
        <header><FileInput :size="18" /><h3>商品导入</h3></header>
        <label>JSON 行（每行一个商品，最多 100 行）
          <textarea v-model="importer.payload" rows="8" spellcheck="false" :placeholder="'[{&quot;spuCode&quot;:&quot;A-1&quot;,&quot;title&quot;:&quot;商品&quot;,&quot;category&quot;:&quot;home&quot;,&quot;price&quot;:&quot;19.90&quot;,&quot;stock&quot;:3}]'" />
        </label>
        <label>导入幂等键（可选，重复提交同一键会重放首次结果）<input v-model="importer.importKey" autocomplete="off" /></label>
        <label class="confirm"><input v-model="importer.confirmed" type="checkbox" />我确认写入（apply=true 时必勾）</label>
        <div class="actions">
          <button type="button" :disabled="!controlApiConfigured || busy === 'import'" @click="submitImport(false)">
            <FileInput :size="16" />验证（不写库）
          </button>
          <button type="button" class="primary" :disabled="!controlApiConfigured || busy === 'import' || !importer.confirmed" @click="submitImport(true)">
            <FileInput :size="16" />确认导入
          </button>
        </div>
      </section>

      <section class="panel">
        <header><ArrowDownToLine :size="18" /><h3>CSV 导出</h3></header>
        <p class="hint">导出本租户全部商品；以 = + - @ 或制表符开头的单元格会加单引号转义，防止表格公式注入。</p>
        <button type="button" :disabled="!controlApiConfigured || busy === 'export'" @click="submitExport">
          <ArrowDownToLine :size="16" />导出 products.csv
        </button>
        <p v-if="exportNote" class="hint">{{ exportNote }}</p>
      </section>

      <section class="panel">
        <header><History :size="18" /><h3>修订历史</h3></header>
        <label>商品 ID<input v-model="revisions.productId" autocomplete="off" /></label>
        <button type="button" :disabled="!controlApiConfigured || busy === 'revisions'" @click="loadRevisions(0)">
          <History :size="16" />查询修订
        </button>
      </section>
    </div>

    <section v-if="importResult" class="result-band">
      <div class="result-heading">
        <h3>{{ importResult.mode === 'APPLY' ? '导入结果' : '验证结果（未写库）' }}</h3>
        <StatusBadge v-if="importResult.replayed" status="CANDIDATE" label="幂等重放" />
      </div>
      <p class="summary-line">
        <span>共 {{ importResult.summary.total }} 行</span>
        <span>将导入 {{ importResult.summary.importCount }}</span>
        <span>跳过已存在 {{ importResult.summary.skipExistingCount }}</span>
        <span>错误 {{ importResult.summary.errorCount }}</span>
      </p>
      <p class="hint">{{ importResult.policy }}</p>
      <p class="mono checksum">importKey {{ importResult.importKey }}</p>
      <table class="row-table">
        <thead><tr><th>#</th><th>spuCode</th><th>标题</th><th>状态</th><th>错误</th></tr></thead>
        <tbody>
          <tr v-for="row in importResult.rows" :key="row.index">
            <td>{{ row.index + 1 }}</td>
            <td class="mono">{{ row.spuCode }}</td>
            <td class="cell-title">{{ row.title }}</td>
            <td><StatusBadge :status="rowStatusTone(row.status)" :label="rowStatusLabel(row.status)" /></td>
            <td>{{ rowErrorText(row) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="history" class="result-band">
      <div class="result-heading">
        <h3>修订历史（不可变）</h3>
        <span class="hint">当前修订 v{{ history.currentRevision }} · 共 {{ history.total }} 条</span>
      </div>
      <table class="row-table">
        <thead><tr><th>动作</th><th>修订</th><th>时间</th><th>操作者</th><th>afterHash</th></tr></thead>
        <tbody>
          <tr v-for="entry in history.items" :key="entry.eventId">
            <td class="mono">{{ entry.action }}</td>
            <td>{{ entry.revision ?? '—' }}</td>
            <td>{{ entry.occurredAt ?? '—' }}</td>
            <td class="mono">{{ entry.actorId }}</td>
            <td class="mono checksum">{{ entry.afterHash ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div class="actions">
        <button type="button" :disabled="historyOffset <= 0 || busy === 'revisions'" @click="loadRevisions(Math.max(0, historyOffset - HISTORY_LIMIT))">上一页</button>
        <span class="hint">第 {{ historyOffset + 1 }}–{{ historyOffset + history.items.length }} 条</span>
        <button type="button" :disabled="historyOffset + history.items.length >= history.total || busy === 'revisions'" @click="loadRevisions(historyOffset + HISTORY_LIMIT)">下一页</button>
      </div>
    </section>
  </section>
</template>

<style scoped>
.content-io { display: grid; gap: 16px; color: #24313d; }
.alert { margin: 0; padding: 10px 12px; border-left: 3px solid #b42318; background: #fff3f2; color: #8a1c13; font-size: 13px; }
.panel-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: stretch; }
.panel { min-width: 0; padding: 14px; border: 1px solid #dce3e8; border-radius: 6px; background: #fff; display: grid; gap: 12px; align-content: start; }
.panel header, .result-heading { display: flex; align-items: center; gap: 8px; min-height: 28px; }
h3 { margin: 0; font-size: 14px; color: #17232c; }
label { display: grid; gap: 5px; color: #60717e; font-size: 12px; }
label.confirm { grid-template-columns: auto 1fr; align-items: center; gap: 8px; }
input, textarea { width: 100%; min-width: 0; box-sizing: border-box; padding: 7px 9px; border: 1px solid #cbd5dc; border-radius: 4px; background: #fff; color: #17232c; font: inherit; font-size: 13px; }
textarea { resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
button { height: 34px; padding: 0 12px; border: 1px solid #116466; border-radius: 4px; background: #fff; color: #116466; display: inline-flex; justify-content: center; align-items: center; gap: 7px; font: inherit; cursor: pointer; }
button.primary { background: #116466; color: #fff; }
button:disabled { cursor: not-allowed; opacity: .5; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.result-band { padding: 14px; border-top: 1px solid #dce3e8; background: #f8fafb; display: grid; gap: 10px; }
.result-heading { justify-content: flex-start; gap: 12px; }
.summary-line { display: flex; flex-wrap: wrap; gap: 16px; margin: 0; color: #60717e; font-size: 13px; }
.hint { margin: 0; color: #71818d; font-size: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.checksum { overflow-wrap: anywhere; color: #475866; }
.row-table { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }
.row-table th { text-align: left; padding: 7px 8px; border-bottom: 1px solid #dce3e8; color: #60717e; font-weight: 600; }
.row-table td { padding: 7px 8px; border-bottom: 1px solid #e4e9ed; vertical-align: top; }
.cell-title { max-width: 260px; overflow-wrap: anywhere; }
@media (max-width: 1050px) { .panel-grid { grid-template-columns: 1fr; } }
</style>
