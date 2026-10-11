import { createPinia } from 'pinia'
import { fireEvent, render, screen } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { collectImBody, ImApiError, listImBodyCollections, type ImBodyCollections, type ImBodySnapshot, type ImThread } from '@/api/im'
import BodyCollectionPanel from '@/features/im/BodyCollectionPanel.vue'
import { useSessionStore } from '@/stores/session'
vi.mock('@/api/im', async (original) => ({ ...await original<typeof import('@/api/im')>(), collectImBody: vi.fn(), listImBodyCollections: vi.fn() }))
const thread: ImThread = { id: 'thread-1', deviceId: 'phone-1', platform: 'xianyu', peerKey: 'peer', peerName: '买家甲', lastMessageAt: '', lastDirection: 'IN', unreadCount: 0, lastMessageText: '原始通知' }
const page = (): ImBodyCollections => ({ capability: { supported: true, available: true, reason: null }, items: [] })
const snapshot = (): ImBodySnapshot => ({ capturedAt: '2026-10-11T10:00:00Z', scope: 'VISIBLE_SCREEN', completeness: 'VISIBLE_ONLY', accountIdentity: 'UNVERIFIED', peerIdentity: { status: 'DISPLAY_NAME_MATCH', observedName: '买家甲', basis: 'CHAT_HEADER' }, messages: [], truncated: false })
function setup(permission = true) {
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.user = { id: 'user', tenant: 'tenant', name: 'User' }
  session.permissions = permission ? ['device.control'] : []
  const view = render(BodyCollectionPanel, { props: { thread, deviceLabel: '一加手机' }, global: { plugins: [pinia] } })
  return { ...view, session }
}
async function prepare() { await flushPromises(); await fireEvent.click(screen.getByRole('button', { name: '读取当前可见正文' })) }
async function submit() { await fireEvent.click(screen.getByRole('button', { name: '确认读取当前可见正文' })) }
beforeEach(() => { vi.mocked(listImBodyCollections).mockResolvedValue(page()); vi.mocked(collectImBody).mockResolvedValue({ taskId: 'task', threadId: thread.id, status: 'QUEUED' }) })
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })
describe('manual visible body collection', () => {
  it('requires explicit target confirmation and never posts on selection or refresh', async () => {
    setup(); await flushPromises()
    expect(collectImBody).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('button', { name: '刷新读取状态' }))
    await prepare()
    const confirmation = screen.getByRole('region', { name: '确认读取正文' })
    for (const label of ['一加手机', 'phone-1', '闲鱼', '买家甲', '账号：未核验', '可能将会话标为已读', '不输入、不发送', '不开启值班']) expect(confirmation.textContent).toContain(label)
    expect(collectImBody).not.toHaveBeenCalled()
    await submit(); expect(collectImBody).toHaveBeenCalledTimes(1)
  })
  it.each([
    [false, true, true, '当前角色无设备控制权限'],
    [true, false, true, '设备尚不支持正文读取'],
    [true, true, false, '设备当前不可读取'],
  ])('gates permission=%s supported=%s available=%s', async (permission, supported, available, text) => {
    vi.mocked(listImBodyCollections).mockResolvedValue({ capability: { supported, available, reason: 'OFFLINE' }, items: [] })
    setup(permission); await flushPromises()
    expect(screen.getByText(text, { exact: false })).toBeTruthy()
    expect((screen.getByRole('button', { name: '读取当前可见正文' }) as HTMLButtonElement).disabled).toBe(true)
    expect(collectImBody).not.toHaveBeenCalled()
  })
  it('handles old cloud 404 without breaking the panel', async () => {
    vi.mocked(listImBodyCollections).mockRejectedValue(new ImApiError(404, 'missing'))
    setup(); await flushPromises(); expect(screen.getByText('云端尚不支持正文读取')).toBeTruthy()
    expect(collectImBody).not.toHaveBeenCalled()
  })
  it('prevents duplicate submit and reuses the idempotency key after uncertain failure', async () => {
    let reject!: (error: Error) => void
    vi.mocked(collectImBody).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    setup(); await prepare(); await submit(); await submit()
    expect(collectImBody).toHaveBeenCalledTimes(1)
    const key = vi.mocked(collectImBody).mock.calls[0][1]
    reject(new Error('network')); await flushPromises(); await submit()
    expect(vi.mocked(collectImBody).mock.calls[1][1]).toBe(key)
  })
  it('labels an empty mobile snapshot honestly', async () => {
    vi.mocked(listImBodyCollections).mockResolvedValue({ ...page(), items: [{ taskId: 'task', threadId: thread.id, status: 'SUCCEEDED', createdAt: '', errorCode: null, snapshot: snapshot() }] })
    setup(); await flushPromises()
    const panel = screen.getByRole('region', { name: '本次读取的可见正文' })
    for (const label of ['手机无障碍可见文字', '非完整聊天历史', '读取时间', '原消息时间：未知', '账号：未核验', '仅标题匹配', '方向根据气泡位置推测', '本次未读取到可见文字']) expect(panel.textContent).toContain(label)
  })
  it('shows truncation and geometry-derived directions without modifying messages', async () => {
    const value = snapshot(); value.truncated = true; value.messages = [{ direction: 'IN', text: '可见正文', visibleOrder: 0, occurredAt: null }, { direction: 'OUT', text: '另一条', visibleOrder: 1, occurredAt: null }]
    vi.mocked(listImBodyCollections).mockResolvedValue({ ...page(), items: [{ taskId: 'task', threadId: thread.id, status: 'SUCCEEDED', createdAt: '', errorCode: null, snapshot: value }] })
    setup(); await flushPromises()
    expect(screen.getByText('内容达到读取上限，已截断。')).toBeTruthy(); expect(screen.getByText('推测收到')).toBeTruthy(); expect(screen.getByText('推测发出')).toBeTruthy()
    expect(thread.lastMessageText).toBe('原始通知')
  })
  it.each(['identity', 'thread', 'unmount'])('discards stale query after %s change', async (change) => {
    let resolve!: (value: ImBodyCollections) => void
    vi.mocked(listImBodyCollections).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const view = setup()
    if (change === 'identity') view.session.user = { id: 'other', tenant: 'other', name: 'Other' }
    if (change === 'thread') await view.rerender({ thread: { ...thread, id: 'thread-2' } })
    if (change === 'unmount') view.unmount()
    await flushPromises()
    resolve({ ...page(), items: [{ taskId: 'old', threadId: thread.id, status: 'SUCCEEDED', createdAt: '', errorCode: null, snapshot: snapshot() }] })
    await flushPromises(); expect(screen.queryByRole('region', { name: '本次读取的可见正文' })).toBeNull()
  })
  it('polls only pending reads and stops on completion and unmount', async () => {
    vi.useFakeTimers()
    const pending = { ...page(), items: [{ taskId: 'task', threadId: thread.id, status: 'RUNNING', createdAt: '', errorCode: null, snapshot: null }] }
    vi.mocked(listImBodyCollections).mockResolvedValueOnce(pending).mockResolvedValue(page())
    const view = setup(); await flushPromises(); await vi.advanceTimersByTimeAsync(3000); await flushPromises()
    expect(listImBodyCollections).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(9000); expect(listImBodyCollections).toHaveBeenCalledTimes(2)
    view.unmount(); await vi.advanceTimersByTimeAsync(6000); expect(listImBodyCollections).toHaveBeenCalledTimes(2)
    expect(collectImBody).not.toHaveBeenCalled()
  })
})

