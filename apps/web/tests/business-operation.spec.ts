import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { OperationCatalogEntry, OperationFeatureEntry } from '@cloudctl/api-contracts'
import {
  canonicalOperationRequestHash,
  freezeBusinessOperationRequest,
  resolveBusinessOperationAvailability,
  type BusinessOperationRequestSnapshot,
} from '@/features/operations/business-operation'
import { mintBusinessOperation } from '@/features/operations/api'
import { operationFormRoutes, registerOperationFormRoutes } from '@/features/operations/routes'
import OperationFormWorkbenchView from '@/features/operations/OperationFormWorkbenchView.vue'
import { findOperation, operationsCatalog } from '@/data/operations-catalog'
import { createMemoryHistory, createRouter } from 'vue-router'

const state = vi.hoisted(() => ({
  configured: true,
  client: {
    operationFeatures: vi.fn(),
    operationCatalog: vi.fn(),
    createOperationTask: vi.fn(),
    createBatchOperation: vi.fn(),
    operationTask: vi.fn(),
  },
}))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return state.configured },
  operationsMockEnabled: false,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  createControlApiClient: () => state.client,
}))

beforeEach(() => {
  state.configured = true
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function catalogEntry(overrides: Partial<OperationCatalogEntry> = {}): OperationCatalogEntry {
  return {
    key: 'demo.operation.v1',
    module: 'demo',
    resourceType: 'product',
    batchAllowed: true,
    requiredPermission: 'operations:write',
    authorized: true,
    allowed: true,
    executorAvailable: true,
    executionState: 'implemented',
    allowedParameters: ['pageParameters'],
    description: 'demo',
    risk: 'standard',
    featureIds: ['f13-demo'],
    ...overrides,
  }
}

function featureEntry(overrides: Partial<OperationFeatureEntry> = {}): OperationFeatureEntry {
  return {
    featureId: 'f13-demo',
    index: 1,
    module: 'demo',
    moduleLabel: '演示',
    stage: '分发执行',
    title: '演示表单',
    mode: 'form',
    operationKey: 'demo.operation.v1',
    policy: 'mapped',
    executionState: 'implemented',
    risk: 'standard',
    authorized: true,
    allowed: true,
    executable: true,
    reason: '后端已确认可执行',
    ...overrides,
  }
}

/** operations-catalog 中真实存在、且带 backendOperationKey 的功能。 */
function realMappedOperation() {
  const found = operationsCatalog.find((item) => item.backendOperationKey !== null)
  if (!found) throw new Error('catalog has no mapped operation')
  return found
}

describe('F13 availability: four states, never mint unavailable ops (incl. mock)', () => {
  const operation = realMappedOperation()

  it('backend [STATE] reason wins and blocks minting', () => {
    const verdict = resolveBusinessOperationAvailability({
      operation,
      connection: 'live',
      catalog: catalogEntry({ key: operation.backendOperationKey!, featureIds: [operation.id] }),
      feature: featureEntry({ featureId: operation.id, operationKey: operation.backendOperationKey!, reason: '[POLICY_BLOCKED] 生产策略明确阻断该能力' }),
    })
    expect(verdict.state).toBe('POLICY_BLOCKED')
    expect(verdict.canMint).toBe(false)
    expect(verdict.reason).toContain('生产策略')
  })

  it('mock mode stays PENDING with an explicit no-mint reason even when backend says executable', () => {
    const verdict = resolveBusinessOperationAvailability({
      operation,
      connection: 'mock',
      catalog: catalogEntry({ key: operation.backendOperationKey!, featureIds: [operation.id] }),
      feature: featureEntry({ featureId: operation.id, operationKey: operation.backendOperationKey! }),
    })
    expect(verdict.state).toBe('PENDING')
    expect(verdict.canMint).toBe(false)
    expect(verdict.reason).toContain('Mock')
  })

  it('unmapped operations are OUT_OF_SCOPE and never fall back to a sample operation', () => {
    const unmapped = operationsCatalog.find((item) => item.backendOperationKey === null)!
    const verdict = resolveBusinessOperationAvailability({
      operation: unmapped,
      connection: 'live',
      catalog: undefined,
      feature: undefined,
    })
    expect(verdict.state).toBe('OUT_OF_SCOPE')
    expect(verdict.canMint).toBe(false)
  })

  it('full green path is ENABLED only when catalog and feature both confirm', () => {
    const verdict = resolveBusinessOperationAvailability({
      operation,
      connection: 'live',
      catalog: catalogEntry({ key: operation.backendOperationKey!, featureIds: [operation.id] }),
      feature: featureEntry({ featureId: operation.id, operationKey: operation.backendOperationKey! }),
    })
    expect(verdict.canMint).toBe(true)
  })
})

describe('F13 frozen snapshot: six-field canonical hash matches the backend algorithm', () => {
  it('computes the same sha256 as the backend canonical_hash over the six fields', async () => {
    const snapshot: BusinessOperationRequestSnapshot = {
      operationKey: 'demo.operation.v1',
      featureId: 'f13-demo',
      resourceIds: ['res-1', 'res-2'],
      parameters: { pageParameters: { budget: '19.9', count: 3, toggle: true, 备注: '中文' } },
      context: {
        deviceScope: 'device-1',
        executionApp: 'com.taobao.idlefish',
        schedule: 'immediate',
        snapshot: 'profile-key',
        reason: 'purpose',
        source: 'web',
        mode: 'form',
        sourcePage: 3,
        sourceRoute: '/demo',
      },
      batch: false,
    }
    // 期望值由后端同语义 canonical_json（sort_keys+紧凑分隔符+ensure_ascii=False）预计算。
    expect(await canonicalOperationRequestHash(snapshot)).toBe(
      'a9c1a54c2b9d9340cc3d1d524e131b9e8d0feaeaa919aa394030697b9992bb1c',
    )
  })

  it('freeze dedupes/trims resource ids and refuses batch when the catalog forbids it', () => {
    const operation = realMappedOperation()
    const catalog = catalogEntry({ key: operation.backendOperationKey!, featureIds: [operation.id], batchAllowed: false })
    const defaults = Object.fromEntries(
      operation.pageProfile.fields.map((field) => [field.id, field.defaultValue]),
    )
    const frozen = freezeBusinessOperationRequest({
      operation,
      catalog,
      pageParameters: defaults,
      resourceIds: [' a ', 'a'],
      context: {
        deviceScope: 'd', executionApp: 'app', schedule: 'now', snapshot: 'k',
        reason: 'r', source: 'web', mode: operation.mode,
        sourcePage: operation.sourcePage, sourceRoute: operation.sourceRoute,
      },
    })
    expect(frozen.resourceIds).toEqual(['a'])
    expect(frozen.batch).toBe(false)
    expect(() => freezeBusinessOperationRequest({
      operation,
      catalog,
      pageParameters: {},
      resourceIds: ['a', 'b'],
      context: { deviceScope: 'd', executionApp: 'app', schedule: 'now', snapshot: 'k', reason: 'r', source: 'web', mode: operation.mode, sourcePage: 1, sourceRoute: '/x' },
    })).toThrow('批量')
  })
})

describe('F13 mint api: single vs batch endpoints with Idempotency-Key', () => {
  it('posts single and batch to their frozen endpoints', async () => {
    state.client.createOperationTask.mockResolvedValue({ id: 'task-1', requestSha256: 'h', items: [] })
    state.client.createBatchOperation.mockResolvedValue({ id: 'task-2', requestSha256: 'h', items: [] })
    await mintBusinessOperation({
      operationKey: 'demo.operation.v1', featureId: 'f13-demo', resourceIds: ['res-1'],
      parameters: {}, context: {}, batch: false, idempotencyKey: 'idem-1',
    })
    await mintBusinessOperation({
      operationKey: 'demo.operation.v1', featureId: 'f13-demo', resourceIds: ['res-1', 'res-2'],
      parameters: {}, context: {}, batch: true, idempotencyKey: 'idem-2',
    })
    expect(state.client.createOperationTask).toHaveBeenCalledTimes(1)
    expect(state.client.createBatchOperation).toHaveBeenCalledTimes(1)
    expect(state.client.createOperationTask.mock.calls[0]).toEqual([
      { operationKey: 'demo.operation.v1', featureId: 'f13-demo', resourceId: 'res-1', parameters: {}, context: {} },
      'idem-1',
    ])
  })
})

describe('F13 workbench view', () => {
  it('registers one idempotent route', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    registerOperationFormRoutes(router)
    registerOperationFormRoutes(router)
    expect(operationFormRoutes).toHaveLength(1)
    expect(router.getRoutes().filter((route) => route.name === 'business-operations')).toHaveLength(1)
  })

  it('never mints and shows the reason while the backend marks the feature POLICY_BLOCKED', async () => {
    const operation = realMappedOperation()
    state.client.operationFeatures.mockResolvedValue([
      featureEntry({ featureId: operation.id, operationKey: operation.backendOperationKey!, reason: '[POLICY_BLOCKED] 生产策略明确阻断该能力' }),
    ])
    state.client.operationCatalog.mockResolvedValue([
      catalogEntry({ key: operation.backendOperationKey!, featureIds: [operation.id] }),
    ])
    render(OperationFormWorkbenchView)
    await waitFor(() => expect(state.client.operationCatalog).toHaveBeenCalled())
    await fireEvent.update(screen.getByRole('combobox'), operation.id)
    await waitFor(() => expect(screen.getByText('POLICY_BLOCKED')).toBeTruthy())
    const submit = screen.getByRole('button', { name: /不可提交/ }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(state.client.createOperationTask).not.toHaveBeenCalled()
    expect(state.client.createBatchOperation).not.toHaveBeenCalled()
  })

  it('freezes the visible snapshot, mints once, and shows per-target partial failures with hash equality', async () => {
    const operation = realMappedOperation()
    const catalog = catalogEntry({ key: operation.backendOperationKey!, featureIds: [operation.id] })
    const feature = featureEntry({ featureId: operation.id, operationKey: operation.backendOperationKey! })
    state.client.operationFeatures.mockResolvedValue([feature])
    state.client.operationCatalog.mockResolvedValue([catalog])
    const minted = {
      id: 'task-9',
      status: 'PARTIAL',
      requestSha256: '',
      totalCount: 2,
      succeededCount: 1,
      failedCount: 1,
      blockedCount: 0,
      items: [
        { id: 'i1', resourceId: 'res-1', status: 'SUCCEEDED', errorCode: null, detail: null, evidenceRefs: [], updatedAt: '2026-09-20T00:00:00Z' },
        { id: 'i2', resourceId: 'res-2', status: 'FAILED', errorCode: 'DEVICE_OFFLINE', detail: '设备离线，目标未执行', evidenceRefs: [], updatedAt: '2026-09-20T00:00:00Z' },
      ],
    }
    state.client.createOperationTask.mockImplementation(async (body: Record<string, unknown>) => {
      // 与后端 create_task 相同的六字段规范化，保证哈希语义一致。
      minted.requestSha256 = await canonicalOperationRequestHash({
        operationKey: body.operationKey as string,
        featureId: body.featureId as string,
        resourceIds: [body.resourceId as string],
        parameters: body.parameters as BusinessOperationRequestSnapshot['parameters'],
        context: body.context as BusinessOperationRequestSnapshot['context'],
        batch: false,
      })
      return minted
    })
    state.client.operationTask.mockResolvedValue(minted)

    render(OperationFormWorkbenchView)
    await waitFor(() => expect(state.client.operationCatalog).toHaveBeenCalled())
    await fireEvent.update(screen.getByRole('combobox'), operation.id)
    await waitFor(() => expect(screen.getByText('ENABLED')).toBeTruthy())
    await fireEvent.update(screen.getByRole('textbox', { name: /资源 ID/ }), 'res-1')
    await waitFor(() => expect(within(screen.getByTestId('business-operation-snapshot')).getByText('res-1')).toBeTruthy())
    await waitFor(() =>
      expect(within(screen.getByTestId('business-operation-snapshot')).getAllByText(/^[0-9a-f]{64}$/).length).toBeGreaterThan(0),
    )
    minted.requestSha256 = ''
    await fireEvent.click(screen.getByRole('button', { name: '提交业务操作' }))

    await waitFor(() => expect(screen.getByText('提交结果')).toBeTruthy())
    expect(screen.getByText('服务端 requestSha256 与页面哈希一致')).toBeTruthy()
    expect(screen.getByText('res-2')).toBeTruthy()
    expect(screen.getByText('DEVICE_OFFLINE')).toBeTruthy()
    expect(screen.getByText('设备离线，目标未执行')).toBeTruthy()
    expect(state.client.createOperationTask).toHaveBeenCalledTimes(1)
  })

  it('uses the real catalog: findOperation still resolves the mapped feature', () => {
    const operation = realMappedOperation()
    expect(findOperation(operation.moduleId, operation.id)?.id).toBe(operation.id)
  })
})
