import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/stores/session'
import { RecipeApiError } from '@/api/recipes'
import RecipeVersionsView from '@/views/RecipeVersionsView.vue'
import { recipeFixture } from './fixtures/recipes'

const mocks = vi.hoisted(() => ({
  configured: true,
  session: vi.fn(), devices: vi.fn(), catalog: vi.fn(), detail: vi.fn(), register: vi.fn(), publish: vi.fn(), rollback: vi.fn(),
}))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return mocks.configured },
  operationsMockEnabled: false,
  createControlApiClient: () => ({ session: mocks.session, devices: mocks.devices }),
}))
vi.mock('@/api/recipes', async (original) => ({
  ...await original<typeof import('@/api/recipes')>(),
  recipeApi: { catalog: mocks.catalog, detail: mocks.detail, register: mocks.register, publish: mocks.publish, rollback: mocks.rollback },
}))

beforeEach(() => {
  vi.resetAllMocks()
  mocks.configured = true
  mocks.session.mockResolvedValue({ userId: 'operator', tenantId: 'tenant-1', roles: ['automation_developer'], mfa: true })
  mocks.devices.mockResolvedValue([{ id: 'device-1', logical_name: '测试设备' }, { id: 'device-2', logical_name: '新设备' }])
  mocks.catalog.mockResolvedValue([recipeFixture(), recipeFixture('1.0.0', 'REVOKED')])
  mocks.detail.mockImplementation(async (id) => recipeFixture(id === 'version-1.0.0' ? '1.0.0' : '2.0.0'))
  mocks.register.mockResolvedValue(recipeFixture())
  mocks.publish.mockResolvedValue(recipeFixture())
  mocks.rollback.mockResolvedValue(recipeFixture('1.0.0'))
})
afterEach(() => vi.restoreAllMocks())

function mount() {
  const pinia = createPinia()
  const view = render(RecipeVersionsView, { global: { plugins: [pinia] } })
  return { ...view, session: useSessionStore(pinia) }
}
async function loaded() { await screen.findByLabelText('版本详情') }
async function selectDevice() { await loaded(); await fireEvent.update(screen.getByLabelText('目标设备'), 'device-1') }
function noMutation() {
  expect(mocks.register).not.toHaveBeenCalled()
  expect(mocks.publish).not.toHaveBeenCalled()
  expect(mocks.rollback).not.toHaveBeenCalled()
}
async function file(text: string) {
  const input = screen.getByLabelText('已签名 JSON 文件')
  Object.defineProperty(input, 'files', { configurable: true, value: [{ name: 'signed.json', text: async () => text }] })
  await fireEvent(input, new Event('change', { bubbles: true }))
}

