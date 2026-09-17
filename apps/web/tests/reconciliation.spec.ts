import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { JsonObject } from '@cloudctl/api-contracts'
import { useSessionStore } from '@/stores/session'
import {
  cancelAvailabilityOf,
  deviceHandoverOf,
  externalEffectLabel,
  externalEffectOf,
  mapReconTask,
  reconcileAvailabilityOf,
  RECONCILE_BRANCHES,
  RECONCILE_DECISIONS,
  retryAvailabilityOf,
  validateReconcileSubmission,
} from '@/features/reconciliation/model'
import { resolveReconciliationDataMode } from '@/features/reconciliation/api'
import { reconciliationRoutes, registerReconciliationRoutes } from '@/features/reconciliation/routes'
import ReconciliationWorkbenchView from '@/features/reconciliation/ReconciliationWorkbenchView.vue'
import { createMemoryHistory, createRouter } from 'vue-router'

// ---------------------------------------------------------------------------
// fixture：与 _business_view() 字段形状对齐的原始任务（缺字段按可空处理）
// ---------------------------------------------------------------------------

interface RawTaskOverrides {
  taskId?: string
  state?: string
  runnerStatus?: string | null
  errorCode?: string | null
  reconciliation?: JsonObject | null
  commandPayload?: JsonObject | null
  accountId?: string | null
  commandType?: string | null
  stallReason?: string | null
}

function rawReconTask(overrides: RawTaskOverrides = {}): JsonObject {
  return {
    taskId: 'task-recon-0001',
    id: 'task-recon-0001',
    deviceId: 'dev-b0644fb5',
    accountId: 'acc-xianyu-01',
    bindingVersion: 7,
    commandType: 'xianyu.publish_listing.steps.v1',
    state: 'RECONCILING',
    runnerStatus: 'UNKNOWN',
    commandPayload: {},
    stallReason: null,
    errorCode: null,
    detail: null,
    reconciliation: null,
    controlRevision: 3,
    controlEvents: [{ revision: 3, event: 'MARKED_UNKNOWN', reason: 'commit result unknown', actor: 'operator:u1', issuedAt: '2026-09-17T09:00:00+08:00' }],
    attempt: 1,
    result: null,
    createdAt: '2026-09-17T09:00:00+08:00',
    ...overrides,
  }
}

function reconTask(overrides: RawTaskOverrides = {}) {
  const task = mapReconTask(rawReconTask(overrides))
  if (!task) throw new Error('fixture task failed to map')
  return task
}

// ---------------------------------------------------------------------------
// API / session mocks（模式对齐 tests/fleet.spec.ts）
// ---------------------------------------------------------------------------

const { api, flags } = vi.hoisted(() => ({
  api: {
    listPlatformTasks: vi.fn(),
    getPlatformTask: vi.fn(),
  },
  flags: {
    configured: true,
  },
}))

vi.mock('@/api/control', () => ({
  get controlApiConfigured() {
    return flags.configured
  },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  createControlApiClient: () => api,
}))

function primeList(...tasks: JsonObject[]) {
  api.listPlatformTasks.mockReset()
  api.getPlatformTask.mockReset()
  api.listPlatformTasks.mockResolvedValue({ items: tasks, nextCursor: null, limit: 100 })
}

