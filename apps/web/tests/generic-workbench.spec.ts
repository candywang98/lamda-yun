import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mock = vi.hoisted(() => ({ api: {
  operationCatalog: vi.fn(), operationTasks: vi.fn(), operationFeatureConfigDraft: vi.fn(), devices: vi.fn(),
  createOperationTask: vi.fn(), createBatchOperation: vi.fn(), updateOperationFeatureConfigDraft: vi.fn(),
} }))
vi.mock('@/api/control', () => ({ controlApiConfigured: true, operationsMockEnabled: false, createControlApiClient: () => mock.api }))
import OperationsView from '@/views/OperationsView.vue'
const catalog = { key: 'media.derivative.generate', module: 'media', resourceType: 'media_asset', batchAllowed: true, allowed: true, allowedParameters: ['pageParameters'], risk: 'standard', featureIds: ['assets-02'] }
async function mount(path = '/operations/assets/assets-02') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/operations/:moduleId/:operationId', component: OperationsView }] })
  await router.push(path); await router.isReady()
  return render(OperationsView, { global: { plugins: [createPinia(), router] } })
}
beforeEach(() => {
  vi.resetAllMocks(); window.localStorage.clear()
  mock.api.operationCatalog.mockResolvedValue([catalog])
  mock.api.operationTasks.mockResolvedValue([])
  mock.api.operationFeatureConfigDraft.mockResolvedValue({ exists: false, version: 0, configuration: {} })
  mock.api.devices.mockResolvedValue([{ id: 'real-device-1', logical_name: '授权手机甲' }])
})
describe('generic workbench truthful production UI', () => {
  it('does not restore invented execution targets from a historical draft', async () => {
    mock.api.operationFeatureConfigDraft.mockResolvedValue({ exists: true, version: 1, configuration: {
      deviceScope: '在线且兼容的授权设备（3 台）', resourceIds: 'demo-resource-001', snapshot: 'catalog-demo/revision-1',
      executionApp: '副应用', schedule: '2026-08-31 09:00',
    } })
    await mount('/operations/chat/chat-01')
    await screen.findByRole('option', { name: '授权手机甲 · real-device-1' })
    expect((screen.getByLabelText('执行设备') as HTMLSelectElement).value).toBe('')
    expect((screen.getByLabelText('实际资源 ID') as HTMLTextAreaElement).value).toBe('')
    expect((screen.getByLabelText('执行时间') as HTMLSelectElement).value).toBe('立即执行（加入队列）')
    expect(mock.api.createOperationTask).not.toHaveBeenCalled()
  })
  it('requires explicit resources, shows actual devices and excludes fake media and claims', async () => {
    await mount()
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新数据' }).hasAttribute('disabled')).toBe(false))
    expect(screen.getByText('配置预览')).toBeTruthy()
    expect((screen.getByLabelText('实际资源 ID') as HTMLTextAreaElement).value).toBe('')
    expect(screen.getByRole('button', { name: '创建后端任务' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText('请填写实际资源 ID；历史任务 ID 不作为资源目标')).toBeTruthy()
    expect(screen.queryByText('brand-cover-01.jpg')).toBeNull()
    expect(screen.queryByText('杭州-内容-023')).toBeNull()
    expect(screen.getByRole('option', { name: '授权手机甲' })).toBeTruthy()
    expect(screen.getByRole('link', { name: '打开媒体资产工作台' }).getAttribute('href')).toBe('/media-assets')
    await fireEvent.update(screen.getByLabelText('实际资源 ID'), 'media-user-selected')
    expect(screen.getByRole('button', { name: '创建后端任务' }).hasAttribute('disabled')).toBe(false)
    expect(mock.api.createOperationTask).not.toHaveBeenCalled()
  })
  it('uses actual task parameters for detail rather than the current configuration', async () => {
    mock.api.operationTasks.mockResolvedValue([{ id: 'history-1', operationKey: catalog.key, module: 'media', context: { deviceScope: 'real-device-1', actual: '服务端上下文' }, parameters: { recorded: '服务端参数' }, status: 'FAILED', totalCount: 1, requestedBy: 'operator', createdAt: '2026-09-30T01:00:00Z' }])
    await mount()
    await fireEvent.update(screen.getByLabelText('版本说明'), '当前未提交草稿')
    await fireEvent.click(await screen.findByRole('button', { name: '查看' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/服务端参数/)).toBeTruthy()
    expect(dialog.textContent).not.toContain('当前未提交草稿')
    expect(dialog.textContent).not.toContain('来源页面')
    expect(dialog.textContent).not.toContain('页面参数快照')
    expect(screen.queryByLabelText('选择当前筛选全部记录')).toBeNull()
    await fireEvent.click(within(dialog).getByRole('button', { name: '关闭详情' }))
    await fireEvent.update(screen.getByLabelText('设备筛选'), 'real-device-1')
    expect(screen.getByRole('button', { name: '查看' })).toBeTruthy()
    await fireEvent.update(screen.getByLabelText('状态筛选'), 'FAILED')
    expect(screen.getByRole('button', { name: '查看' })).toBeTruthy()
    await fireEvent.update(screen.getByLabelText('筛选当前功能记录'), 'non-matching')
    expect(screen.getByText('没有符合筛选条件的记录')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '还原筛选' }))
    expect(screen.getByRole('button', { name: '查看' })).toBeTruthy()
  })
  it('offers guide navigation without save, reset, task creation or copied source workflow', async () => {
    await mount('/operations/system-home/system-home-04')
    expect(screen.getByText(/CloudCtl 使用入口/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '保存配置' })).toBeNull()
    expect(screen.queryByRole('button', { name: '重置' })).toBeNull()
    expect(screen.queryByRole('button', { name: /任务|已读/ })).toBeNull()
    expect(screen.getByRole('link', { name: '设备总览' }).getAttribute('href')).toBe('/fleet')
    expect(screen.getByRole('link', { name: '内容导入导出' }).getAttribute('href')).toBe('/content-io')
    expect(mock.api.operationCatalog).not.toHaveBeenCalled()
  })
  it('removes fixed task devices, unsupported app choices and a fake timer', async () => {
    await mount('/operations/chat/chat-01')
    await screen.findByRole('option', { name: '授权手机甲 · real-device-1' })
    expect((screen.getByLabelText('执行设备') as HTMLSelectElement).value).toBe('')
    expect(screen.queryByRole('option', { name: '副应用' })).toBeNull()
    expect(screen.queryByRole('option', { name: '2026-08-31 09:00' })).toBeNull()
    expect(screen.queryByText(/仅北京实验设备|授权设备（3 台）/)).toBeNull()
    await fireEvent.update(screen.getByLabelText('执行时间'), '仅保存配置')
    expect(screen.getByText('当前选择仅保存配置，不会创建执行任务')).toBeTruthy()
  })
  it('keeps blocked and unconfirmed mappings closed with visible reasons', async () => {
    await mount('/operations/red-tasks/red-tasks-04')
    expect(await screen.findByText('生产策略明确阻断该能力')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: '策略已阻断' }).every(button => button.hasAttribute('disabled'))).toBe(true)
    expect(mock.api.createOperationTask).not.toHaveBeenCalled()
  })
  it('keeps a mismatched backend mapping closed after entering resource IDs', async () => {
    mock.api.operationCatalog.mockResolvedValue([{ ...catalog, featureIds: [] }])
    await mount()
    await screen.findByText('后端目录未确认该 featureId 与风险映射')
    await fireEvent.update(screen.getByLabelText('实际资源 ID'), 'real-media')
    expect(screen.getByRole('button', { name: '创建后端任务' }).hasAttribute('disabled')).toBe(true)
  })
  it('shows no fabricated insight trend in live mode', async () => {
    await mount('/operations/analytics/analytics-02')
    expect(screen.queryByLabelText('模拟运营趋势图')).toBeNull()
    expect(screen.getByText(/本页尚未接入运营趋势数据/)).toBeTruthy()
  })
  it('shows loading, failed retry and then a true empty state', async () => {
    let reject!: (error: Error) => void
    mock.api.operationTasks.mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail }))
    await mount()
    expect(screen.getByText('正在加载配置与任务记录…')).toBeTruthy()
    expect(screen.queryByText('暂无任务记录')).toBeNull()
    reject(new Error('offline'))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('offline'))
    await fireEvent.click(screen.getByRole('button', { name: '刷新数据' }))
    expect(await screen.findByText('暂无任务记录')).toBeTruthy()
    expect(mock.api.operationTasks).toHaveBeenCalledTimes(2)
  })
})
