import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OperationTask, ProductView } from '@cloudctl/api-contracts'

const { api, queuedTask, canceledTask } = vi.hoisted(() => {
  const queued: OperationTask = {
    id: 'task-live-001',
    tenantId: 'tenant-001',
    operationKey: 'media.derivative.generate',
    featureId: 'assets-02',
    module: 'media',
    requestSha256: '0123456789abcdef0123456789abcdef',
    requestedBy: 'user-001',
    status: 'QUEUED',
    parameters: {},
    context: {},
    risk: 'standard',
    executionState: 'contract_only',
    executorAvailable: false,
    totalCount: 1,
    succeededCount: 0,
    failedCount: 0,
    blockedCount: 0,
    canceledCount: 0,
    cancelRequested: false,
    resultSummary: {},
    createdAt: '2026-08-31T00:00:00Z',
    startedAt: null,
    completedAt: null,
    approvalDecision: null,
    approvalReason: null,
    approvedBy: null,
    decidedAt: null,
    items: [],
  }
  const canceled: OperationTask = { ...queued, status: 'CANCELED', canceledCount: 1, cancelRequested: true, completedAt: '2026-08-31T00:01:00Z' }
  const product: ProductView = { id: 'product-001', spuCode: 'SPU-001', title: '测试商品', description: '真实商品描述', category: '数码', price: '128', stock: 2, status: 'ACTIVE', revision: 3, mediaAssetIds: ['media-1'], media: [{ mediaAssetId: 'media-1', sortOrder: 0, role: 'cover' }], createdAt: '2026-08-31T00:00:00Z' }
  return {
    queuedTask: queued,
    canceledTask: canceled,
    product,
    api: {
      operationCatalog: vi.fn().mockResolvedValue([{ key: 'media.derivative.generate', module: 'media', resourceType: 'media_asset', batchAllowed: true, requiredPermission: 'content:write', allowed: true, allowedParameters: ['derivativeProfileId', 'pageParameters'], description: 'preview', risk: 'standard', featureIds: ['assets-02'] }]),
      operationTasks: vi.fn().mockResolvedValue([]),
      operationFeatureConfigDraft: vi.fn().mockResolvedValue({ featureId: 'assets-02', configuration: {}, version: 0, exists: false, createdAt: null, updatedAt: null, updatedBy: null }),
      updateOperationFeatureConfigDraft: vi.fn().mockResolvedValue({ featureId: 'assets-02', configuration: { pageParameters: { versionNote: '封面素材 v2' } }, version: 1, exists: true, createdAt: '2026-08-31T00:00:00Z', updatedAt: '2026-08-31T00:00:00Z', updatedBy: 'user-001' }),
      createOperationTask: vi.fn().mockResolvedValue(queued),
      createBatchOperation: vi.fn().mockResolvedValue(queued),
      operationTask: vi.fn().mockResolvedValue(queued),
      cancelOperationTask: vi.fn().mockResolvedValue(canceled),
      operationAuditResult: vi.fn().mockResolvedValue({ task: queued, auditEvents: [{ id: 'audit-1', actorType: 'USER', actorId: 'user-001', action: 'operation.task.created', requestId: 'request-001', result: null, beforeHash: null, afterHash: 'abc', occurredAt: '2026-08-31T00:00:00Z' }] }),
      devices: vi.fn().mockResolvedValue([]),
      products: vi.fn().mockResolvedValue([product]),
      product: vi.fn().mockResolvedValue(product),
      createProduct: vi.fn().mockResolvedValue({ ...product, id: 'product-new', revision: 1 }),
      updateProduct: vi.fn().mockResolvedValue({ ...product, revision: 4 }),
      updateProductMedia: vi.fn().mockResolvedValue({ ...product, revision: 5, media: [{ mediaAssetId: 'media-1', sortOrder: 0, role: 'cover' }, { mediaAssetId: 'media-2', sortOrder: 1, role: 'detail' }] }),
      archiveProduct: vi.fn().mockRejectedValue(Object.assign(new Error('活动发布计划引用商品'), { status: 409 })),
    },
  }
})

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  operationsMockEnabled: false,
  createControlApiClient: () => api,
}))

import OperationsView from '@/views/OperationsView.vue'

async function renderLiveOperation() {
  window.localStorage.setItem('cloudctl:operation-display-settings', JSON.stringify({ auditPanel: true, runResultBanner: true }))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/operations', component: { template: '<div>目录</div>' } },
      { path: '/operations/:moduleId/:operationId', component: OperationsView },
    ],
  })
  await router.push('/operations/assets/assets-02')
  await router.isReady()
  return render(OperationsView, { global: { plugins: [createPinia(), router] } })
}

async function renderLiveProduct(path = '/operations/product-editor/product-editor-01') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/operations/:moduleId/:operationId', component: OperationsView }],
  })
  await router.push(path)
  await router.isReady()
  const view = render(OperationsView, { global: { plugins: [createPinia(), router] } })
  return { ...view, router }
}