describe('Recipe version management page', () => {
  it('loads tenant catalog/detail and shows signing, engine, current/history and persisted actor/time without mutation', async () => {
    mount()
    await selectDevice()
    expect(mocks.catalog).toHaveBeenCalledOnce()
    expect(mocks.detail).toHaveBeenCalledWith('version-2.0.0')
    const detail = within(screen.getByLabelText('版本详情'))
    expect(detail.getByText('test-signing-key')).toBeTruthy()
    expect(detail.getByText('2')).toBeTruthy()
    expect(detail.getByText('a'.repeat(64))).toBeTruthy()
    const table = within(screen.getByRole('table'))
    expect(table.getAllByText('operator-persisted')).toHaveLength(2)
    expect(table.getByText('当前发布')).toBeTruthy()
    expect(table.getByText('已撤销 / 历史')).toBeTruthy()
    expect(table.getAllByText(new Date('2026-09-09T10:05:00Z').toLocaleString('zh-CN', { hour12: false }))).toHaveLength(2)
    await fireEvent.update(screen.getByLabelText('查看版本'), 'version-1.0.0')
    await waitFor(() => expect(mocks.detail).toHaveBeenCalledWith('version-1.0.0'))
    noMutation()
  })

  it('keeps writes disabled while catalog loads', async () => {
    let finish!: (value: ReturnType<typeof recipeFixture>[]) => void
    mocks.catalog.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    mount()
    await waitFor(() => expect(mocks.catalog).toHaveBeenCalledOnce())
    expect((screen.getByRole('button', { name: '登记签名包' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('正在加载登录态、版本与设备…')).toBeTruthy()
    noMutation()
    finish([])
    await screen.findByText('暂无已登记版本，请先登记签名包。')
  })

  it.each(['catalog', 'devices', 'detail'] as const)('shows %s read failure and blocks publishing', async (method) => {
    mocks[method].mockRejectedValue(new Error('读取失败'))
    mount()
    expect(await screen.findByText('读取失败')).toBeTruthy()
    const publish = screen.queryByRole('button', { name: '手动发布所选版本' }) as HTMLButtonElement | null
    expect(!publish || publish.disabled).toBe(true)
    noMutation()
  })

  it('denies the catalog and all writes for a viewer', async () => {
    mocks.session.mockResolvedValue({ userId: 'viewer', tenantId: 'tenant-1', roles: ['viewer'], mfa: true })
    mount()
    await screen.findByText(/需要 recipe.publish 权限/)
    expect(mocks.catalog).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('已签名 JSON 文件')).toBeNull()
    noMutation()
  })

  it('fails closed on missing API or failed session', async () => {
    mocks.configured = false
    const view = mount()
    await screen.findByText('未配置 Control API，无法管理 Recipe 版本')
    expect(mocks.session).not.toHaveBeenCalled()
    view.unmount()
    mocks.configured = true
    mocks.session.mockRejectedValue(new Error('401'))
    mount()
    await screen.findByText('登录态加载失败：401')
    expect(mocks.catalog).not.toHaveBeenCalled()
    noMutation()
  })

  it('requires separate publish confirmation and supports cancel without mutation', async () => {
    mount(); await selectDevice()
    await fireEvent.click(screen.getByRole('button', { name: '手动发布所选版本' }))
    noMutation()
    expect(screen.getByText(/目标设备：测试设备/)).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '取消' }))
    noMutation()
    await fireEvent.click(screen.getByRole('button', { name: '手动发布所选版本' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认发布' }))
    await waitFor(() => expect(mocks.publish).toHaveBeenCalledWith('version-2.0.0', { targetDeviceIds: ['device-1'], idempotencyKey: expect.any(String) }))
    await screen.findByText(/服务端已确认发布/)
    expect(mocks.publish).toHaveBeenCalledOnce()
  })

  it('rolls back only after confirmation with the captured expected current version', async () => {
    mount(); await selectDevice()
    await fireEvent.click(screen.getByRole('button', { name: '回滚到 1.0.0' }))
    noMutation()
    expect(screen.getByText(/预期当前版本：.*version-2.0.0/)).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '确认回滚' }))
    await waitFor(() => expect(mocks.rollback).toHaveBeenCalledWith('version-1.0.0', { targetDeviceIds: ['device-1'], expectedCurrentVersionId: 'version-2.0.0', idempotencyKey: expect.any(String) }))
    expect(mocks.publish).not.toHaveBeenCalled()
  })

  it('hides rollback for a device without history', async () => {
    mount(); await loaded()
    await fireEvent.update(screen.getByLabelText('目标设备'), 'device-2')
    expect(screen.queryByRole('button', { name: '回滚到 1.0.0' })).toBeNull()
    await screen.findByText('该设备暂无部署历史。')
    noMutation()
  })

  it('clears stale rollback intent after 409 and requires refresh and a new confirmation', async () => {
    mocks.rollback.mockRejectedValue(new RecipeApiError(409, '版本状态冲突'))
    mount(); await selectDevice()
    await fireEvent.click(screen.getByRole('button', { name: '回滚到 1.0.0' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认回滚' }))
    await screen.findByText(/版本状态冲突/)
    expect(screen.queryByRole('button', { name: '确认回滚' })).toBeNull()
    expect(mocks.rollback).toHaveBeenCalledOnce()
    await fireEvent.click(screen.getByRole('button', { name: '刷新版本与设备' }))
    await loaded()
    expect(mocks.rollback).toHaveBeenCalledOnce()
  })

  it('reuses the same idempotency key on explicit retry and prevents duplicate in-flight submits', async () => {
    mocks.publish.mockRejectedValueOnce(new Error('网络中断'))
    mount(); await selectDevice()
    await fireEvent.click(screen.getByRole('button', { name: '手动发布所选版本' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认发布' }))
    await screen.findByText('网络中断')
    const first = mocks.publish.mock.calls[0]
    let finish!: (value: ReturnType<typeof recipeFixture>) => void
    mocks.publish.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    await fireEvent.click(screen.getByRole('button', { name: '确认发布' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认发布' }))
    expect(mocks.publish).toHaveBeenCalledTimes(2)
    expect(mocks.publish.mock.calls[1]).toEqual(first)
    finish(recipeFixture())
    await screen.findByText(/服务端已确认发布/)
  })

  it('rechecks permission before confirmation when the session changes', async () => {
    const { session } = mount(); await selectDevice()
    await fireEvent.click(screen.getByRole('button', { name: '手动发布所选版本' }))
    session.permissions = ['device.read']
    await screen.findByText(/需要 recipe.publish 权限/)
    expect(screen.queryByRole('button', { name: '确认发布' })).toBeNull()
    noMutation()
  })

  it('blocks further actions after a backend permission rejection', async () => {
    mocks.publish.mockRejectedValue(new RecipeApiError(403, '权限不足'))
    mount(); await selectDevice()
    await fireEvent.click(screen.getByRole('button', { name: '手动发布所选版本' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认发布' }))
    await screen.findByText(/需要 recipe.publish 权限/)
    expect(mocks.publish).toHaveBeenCalledOnce()
    expect(screen.queryByLabelText('已签名 JSON 文件')).toBeNull()
  })

  it('previews a file without uploading then explicitly registers without publishing', async () => {
    mount(); await loaded()
    const signed = recipeFixture().package
    await file(JSON.stringify(signed))
    await screen.findByLabelText('待登记清单')
    noMutation()
    await fireEvent.click(screen.getByRole('button', { name: '登记签名包' }))
    await waitFor(() => expect(mocks.register).toHaveBeenCalledWith(signed))
    await screen.findByText(/尚未发布到设备/)
    expect(mocks.publish).not.toHaveBeenCalled()
    expect(mocks.rollback).not.toHaveBeenCalled()
  })

  it('rejects malformed files and surfaces server signature rejection without publishing', async () => {
    mount(); await loaded()
    await file('{')
    await screen.findByText('文件不是有效的 JSON')
    expect((screen.getByRole('button', { name: '登记签名包' }) as HTMLButtonElement).disabled).toBe(true)
    noMutation()
    mocks.register.mockRejectedValue(new RecipeApiError(422, '签名验证失败'))
    await file(JSON.stringify(recipeFixture().package))
    await screen.findByLabelText('待登记清单')
    await fireEvent.click(screen.getByRole('button', { name: '登记签名包' }))
    await screen.findByText('签名验证失败')
    expect(screen.queryByText(/已登记版本/)).toBeNull()
    expect(mocks.publish).not.toHaveBeenCalled()
  })
})