function primeOperatorSession() {
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.applySession({ userId: 'user-op', tenantId: 'tenant-0001', roles: ['device_operator'], mfa: true, requestId: 'req-test' })
  return pinia
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

async function openPanel(taskId: string) {
  const row = await waitFor(() => {
    const node = document.querySelector(`[data-task-id="${taskId}"]`)
    expect(node).not.toBeNull()
    return node as HTMLElement
  })
  await fireEvent.click(within(row).getByRole('button', { name: '介入 / 对账' }))
  const panel = await screen.findByTestId('recon-panel')
  return { row, panel }
}

afterEach(() => {
  vi.unstubAllGlobals()
  flags.configured = true
})

// ---------------------------------------------------------------------------
// 验收 3：任务失败 ≠ 业务效果不确定 ≠ 成功（三轴推导不混淆）
// ---------------------------------------------------------------------------

describe('C11 model: three status axes derivation (no invented backend semantics)', () => {
  it('derives the external-effect axis from reconciliation envelope first, then state/errorCode, fail-closed to UNKNOWN', () => {
    // 服务端信封优先。
    expect(externalEffectOf(reconTask({ reconciliation: { status: 'APPLIED', history: [] } }))).toBe('APPLIED')
    expect(externalEffectOf(reconTask({ reconciliation: { status: 'NOT_SUBMITTED', history: [] } }))).toBe('NOT_SUBMITTED')
    expect(externalEffectOf(reconTask({ reconciliation: { status: 'KEEP_WAITING', history: [] } }))).toBe('UNKNOWN')
    // state/errorCode 推导。
    expect(externalEffectOf(reconTask({ state: 'SUCCEEDED', runnerStatus: 'SUCCEEDED' }))).toBe('APPLIED')
    expect(externalEffectOf(reconTask({ state: 'FAILED', errorCode: 'CONFIRMED_NOT_SUBMITTED' }))).toBe('NOT_SUBMITTED')
    expect(externalEffectOf(reconTask({ state: 'RECONCILING' }))).toBe('UNKNOWN')
    expect(externalEffectOf(reconTask({ state: 'FAILED', errorCode: 'COMMIT_UNKNOWN' }))).toBe('UNKNOWN')
    expect(externalEffectOf(reconTask({ state: 'FAILED', errorCode: 'ACCOUNT_CHANGED' }))).toBe('UNKNOWN')
    expect(externalEffectOf(reconTask({ state: 'FAILED', errorCode: 'STEP_TIMEOUT' }))).toBe('NOT_SUBMITTED')
    expect(externalEffectOf(reconTask({ state: 'RUNNING', runnerStatus: 'RUNNING' }))).toBe('PENDING')
  })

  it('never labels a failed-but-uncertain task as success (execution failure and uncertain effect stay distinct)', () => {
    const failed = reconTask({ state: 'FAILED', errorCode: 'COMMIT_UNKNOWN' })
    expect(externalEffectOf(failed)).toBe('UNKNOWN')
    expect(externalEffectLabel('UNKNOWN')).toContain('不确定')
    expect(externalEffectLabel('UNKNOWN')).not.toContain('已生效')
    expect(deviceHandoverOf(failed)).toBe('HOLD_RECONCILE')
  })

  it('derives the device-handover axis: hold on uncertain, in-use on active, returnable on settled+converged', () => {
    expect(deviceHandoverOf(reconTask({ state: 'RECONCILING' }))).toBe('HOLD_RECONCILE')
    expect(deviceHandoverOf(reconTask({ state: 'RUNNING', runnerStatus: 'RUNNING' }))).toBe('IN_USE')
    expect(deviceHandoverOf(reconTask({ state: 'SUCCEEDED', runnerStatus: 'SUCCEEDED' }))).toBe('RETURNABLE')
    expect(deviceHandoverOf(reconTask({ state: 'FAILED', errorCode: 'STEP_TIMEOUT' }))).toBe('RETURNABLE')
  })
})

// ---------------------------------------------------------------------------
// 验收 1/2：动作门槛镜像（取消/重试/对账可用性 + 三分支校验）
// ---------------------------------------------------------------------------

describe('C11 model: server-rule mirrors for cancel / retry / reconcile availability', () => {
  it('REFUSES cancel on RECONCILING (no path to clear an uncertain task via cancel)', () => {
    const verdict = cancelAvailabilityOf(reconTask({ state: 'RECONCILING' }))
    expect(verdict.available).toBe(false)
    expect(verdict.reason).toContain('REJECTED_RECONCILE_FIRST')
  })

  it('marks ordinary cancel as available but with an explicit irreversible consequence', () => {
    const verdict = cancelAvailabilityOf(reconTask({ state: 'RUNNING', runnerStatus: 'RUNNING' }))
    expect(verdict.available).toBe(true)
    expect(verdict.consequence).toContain('不可恢复')
    expect(verdict.consequence).toContain('不会把不确定结果改成成功')
  })

  it('refuses cancel inside the commit window (commandPayload carries commitIntent)', () => {
    const verdict = cancelAvailabilityOf(
      reconTask({ state: 'RUNNING', runnerStatus: 'RUNNING', commandPayload: { commitIntent: 'publish_listing' } }),
    )
    expect(verdict.available).toBe(false)
    expect(verdict.reason).toContain('commitIntent')
  })

  it('disables retry for RECONCILING and unsafe error codes, mirroring the server 409 rules', () => {
    expect(retryAvailabilityOf(reconTask({ state: 'RECONCILING' })).available).toBe(false)
    expect(retryAvailabilityOf(reconTask({ state: 'RECONCILING' })).reason).toContain('先对账')
    expect(retryAvailabilityOf(reconTask({ state: 'FAILED', errorCode: 'ACCOUNT_CHANGED' })).available).toBe(false)
    expect(retryAvailabilityOf(reconTask({ state: 'RUNNING', runnerStatus: 'RUNNING' })).available).toBe(false)
    expect(retryAvailabilityOf(reconTask({ state: 'FAILED', errorCode: 'STEP_TIMEOUT' })).available).toBe(true)
  })

  it('allows reconcile only for RECONCILING / non-terminal COMMIT_UNKNOWN tasks (terminal is refused 409)', () => {
    expect(reconcileAvailabilityOf(reconTask({ state: 'RECONCILING' })).available).toBe(true)
    // 非终态 + COMMIT_UNKNOWN（服务端 reconcile 的第二分支）。
    expect(reconcileAvailabilityOf(reconTask({ state: 'RUNNING', runnerStatus: 'RUNNING', errorCode: 'COMMIT_UNKNOWN' })).available).toBe(true)
    // FAILED 属终态：即便错误码是 COMMIT_UNKNOWN，服务端也按终态 409 拒绝。
    expect(reconcileAvailabilityOf(reconTask({ state: 'FAILED', errorCode: 'COMMIT_UNKNOWN' })).available).toBe(false)
    expect(reconcileAvailabilityOf(reconTask({ state: 'SUCCEEDED', runnerStatus: 'SUCCEEDED' })).available).toBe(false)
    expect(reconcileAvailabilityOf(reconTask({ state: 'QUEUED', runnerStatus: 'QUEUED' })).available).toBe(false)
  })
})

describe('C11 model: exactly three reconcile branches with pre-submit validation', () => {
  it('exposes exactly the three frozen decisions and no shortcut branch', () => {
    expect([...RECONCILE_DECISIONS]).toEqual(['KEEP_WAITING', 'CONFIRMED_APPLIED', 'CONFIRMED_NOT_SUBMITTED'])
    expect(RECONCILE_BRANCHES).toHaveLength(3)
    expect(RECONCILE_BRANCHES.map((branch) => branch.decision)).toEqual([...RECONCILE_DECISIONS])
    // 没有任何分支叫「重试」：分支集合与 retry 无关。
    expect(RECONCILE_BRANCHES.some((branch) => /retry|重试/i.test(branch.decision))).toBe(false)
  })

  it('blocks unreadable evidence, missing precise target, and unknown decisions', () => {
    const task = reconTask({ state: 'RECONCILING' })
    expect(validateReconcileSubmission(task, 'KEEP_WAITING', '  ', '').ok).toBe(false)
    expect(validateReconcileSubmission(task, 'KEEP_WAITING', 'ab', '').reason).toContain('证据不可读')
    expect(validateReconcileSubmission(task, 'KEEP_WAITING', '平台页人工核对无此商品', '').ok).toBe(true)
    expect(validateReconcileSubmission(task, 'RETRY_UNKNOWN', '证据足够长', '').reason).toContain('非法决策')
    // 精确目标缺失（账号/动作未知）→ 禁止确认。
    const incomplete = reconTask({ state: 'RECONCILING', accountId: null, commandType: null })
    expect(validateReconcileSubmission(incomplete, 'KEEP_WAITING', '证据足够长', '').reason).toContain('精确目标不完整')
  })

  it('front-blocks CONFIRMED_APPLIED without a platformItemId (server would 409)', () => {
    const task = reconTask({ state: 'RECONCILING' })
    const verdict = validateReconcileSubmission(task, 'CONFIRMED_APPLIED', '闲鱼商品页已存在该商品', '')
    expect(verdict.ok).toBe(false)
    expect(verdict.reason).toContain('platformItemId')
    expect(validateReconcileSubmission(task, 'CONFIRMED_APPLIED', '闲鱼商品页已存在该商品', 'item-8899').ok).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 视图：fail-closed / 三轴并排 / 介入面板
// ---------------------------------------------------------------------------

describe('C11 view: fail-closed when Control API is not configured', () => {
  it('keeps the workbench closed (no list fetch, no mock fallback)', async () => {
    flags.configured = false
    primeList()
    render(ReconciliationWorkbenchView, { global: { plugins: [createPinia()] } })
    const alert = await screen.findByTestId('recon-unavailable')
    expect(alert.textContent).toContain('fail-closed')
    expect(api.listPlatformTasks).not.toHaveBeenCalled()
    expect(resolveReconciliationDataMode(false)).toBe('unavailable')
  })
})

describe('C11 view: three axes rendered side by side, failure never dressed as success', () => {
  it('renders execution/effect/handover badges per task and keeps the uncertain task free of green success tags', async () => {
    primeList(
      rawReconTask({ taskId: 'task-failed-unknown', state: 'FAILED', errorCode: 'COMMIT_UNKNOWN', runnerStatus: 'FAILED' }),
      rawReconTask({ taskId: 'task-succeeded', state: 'SUCCEEDED', runnerStatus: 'SUCCEEDED' }),
    )
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })

    const failedRow = await waitFor(() => {
      const node = document.querySelector('[data-task-id="task-failed-unknown"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })
    const succeededRow = await waitFor(() => {
      const node = document.querySelector('[data-task-id="task-succeeded"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })

    // 失败 + 效果不确定：执行轴红（FAILED）、效果轴琥珀（不确定）、交还轴琥珀（不可交还），没有任何绿色成功徽章。
    expect(within(failedRow).getByTestId('recon-axis-execution').textContent).toContain('FAILED')
    expect(within(failedRow).getByTestId('recon-axis-effect').textContent).toContain('不确定')
    expect(within(failedRow).getByTestId('recon-axis-handover').textContent).toContain('不可交还')
    expect(failedRow.querySelectorAll('.tag-ok')).toHaveLength(0)

    // 真正成功：执行轴绿 + 效果已生效 + 可交还。
    expect(within(succeededRow).getByTestId('recon-axis-execution').textContent).toContain('SUCCEEDED')
    expect(within(succeededRow).getByTestId('recon-axis-effect').textContent).toContain('已生效')
    expect(succeededRow.querySelectorAll('.tag-ok').length).toBeGreaterThan(0)
  })
})

describe('C11 acceptance 1: an UNKNOWN/RECONCILING task cannot be cleared to success via cancel', () => {
  it('disables cancel on RECONCILING with the 409 reason, shows no consequence note, and offers no clear-to-success button', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-hold', state: 'RECONCILING', stallReason: 'commit result unknown' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-hold')

    const cancelButton = within(panel).getByTestId('recon-cancel') as HTMLButtonElement
    expect(cancelButton.disabled).toBe(true)
    expect(cancelButton.title).toContain('REJECTED_RECONCILE_FIRST')
    // 取消后果提示只在可取消时出现；RECONCILING 下不存在「取消清零」的暗示。
    expect(within(panel).queryByTestId('recon-cancel-consequence')).toBeNull()
    // 取消按钮自身的文案明确标注不可恢复。
    expect(cancelButton.textContent).toContain('不可恢复')
    // 没有任何按钮直接把任务改成成功：面板里不存在「标记成功」类快捷键，唯一收敛路径是三分支对账。
    const buttons = [...panel.querySelectorAll('button')].map((node) => node.textContent ?? '')
    expect(buttons.some((text) => /标记成功|直接成功|清除为成功/.test(text))).toBe(false)
  })

  it('disables retry on RECONCILING with the reconcile-first reason', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-hold', state: 'RECONCILING' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-hold')
    const retryButton = within(panel).getByTestId('recon-retry') as HTMLButtonElement
    expect(retryButton.disabled).toBe(true)
    expect(retryButton.title).toContain('先对账')
  })
})

describe('C11 acceptance 2: unreadable/missing evidence cannot pass (confirm disabled with reason)', () => {
  it('keeps submit disabled with an explicit reason until a branch plus readable evidence exist, and never calls the server', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-hold', state: 'RECONCILING' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-hold')

    const submit = within(panel).getByTestId('recon-submit') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(within(panel).getByTestId('recon-block-reason').textContent).toContain('三个对账分支')

    // 选分支但证据为空 → 仍然禁用，理由指向证据。
    await fireEvent.click(within(panel).getByTestId('recon-branch-KEEP_WAITING'))
    expect(submit.disabled).toBe(true)
    expect(within(panel).getByTestId('recon-block-reason').textContent).toContain('证据不可读')

    // 点击被禁用的提交按钮也不发出请求（前端不是授权来源，也不发必败请求）。
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await fireEvent.click(submit)
    expect(fetchMock).not.toHaveBeenCalled()

    // 补足证据 → 放行提交（由服务端裁决）。
    await fireEvent.update(within(panel).getByTestId('recon-evidence'), '平台页人工核对，尚无结果')
    expect(submit.disabled).toBe(false)
    expect(within(panel).queryByTestId('recon-block-reason')).toBeNull()
  })

  it('blocks confirmation when the precise target is incomplete (accountId/commandType missing)', async () => {
    primeList(rawReconTask({ taskId: 'task-blank-target', state: 'RECONCILING', accountId: null, commandType: null }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-blank-target')

    expect(within(panel).getByTestId('recon-target-incomplete').textContent).toContain('禁止提交任何确认')
    await fireEvent.click(within(panel).getByTestId('recon-branch-KEEP_WAITING'))
    await fireEvent.update(within(panel).getByTestId('recon-evidence'), '证据足够长的核对描述')
    const submit = within(panel).getByTestId('recon-submit') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(within(panel).getByTestId('recon-block-reason').textContent).toContain('精确目标不完整')
  })
})

describe('C11 acceptance 4: CONFIRMED_APPLIED needs platformItemId (front intercept) and 409 conflicts render verbatim', () => {
  it('front-blocks the submission without platformItemId, then sends it once filled (server-authoritative)', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-applied', state: 'RECONCILING' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-applied')

    await fireEvent.click(within(panel).getByTestId('recon-branch-CONFIRMED_APPLIED'))
    await fireEvent.update(within(panel).getByTestId('recon-evidence'), '闲鱼 App 已看到该商品在售，人工核对通过')
    // 精确目标卡片此时标注 platformItemId 必填。
    expect(within(panel).getByTestId('recon-target').textContent).toContain('必填')

    const submit = within(panel).getByTestId('recon-submit') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(within(panel).getByTestId('recon-block-reason').textContent).toContain('platformItemId')

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await fireEvent.click(submit)
    expect(fetchMock).not.toHaveBeenCalled() // 前端拦截，未发必败请求

    await fireEvent.update(within(panel).getByTestId('recon-platform-item-id'), 'item-8899')
    expect(submit.disabled).toBe(false)
    fetchMock.mockResolvedValue(jsonResponse(rawReconTask({ taskId: 'task-recon-applied', state: 'SUCCEEDED', runnerStatus: 'SUCCEEDED' })))
    await fireEvent.click(submit)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/platform-tasks/task-recon-applied:reconcile')
    expect(JSON.parse(String(init.body))).toEqual({
      decision: 'CONFIRMED_APPLIED',
      evidence: '闲鱼 App 已看到该商品在售，人工核对通过',
      platformItemId: 'item-8899',
    })
    expect(await screen.findByTestId('recon-action-done')).toBeTruthy()
  })

  it('renders the 409 conflict detail verbatim (NOT_SUBMITTED vs APPLIED ledger) and never shows success', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-conflict', state: 'RECONCILING' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-conflict')

    await fireEvent.click(within(panel).getByTestId('recon-branch-CONFIRMED_NOT_SUBMITTED'))
    await fireEvent.update(within(panel).getByTestId('recon-evidence'), '平台后台与 App 均无此商品，确认未提交')
    const submit = within(panel).getByTestId('recon-submit') as HTMLButtonElement
    expect(submit.disabled).toBe(false)

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            type: 'about:blank',
            title: 'Conflict',
            status: 409,
            code: 'CONFLICT',
            detail: 'reported APPLIED evidence contradicts NOT_SUBMITTED',
          },
          409,
        ),
      ),
    )
    await fireEvent.click(submit)

    const error = await screen.findByTestId('recon-action-error')
    expect(error.textContent).toContain('409')
    expect(error.textContent).toContain('reported APPLIED evidence contradicts NOT_SUBMITTED')
    expect(screen.queryByTestId('recon-action-done')).toBeNull()
  })
})