describe('OperationsView live Control API path', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('creates, audits and cancels a real backend task', async () => {
    await renderLiveOperation()
    await screen.findByLabelText('版本说明')
    await fireEvent.update(screen.getByLabelText('版本说明'), '封面素材 v2')
    await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))
    await waitFor(() => expect(api.updateOperationFeatureConfigDraft).toHaveBeenCalledWith(
      'assets-02',
      expect.objectContaining({
        expectedVersion: 0,
        configuration: expect.objectContaining({
          pageParameters: expect.objectContaining({ versionNote: '封面素材 v2' }),
        }),
      }),
    ))
    expect(await screen.findByText(/后端配置草稿已保存 · v1/)).toBeTruthy()
    await fireEvent.click(screen.getAllByRole('button', { name: '创建后端任务' })[0]!)
    await fireEvent.update(screen.getByPlaceholderText('填写授权依据或业务用途，写入审计'), '登记图片素材')
    await fireEvent.update(screen.getByPlaceholderText('确认授权范围'), '确认授权范围')
    await fireEvent.click(screen.getByRole('button', { name: '确认提交' }))

    await screen.findByText('后端任务已接收')
    expect(api.createOperationTask).toHaveBeenCalledWith(
      expect.objectContaining({
        operationKey: 'media.derivative.generate',
        featureId: 'assets-02',
        resourceId: 'demo-resource-001',
        parameters: {
          pageParameters: {
            assetName: '',
            assetScope: '全部内容',
            fileReference: '',
            versionNote: '封面素材 v2',
            active: true,
          },
        },
        context: expect.objectContaining({
          sourcePage: 130,
          sourceRoute: '#/set/material/image',
        }),
      }),
      expect.stringContaining('web-assets-02-'),
    )
    const submitted = api.createOperationTask.mock.calls[0]![0]
    expect(submitted.context).not.toHaveProperty('pageParameters')
    expect(submitted.parameters).not.toEqual({})
    expect(await screen.findByText('operation.task.created')).toBeTruthy()

    await fireEvent.click(screen.getByRole('button', { name: '取消任务' }))
    await waitFor(() => expect(api.cancelOperationTask).toHaveBeenCalledWith('task-live-001', { reason: '登记图片素材' }))
    expect(screen.getByText(/CANCELED/)).toBeTruthy()
    expect(canceledTask.status).toBe('CANCELED')
    expect(queuedTask.status).toBe('QUEUED')
  })

  it('passes validated page parameters to batch task creation', async () => {
    api.operationTasks.mockResolvedValueOnce([
      queuedTask,
      { ...queuedTask, id: 'task-live-002', requestSha256: 'abcdef0123456789abcdef0123456789' },
    ])
    await renderLiveOperation()
    await screen.findByLabelText('版本说明')
    await fireEvent.update(screen.getByLabelText('版本说明'), '封面素材 v3')
    const rowSelections = screen.getAllByLabelText('选择 图片素材 · task-liv')
    await fireEvent.click(rowSelections[0]!)
    await fireEvent.click(rowSelections[1]!)
    await fireEvent.click(screen.getAllByRole('button', { name: '创建后端任务' })[0]!)
    await fireEvent.update(
      screen.getByPlaceholderText('填写授权依据或业务用途，写入审计'),
      '批量登记图片素材',
    )
    await fireEvent.update(screen.getByPlaceholderText('确认授权范围'), '确认授权范围')
    await fireEvent.click(screen.getByRole('button', { name: '确认提交' }))

    await waitFor(() => expect(api.createBatchOperation).toHaveBeenCalledWith(
      expect.objectContaining({
        operationKey: 'media.derivative.generate',
        featureId: 'assets-02',
        resourceIds: ['task-live-001', 'task-live-002'],
        parameters: {
          pageParameters: {
            assetName: '',
            assetScope: '全部内容',
            fileReference: '',
            versionNote: '封面素材 v3',
            active: true,
          },
        },
      }),
      expect.stringContaining('web-assets-02-'),
    ))
  })

  it('saves an ordinary product from the dedicated editor', async () => {
    await renderLiveProduct()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.queryByText('暂无执行适配器')).toBeNull()
    await fireEvent.update(screen.getByLabelText('标题'), '南京黄金回收服务')
    await fireEvent.update(screen.getByLabelText('描述'), '说穿了，搞不清纯度？')
    await fireEvent.update(screen.getByLabelText('价格'), '1.1')
    await fireEvent.click(screen.getAllByRole('button', { name: '保存编辑' })[0]!)
    await waitFor(() => expect(api.createProduct).toHaveBeenCalledWith(expect.objectContaining({
      title: '南京黄金回收服务',
      description: '说穿了，搞不清纯度？',
      price: '1.1',
    })))
    expect(await screen.findByText('已保存编辑')).toBeTruthy()
  })

  it('loads a product from the list and opens the editor without adapter chrome', async () => {
    const { router } = await renderLiveProduct('/operations/product-management/product-management-01')
    expect(await screen.findByText('测试商品')).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.queryByText('Control API 请求未完成')).toBeNull()
    await fireEvent.click(screen.getByTitle('编辑'))
    await waitFor(() => {
      expect(router.currentRoute.value.fullPath).toBe('/operations/product-editor/product-editor-01?id=product-001')
    })
  })
})
