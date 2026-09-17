<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useSessionStore } from '@/stores/session'
import PageHeader from '@/components/PageHeader.vue'
import QueryState from '@/components/QueryState.vue'
import { controlApiConfigured } from '@/api/control'
import {
  cancelTask,
  fetchReconTasks,
  markTaskUnknown,
  reconcileTask,
  resolveReconciliationDataMode,
  retryTask,
  RECONCILIATION_WORKBENCH_VERSION,
  type ReconciliationApiError,
} from './api'
import {
  cancelAvailabilityOf,
  deviceHandoverLabel,
  deviceHandoverOf,
  externalEffectLabel,
  externalEffectOf,
  markUnknownAvailabilityOf,
  preciseTargetOf,
  reconcileAvailabilityOf,
  RECONCILE_BRANCHES,
  retryAvailabilityOf,
  validateReconcileSubmission,
  type ReconTask,
  type ReconcileDecision,
} from './model'

const session = useSessionStore()
const mode = resolveReconciliationDataMode(controlApiConfigured)

const loading = ref(false)
const loadError = ref('')
const tasks = ref<ReconTask[]>([])
const pendingOnly = ref(false)
const selectedTaskId = ref<string | null>(null)
const decision = ref<ReconcileDecision | null>(null)
const evidence = ref('')
const platformItemId = ref('')
const actionBusy = ref('')
const actionError = ref<{ status: number; code: string; detail: string } | null>(null)
const actionDone = ref('')

const canAct = computed(() => session.can('task.create'))
const visibleTasks = computed(() => {
  if (!pendingOnly.value) return tasks.value
  return tasks.value.filter((task) => task.state === 'RECONCILING' || task.errorCode === 'COMMIT_UNKNOWN')
})
const selectedTask = computed(() => tasks.value.find((task) => task.taskId === selectedTaskId.value) ?? null)
const reconAvailability = computed(() => (selectedTask.value ? reconcileAvailabilityOf(selectedTask.value) : null))
const markUnknownAvailability = computed(() => (selectedTask.value ? markUnknownAvailabilityOf(selectedTask.value) : null))
const retryAvailability = computed(() => (selectedTask.value ? retryAvailabilityOf(selectedTask.value) : null))
const cancelAvailability = computed(() => (selectedTask.value ? cancelAvailabilityOf(selectedTask.value) : null))
const submission = computed(() =>
  selectedTask.value ? validateReconcileSubmission(selectedTask.value, decision.value, evidence.value, platformItemId.value) : { ok: false, reason: '先选择一个任务' },
)
const submitDisabled = computed(
  () => !canAct.value || actionBusy.value !== '' || !reconAvailability.value?.available || !submission.value.ok,
)
const submitTitle = computed(() => {
  if (!canAct.value) return '当前身份缺少 task.create 权限'
  if (!reconAvailability.value?.available) return reconAvailability.value?.reason ?? '该任务不可对账'
  return submission.value.reason ?? '把对账决策提交服务端裁决'
})

function axisClasses(kind: 'execution' | 'effect' | 'handover', task: ReconTask): string[] {
  // 成功绿（tag-ok）只给「执行成功且外部效果已确认」的组合；不确定一律琥珀，失败红。
  if (kind === 'execution') {
    if (task.state === 'SUCCEEDED') return ['tag', 'tag-ok']
    if (task.state === 'FAILED') return ['tag', 'tag-danger']
    if (task.state === 'RECONCILING') return ['tag', 'tag-warn']
    return ['tag', 'tag-info']
  }
  const effect = externalEffectOf(task)
  if (kind === 'effect') {
    if (effect === 'APPLIED') return ['tag', 'tag-ok']
    if (effect === 'UNKNOWN') return ['tag', 'tag-warn']
    if (effect === 'NOT_SUBMITTED') return ['tag', 'tag-muted']
    return ['tag', 'tag-info']
  }
  const handover = deviceHandoverOf(task)
  if (handover === 'RETURNABLE') return ['tag', 'tag-ok']
  if (handover === 'HOLD_RECONCILE') return ['tag', 'tag-warn']
  return ['tag', 'tag-info']
}