it('ignores a late submission after identity change and clears confirmation', async () => {
  let resolve!: (value: { taskId: string; threadId: string; status: string }) => void
  vi.mocked(collectImBody).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  const view = setup(); await prepare(); await submit()
  view.session.user = { id: 'other', tenant: 'other', name: 'Other' }
  await flushPromises()
  resolve({ taskId: 'old-task', threadId: thread.id, status: 'RUNNING' }); await flushPromises()
  expect(screen.queryByRole('region', { name: '确认读取正文' })).toBeNull()
  expect(screen.queryByText('最近读取任务：正在读取')).toBeNull()
  expect(collectImBody).toHaveBeenCalledTimes(1)
})
it('suspends pending polling while hidden and removes timers on unmount', async () => {
  vi.useFakeTimers()
  vi.mocked(listImBodyCollections).mockResolvedValue({ ...page(), items: [{ taskId: 'task', threadId: thread.id, status: 'RUNNING', createdAt: '', errorCode: null, snapshot: null }] })
  const visibility = vi.spyOn(document, 'visibilityState', 'get')
  const view = setup(); await flushPromises()
  visibility.mockReturnValue('hidden'); document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(9000); expect(listImBodyCollections).toHaveBeenCalledTimes(1)
  visibility.mockReturnValue('visible'); document.dispatchEvent(new Event('visibilitychange')); await flushPromises()
  expect(listImBodyCollections).toHaveBeenCalledTimes(2)
  view.unmount(); await vi.advanceTimersByTimeAsync(9000); expect(listImBodyCollections).toHaveBeenCalledTimes(2)
  visibility.mockRestore()
})
it('keeps a confirmation stable when inbox polling replaces the same thread object', async () => {
  const view = setup(); await prepare()
  await view.rerender({ thread: { ...thread, unreadCount: 3 } }); await flushPromises()
  expect(screen.getByRole('region', { name: '确认读取正文' })).toBeTruthy()
  expect(listImBodyCollections).toHaveBeenCalledTimes(1)
  expect(collectImBody).not.toHaveBeenCalled()
})
it.each(['RUNNING', 'FAILED'])('labels an older successful snapshot when the latest task is %s', async (status) => {
  vi.mocked(listImBodyCollections).mockResolvedValue({ ...page(), items: [
    { taskId: 'new', threadId: thread.id, status, createdAt: '', errorCode: 'PRIVATE_CODE', snapshot: null },
    { taskId: 'old', threadId: thread.id, status: 'SUCCEEDED', createdAt: '', errorCode: null, snapshot: snapshot() },
  ] })
  setup(); await flushPromises()
  expect(screen.getByRole('region', { name: '上次读取的可见正文' })).toBeTruthy()
  expect(screen.queryByRole('region', { name: '本次读取的可见正文' })).toBeNull()
  expect(screen.queryByText('PRIVATE_CODE')).toBeNull()
  expect(screen.queryByText('UNVERIFIED')).toBeNull()
})
it.each([
  { supported: 'true', available: true },
  { supported: true, available: 'true' },
  { supported: true },
  {},
])('fails closed on malformed capability %j', async (capability) => {
  vi.mocked(listImBodyCollections).mockResolvedValue({ capability, items: [] } as unknown as ImBodyCollections)
  setup(); await flushPromises()
  expect((screen.getByRole('button', { name: '读取当前可见正文' }) as HTMLButtonElement).disabled).toBe(true)
  expect(collectImBody).not.toHaveBeenCalled()
})
it('keeps polling through PREFLIGHT and RUNNING until SUCCEEDED', async () => {
  vi.useFakeTimers()
  const state = (status: string): ImBodyCollections => ({ ...page(), items: [{ taskId: 'task', threadId: thread.id, status, createdAt: '', errorCode: null, snapshot: status === 'SUCCEEDED' ? snapshot() : null }] })
  vi.mocked(listImBodyCollections).mockResolvedValueOnce(state('PREFLIGHT')).mockResolvedValueOnce(state('RUNNING')).mockResolvedValue(state('SUCCEEDED'))
  setup(); await flushPromises()
  expect((screen.getByRole('button', { name: '读取当前可见正文' }) as HTMLButtonElement).disabled).toBe(true)
  await vi.advanceTimersByTimeAsync(3000); await flushPromises()
  expect((screen.getByRole('button', { name: '读取当前可见正文' }) as HTMLButtonElement).disabled).toBe(true)
  await vi.advanceTimersByTimeAsync(3000); await flushPromises()
  expect(screen.getByRole('region', { name: '本次读取的可见正文' })).toBeTruthy()
  await vi.advanceTimersByTimeAsync(6000)
  expect(listImBodyCollections).toHaveBeenCalledTimes(3); expect(collectImBody).not.toHaveBeenCalled()
})
it.each(['PAUSED_WAITING_USER', 'RESUME_CHECK', 'RECONCILING', 'PAUSE_REQUESTED', 'CANCEL_REQUESTED', 'WAITING_MATERIALS'])('keeps %s pending and prevents another collection', async (status) => {
  vi.useFakeTimers()
  vi.mocked(listImBodyCollections).mockResolvedValue({ ...page(), items: [{ taskId: 'task', threadId: thread.id, status, createdAt: '', errorCode: null, snapshot: null }] })
  setup(); await flushPromises()
  expect((screen.getByRole('button', { name: '读取当前可见正文' }) as HTMLButtonElement).disabled).toBe(true)
  await vi.advanceTimersByTimeAsync(3000); await flushPromises()
  expect(listImBodyCollections).toHaveBeenCalledTimes(2); expect(collectImBody).not.toHaveBeenCalled()
})
it.each([
  ['IM_COLLECTION_NO_BINDING', false, '没有有效手机绑定'],
  ['IM_COLLECTION_UNSUPPORTED', false, '手机端尚不支持正文读取协议'],
  ['IM_COLLECTION_OFFLINE', true, '手机离线'],
  ['IM_COLLECTION_NOT_EXECUTABLE', true, '手机当前不满足任务执行条件'],
])('explains actual server capability reason %s without exposing codes', async (reason, supported, explanation) => {
  vi.mocked(listImBodyCollections).mockResolvedValue({ capability: { supported, available: false, reason }, items: [] })
  const view = setup(); await flushPromises()
  expect(screen.getByText(explanation, { exact: false })).toBeTruthy()
  expect(view.container.textContent).not.toContain(reason)
  const button = screen.getByRole('button', { name: '读取当前可见正文' }) as HTMLButtonElement
  expect(button.disabled).toBe(true)
  await fireEvent.click(button)
  expect(collectImBody).not.toHaveBeenCalled()
})