describe('C11 view: KEEP_WAITING and mark-unknown both go through the server endpoints', () => {
  it('submits KEEP_WAITING to :reconcile with evidence (server stays the authority)', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-wait', state: 'RECONCILING' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-wait')

    await fireEvent.click(within(panel).getByTestId('recon-branch-KEEP_WAITING'))
    await fireEvent.update(within(panel).getByTestId('recon-evidence'), '平台结果尚未唯一，继续等待')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(rawReconTask({ taskId: 'task-recon-wait', state: 'RECONCILING', reconciliation: { status: 'KEEP_WAITING', history: [] } })))
    vi.stubGlobal('fetch', fetchMock)
    await fireEvent.click(within(panel).getByTestId('recon-submit'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/platform-tasks/task-recon-wait:reconcile')
    expect(JSON.parse(String(init.body))).toEqual({ decision: 'KEEP_WAITING', evidence: '平台结果尚未唯一，继续等待' })
    expect(await screen.findByTestId('recon-action-done')).toBeTruthy()
  })

  it('sends mark-unknown to :mark-unknown and renders the refusal verbatim on 409', async () => {
    primeList(rawReconTask({ taskId: 'task-recon-mark', state: 'RUNNING', runnerStatus: 'RUNNING' }))
    render(ReconciliationWorkbenchView, { global: { plugins: [primeOperatorSession()] } })
    const { panel } = await openPanel('task-recon-mark')

    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ type: 'about:blank', title: 'Conflict', status: 409, code: 'CONFLICT', detail: 'terminal tasks cannot enter reconciliation' }, 409),
    )
    vi.stubGlobal('fetch', fetchMock)
    await fireEvent.click(within(panel).getByTestId('recon-mark-unknown'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/platform-tasks/task-recon-mark:mark-unknown')
    expect(JSON.parse(String(init.body))).toHaveProperty('reason')
    const error = await screen.findByTestId('recon-action-error')
    expect(error.textContent).toContain('terminal tasks cannot enter reconciliation')
  })
})

describe('C11 routes: minimal registration point', () => {
  it('exposes one reconciliation route and registers idempotently', async () => {
    expect(reconciliationRoutes).toHaveLength(1)
    expect(reconciliationRoutes[0]?.path).toBe('/reconciliation')
    expect(reconciliationRoutes[0]?.name).toBe('reconciliation-workbench')
    expect(reconciliationRoutes[0]?.meta?.title).toBe('对账工作台')

    const router = createRouter({ history: createMemoryHistory(), routes: [...reconciliationRoutes] })
    registerReconciliationRoutes(router)
    registerReconciliationRoutes(router)
    await router.push('/reconciliation')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('reconciliation-workbench')
  })
})