function effectOf(task: ReconTask): string {
  return externalEffectLabel(externalEffectOf(task))
}

function handoverOf(task: ReconTask): string {
  return deviceHandoverLabel(deviceHandoverOf(task))
}

function selectTask(taskId: string) {
  if (selectedTaskId.value === taskId) return
  selectedTaskId.value = taskId
  resetForm()
}

function resetForm() {
  decision.value = null
  evidence.value = ''
  platformItemId.value = ''
  actionError.value = null
  actionDone.value = ''
  actionBusy.value = ''
}

watch(pendingOnly, () => {
  if (selectedTaskId.value && !visibleTasks.value.some((task) => task.taskId === selectedTaskId.value)) {
    selectedTaskId.value = null
    resetForm()
  }
})

async function refresh() {
  if (mode === 'unavailable') {
    loadError.value = '未配置 VITE_CONTROL_API_URL，对账工作台保持关闭（fail-closed，不回退 Mock）。'
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    tasks.value = await fetchReconTasks()
  } catch (error) {
    // fail-closed：API 失败不回退 Mock，保持错误态。
    tasks.value = []
    loadError.value = `Control API 请求失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

function errorOf(error: unknown): { status: number; code: string; detail: string } {
  const apiError = error as ReconciliationApiError
  if (apiError && typeof apiError === 'object' && 'status' in apiError && 'code' in apiError) {
    return { status: apiError.status, code: apiError.code, detail: apiError.message }
  }
  return { status: 0, code: 'UNKNOWN_ERROR', detail: error instanceof Error ? error.message : String(error) }
}

async function runAction(name: string, action: () => Promise<ReconTask>) {
  actionBusy.value = name
  actionError.value = null
  actionDone.value = ''
  try {
    const updated = await action()
    actionDone.value = `服务端已受理（${updated.taskId} → ${updated.state}）`
    await refresh()
  } catch (error) {
    // 服务端负例（409 冲突等）原文呈现，绝不显示成成功。
    actionError.value = errorOf(error)
  } finally {
    actionBusy.value = ''
  }
}

function submitReconcile() {
  const task = selectedTask.value
  if (!task || submitDisabled.value) return // 前端只拦截明显必败/越权的请求；放行由服务端裁决
  const chosen = decision.value
  if (!chosen) return
  void runAction('reconcile', () => reconcileTask(task.taskId, chosen, evidence.value.trim(), platformItemId.value.trim()))
}

function submitMarkUnknown() {
  const task = selectedTask.value
  if (!task || !canAct.value || !markUnknownAvailability.value?.available || actionBusy.value !== '') return
  void runAction('mark-unknown', () =>
    markTaskUnknown(task.taskId, evidence.value.trim() || 'operator marked unknown from reconciliation workbench'),
  )
}

function submitCancel() {
  const task = selectedTask.value
  if (!task || !canAct.value || !cancelAvailability.value?.available || actionBusy.value !== '') return
  void runAction('cancel', () => cancelTask(task.taskId, 'operator canceled from reconciliation workbench'))
}

function submitRetry() {
  const task = selectedTask.value
  if (!task || !canAct.value || !retryAvailability.value?.available || actionBusy.value !== '') return
  void runAction('retry', () => retryTask(task.taskId, 'operator retried from reconciliation workbench'))
}

onMounted(() => { void refresh() })
</script>

<template>
  <div>
    <PageHeader
      title="对账与人工介入工作台"
      description="三轴并视：任务执行状态 / 外部效果状态 / 设备可否安全交还。对账只走服务端三分支裁决，前端不做任何本地豁免。"
      :kicker="`UI ${RECONCILIATION_WORKBENCH_VERSION}`"
    />

    <div v-if="mode === 'unavailable'" class="notice notice-danger" role="alert" data-testid="recon-unavailable">
      <strong>Control API 未配置</strong>
      <p>未配置 VITE_CONTROL_API_URL，对账工作台保持关闭（fail-closed），不会自动回退 Mock 数据，也不会发出任何介入动作。</p>
    </div>
    <div v-if="loadError" class="notice notice-danger" role="alert" data-testid="recon-load-error">{{ loadError }}</div>

    <QueryState
      :loading="loading"
      :error="null"
      :empty="visibleTasks.length === 0 && !loading && !loadError"
      empty-text="当前租户没有平台任务记录。"
    >
      <div class="recon-toolbar page-actions">
        <button class="button" type="button" :disabled="mode === 'unavailable' || loading" @click="refresh">刷新任务列表</button>
        <button class="button" type="button" :class="{ 'button-primary': pendingOnly }" @click="pendingOnly = !pendingOnly">
          {{ pendingOnly ? '显示全部任务' : '只看待对账（RECONCILING / COMMIT_UNKNOWN）' }}
        </button>
        <span class="cell-sub">共 {{ tasks.length }} 条 · 待对账 {{ tasks.filter((task) => task.state === 'RECONCILING' || task.errorCode === 'COMMIT_UNKNOWN').length }} 条</span>
      </div>

      <div class="recon-axes-header cell-sub">
        并列三轴：① 任务执行状态（status）② 外部效果状态（business_state / reconciliation）③ 设备是否可安全交还（推导）
      </div>

      <section class="panel recon-list" data-testid="recon-task-list">
        <div
          v-for="task in visibleTasks"
          :key="task.taskId"
          class="recon-row"
          :class="{ 'recon-row-active': task.taskId === selectedTaskId }"
          :data-task-id="task.taskId"
        >
          <div class="recon-row-main">
            <span class="mono cell-sub">{{ task.taskId }}</span>
            <strong class="cell-sub">{{ task.commandType ?? 'commandType 缺失' }}</strong>
            <span class="cell-sub">设备 {{ task.deviceId ?? '未知' }} · 账号 {{ task.accountId ?? '未知' }}</span>
          </div>
          <div class="recon-row-axes">
            <span data-testid="recon-axis-execution" :class="axisClasses('execution', task)">执行：{{ task.state }}<template v-if="task.runnerStatus && task.runnerStatus !== task.state"> / {{ task.runnerStatus }}</template></span>
            <span data-testid="recon-axis-effect" :class="axisClasses('effect', task)">效果：{{ effectOf(task) }}</span>
            <span data-testid="recon-axis-handover" :class="axisClasses('handover', task)">交还：{{ handoverOf(task) }}</span>
          </div>
          <div class="recon-row-actions">
            <button class="button" type="button" @click="selectTask(task.taskId)">介入 / 对账</button>
          </div>
        </div>
      </section>

      <section v-if="selectedTask" class="panel recon-panel" data-testid="recon-panel">
        <h3>人工介入面板</h3>

        <!-- 任何确认前展示精确目标（taskId、commandType、账号、动作、platformItemId 是否必填） -->
        <div class="recon-target" data-testid="recon-target">
          <h4>精确目标（提交任何决策前请核对）</h4>
          <dl>
            <div><dt>taskId</dt><dd class="mono">{{ preciseTargetOf(selectedTask, decision).taskId }}</dd></div>
            <div><dt>commandType（动作）</dt><dd class="mono">{{ selectedTask.commandType ?? '缺失' }}</dd></div>
            <div><dt>deviceId</dt><dd class="mono">{{ selectedTask.deviceId ?? '缺失' }}</dd></div>
            <div><dt>平台账号</dt><dd class="mono">{{ selectedTask.accountId ?? '缺失' }}</dd></div>
            <div><dt>bindingVersion / attempt</dt><dd class="mono">{{ selectedTask.bindingVersion ?? '—' }} / {{ selectedTask.attempt ?? '—' }}</dd></div>
            <div>
              <dt>platformItemId</dt>
              <dd>{{ decision === 'CONFIRMED_APPLIED' ? '必填（CONFIRMED_APPLIED 的证据锚点）' : '本分支不要求' }}</dd>
            </div>
          </dl>
          <p v-if="!preciseTargetOf(selectedTask, decision).accountId || !selectedTask.commandType" class="recon-warn" data-testid="recon-target-incomplete">
            精确目标不完整（commandType / 账号 / 设备有缺失）：禁止提交任何确认。
          </p>
        </div>

        <div class="recon-status-facts">
          <p v-if="selectedTask.stallReason" class="cell-sub">停滞原因：{{ selectedTask.stallReason }}</p>
          <p v-if="selectedTask.errorCode" class="cell-sub">错误码：{{ selectedTask.errorCode }}<template v-if="selectedTask.detail"> · {{ selectedTask.detail }}</template></p>
          <p v-if="selectedTask.reconciliation?.status" class="cell-sub">
            对账信封：{{ selectedTask.reconciliation.status }}<template v-if="selectedTask.reconciliation.reason"> · {{ selectedTask.reconciliation.reason }}</template>
          </p>
          <p v-if="selectedTask.reconciliation && selectedTask.reconciliation.history.length > 0" class="cell-sub">
            历史决策：{{ selectedTask.reconciliation.history.length }} 条（最新：{{ selectedTask.reconciliation.history[selectedTask.reconciliation.history.length - 1]?.decision }}）
          </p>
          <p v-if="(selectedTask.controlEvents ?? []).length > 0" class="cell-sub">
            控制事件（最近）：{{ [...selectedTask.controlEvents].slice(-3).map((event) => event.event ?? '?').join(' → ') }}
          </p>
        </div>

        <div class="recon-branch-area">
          <h4>对账分支（只有这三条路，没有「重试 UNKNOWN」快捷方式）</h4>
          <div v-for="branch in RECONCILE_BRANCHES" :key="branch.decision" class="recon-branch">
            <label class="recon-branch-label">
              <input
                v-model="decision"
                type="radio"
                name="recon-decision"
                :value="branch.decision"
                :data-testid="`recon-branch-${branch.decision}`"
                :disabled="!canAct || !reconAvailability?.available"
              />
              <span>{{ branch.label }}</span>
            </label>
            <p class="cell-sub">{{ branch.hint }}</p>
          </div>

          <label class="recon-field">
            <span>核实证据（必填，≥3 字符；服务端校验一致）</span>
            <textarea v-model="evidence" rows="3" aria-label="对账证据" data-testid="recon-evidence" placeholder="例：闲鱼 App 商品页已存在该商品，URL/ID 已人工核对" />
          </label>
          <label v-if="decision === 'CONFIRMED_APPLIED'" class="recon-field">
            <span>平台条目 platformItemId（CONFIRMED_APPLIED 必填）</span>
            <input v-model="platformItemId" type="text" aria-label="平台条目ID" data-testid="recon-platform-item-id" placeholder="平台侧唯一条目 ID" />
          </label>

          <p v-if="!submission.ok" class="recon-warn" data-testid="recon-block-reason">{{ submission.reason }}</p>
          <p v-else class="cell-sub recon-ok-hint">校验通过：将把 {{ decision }} 连同证据提交服务端裁决。</p>

          <div class="recon-actions">
            <button
              class="button button-primary"
              type="button"
              data-testid="recon-submit"
              :disabled="submitDisabled"
              :title="submitTitle"
              @click="submitReconcile"
            >
              {{ actionBusy === 'reconcile' ? '提交中…' : '提交对账决策' }}
            </button>
            <button
              class="button"
              type="button"
              data-testid="recon-mark-unknown"
              :disabled="!canAct || !markUnknownAvailability?.available || actionBusy !== ''"
              :title="!canAct ? '当前身份缺少 task.create 权限' : (markUnknownAvailability?.reason ?? 'POST :mark-unknown，任务进入 RECONCILING')"
              @click="submitMarkUnknown"
            >
              {{ actionBusy === 'mark-unknown' ? '标记中…' : '标记结果未知（进入对账）' }}
            </button>
            <button
              class="button"
              type="button"
              data-testid="recon-retry"
              :disabled="!canAct || !retryAvailability?.available || actionBusy !== ''"
              :title="!canAct ? '当前身份缺少 task.create 权限' : (retryAvailability?.reason ?? 'POST :retry，仅安全失败码可重试')"
              @click="submitRetry"
            >
              重试任务
            </button>
            <button
              class="button button-danger"
              type="button"
              data-testid="recon-cancel"
              :disabled="!canAct || !cancelAvailability?.available || actionBusy !== ''"
              :title="!canAct ? '当前身份缺少 task.create 权限' : (cancelAvailability?.reason ?? cancelAvailability?.consequence ?? '')"
              @click="submitCancel"
            >
              取消任务（不可恢复）
            </button>
          </div>
          <p v-if="cancelAvailability?.available" class="cell-sub recon-consequence" data-testid="recon-cancel-consequence">
            取消后果：{{ cancelAvailability.consequence }}
          </p>
        </div>

        <p v-if="actionError" class="recon-error" role="alert" data-testid="recon-action-error">
          服务端拒绝（HTTP {{ actionError.status }} / {{ actionError.code }}）：{{ actionError.detail }}
        </p>
        <p v-if="actionDone" class="recon-done" data-testid="recon-action-done">{{ actionDone }}</p>
      </section>
    </QueryState>
  </div>
</template>

<style scoped>
.recon-toolbar { margin-bottom: 12px; align-items: center; }
.recon-axes-header { margin: 4px 0 8px; }
.recon-list { padding: 8px 16px; margin-bottom: 12px; }
.recon-row { display: flex; flex-direction: column; gap: 6px; padding: 10px 0; border-top: 1px solid #e2e8f0; }
.recon-row-active { background: #f1f5f9; }
.recon-row-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.recon-row-axes { display: flex; gap: 8px; flex-wrap: wrap; }
.recon-row-actions { display: flex; gap: 8px; }
.recon-panel { padding: 14px 16px; }
.recon-panel h3, .recon-panel h4 { margin: 0 0 8px; }
.recon-target { border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; }
.recon-target dl { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 4px 16px; margin: 0; }
.recon-target dl div { display: flex; gap: 8px; }
.recon-target dt { color: #64748b; white-space: nowrap; }
.recon-target dd { margin: 0; word-break: break-all; }
.recon-status-facts { margin-bottom: 12px; }
.recon-status-facts p { margin: 2px 0; }
.recon-branch-area { border-top: 1px dashed #cbd5e1; padding-top: 10px; }
.recon-branch { margin-bottom: 6px; }
.recon-branch-label { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.recon-branch p { margin: 2px 0 0 24px; }
.recon-field { display: flex; flex-direction: column; gap: 4px; margin: 10px 0; }
.recon-field textarea, .recon-field input { padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 4px; }
.recon-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.recon-warn { color: #b45309; font-weight: 600; }
.recon-ok-hint { color: #15803d; }
.recon-consequence { color: #b45309; }
.recon-error { color: #b91c1c; font-weight: 600; }
.recon-done { color: #15803d; }
.tag-warn { background: #fef3c7; color: #b45309; }
.tag-muted { background: #e2e8f0; color: #475569; }
.tag-info { background: #e0f2fe; color: #0369a1; }
.tag-ok { background: #dcfce7; color: #15803d; }
.tag-danger { background: #fee2e2; color: #b91c1c; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
</style>
