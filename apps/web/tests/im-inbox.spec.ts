import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchImConfig,
  classifyImMessage,
  reclassifyImMessage,
  listImMessages,
  listImThreads,
  markImThreadRead,
  replyImThread,
  saveImConfig,
  ImApiError,
  type ImMessage,
  type ImMonitorConfig,
  type ImThread,
  type ImThreadPage,
  type ImClassification,
} from '@/api/im'
import { useSessionStore } from '@/stores/session'
import ImInboxView from '@/views/ImInboxView.vue'

const deviceReads = vi.hoisted(() => ({ pending: vi.fn() }))

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  operationsMockEnabled: false,
  createControlApiClient: () => ({
    devices: () => deviceReads.pending() ?? Promise.resolve([
      { id: 'dev-alpha-0001', logical_name: '一加 9R', state: 'REGISTERED' },
      { id: 'dev-huawei-vog', logical_name: '华为 VOG', state: 'REGISTERED' },
      { id: 'dev-huawei-ele', logical_name: '华为 ELE', state: 'REGISTERED' },
    ]),
  }),
}))

vi.mock('@/api/runtime-mode', () => ({
  controlApiConfigured: true,
  operationsMockEnabled: false,
  runtimeDataMode: 'api',
  localBusinessDataAllowed: () => false,
  requireApiMode: () => undefined,
  requireWritableApi: () => undefined,
}))

vi.mock('@/api/im', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/im')>()
  return {
    ...actual,
    listImThreads: vi.fn(),
    listImMessages: vi.fn(),
    listImBodyCollections: vi.fn().mockResolvedValue({ capability: { supported: true, available: true, reason: null }, items: [] }),
    collectImBody: vi.fn(),
    markImThreadRead: vi.fn(),
    replyImThread: vi.fn(),
    fetchImConfig: vi.fn(),
    saveImConfig: vi.fn(),
    classifyImMessage: vi.fn(),
    reclassifyImMessage: vi.fn(),
  }
})

function threadFixture(overrides: Partial<ImThread> = {}): ImThread {
  return {
    id: 'thread-1',
    deviceId: 'dev-alpha-0001',
    platform: 'xianyu',
    peerKey: '买家小王',
    peerName: '买家小王',
    lastMessageAt: '2026-09-14T10:00:00.000Z',
    lastDirection: 'IN',
    unreadCount: 2,
    lastMessageText: null,
    ...overrides,
  }
}

function messageFixture(text: string, overrides: Partial<ImMessage> = {}): ImMessage {
  return {
    id: 'm-1',
    threadId: 'thread-1',
    direction: 'IN',
    contentType: 'TEXT',
    text,
    occurredAt: '2026-09-14T09:59:00.000Z',
    replyTaskId: null,
    ...overrides,
  }
}

function configFixture(overrides: Partial<ImMonitorConfig> = {}): ImMonitorConfig {
  return {
    deviceId: 'dev-alpha-0001',
    enabled: true,
    platforms: ['xianyu'],
    mode: 'NOTIFICATION',
    dutyStart: '09:00',
    dutyEnd: '23:00',
    updatedAt: '2026-09-14T08:00:00.000Z',
    ...overrides,
  }
}

function pageFixture(items = [threadFixture()], bucketCounts: ImThreadPage['bucketCounts'] = { all: 13, user: 8, notice: 5, review: 3 }): ImThreadPage {
  return { items, count: items.length, bucketCounts }
}

function classificationFixture(overrides: Partial<ImClassification> = {}): ImClassification {
  return {
    category: 'UNKNOWN', predictedCategory: null, confidence: null, source: 'UNCLASSIFIED',
    status: 'UNCLASSIFIED', modelStatus: null, ruleCode: null, reviewedAt: null, reviewedBy: null,
    version: 0, ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

describe('ImInboxView', () => {
  beforeEach(() => {
    deviceReads.pending.mockReset()
    vi.mocked(listImThreads).mockReset().mockResolvedValue(pageFixture([
      threadFixture({ lastMessageText: '一加上的入站正文' }),
      threadFixture({
        id: 'thread-2', deviceId: 'dev-huawei-vog', peerName: '华为买家', unreadCount: 0,
        lastMessageText: 'VOG 入站正文', lastMessageAt: '2026-09-14T09:30:00.000Z',
      }),
      threadFixture({
        id: 'thread-3', deviceId: 'dev-huawei-ele', peerName: '另一位买家', unreadCount: 1,
        lastMessageText: 'ELE 入站正文', lastMessageAt: '2026-09-14T09:00:00.000Z',
      }),
    ]))
    vi.mocked(fetchImConfig).mockReset().mockImplementation(async (deviceId: string) => configFixture({ deviceId }))
    vi.mocked(saveImConfig).mockReset()
    vi.mocked(listImMessages).mockReset()
    vi.mocked(markImThreadRead).mockReset().mockResolvedValue(undefined)
    vi.mocked(replyImThread).mockReset()
    vi.mocked(classifyImMessage).mockReset()
    vi.mocked(reclassifyImMessage).mockReset()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function renderView(roles: string[]) {
    const pinia = createPinia()
    const session = useSessionStore(pinia)
    session.applySession({ userId: 'user-1', tenantId: 'tenant-1', roles, mfa: true, requestId: 'req-1' })
    return render(ImInboxView, { global: { plugins: [pinia] } })
  }


  it('shows placeholders, raw text and honest delivery states without treating ordinary text as a preview', async () => {
    vi.mocked(listImMessages).mockResolvedValue([
      messageFixture('发来一条新消息'),
      messageFixture('你好\n还在吗', { id: 'real' }),
      ...[undefined, 'PENDING', 'DELIVERED', 'FAILED'].map((deliveryState, index) => messageFixture('回复' + index, { id: 'out' + index, direction: 'OUT', deliveryState: deliveryState as ImMessage['deliveryState'] })),
    ])
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    expect(await screen.findByText('通知提示 · 正文待采集')).toBeTruthy()
    expect(screen.getByText('发来一条新消息')).toBeTruthy()
    expect(screen.getByText('你好 还在吗').textContent).toBe('你好\n还在吗')
    expect(screen.getByText('发送状态未知')).toBeTruthy()
    expect(screen.getByText('等待手机确认')).toBeTruthy()
    expect(screen.getByText(/手机报告发送完成/)).toBeTruthy()
    expect(screen.getByText(/回复任务失败/)).toBeTruthy()
    expect(screen.getByText(/账号：未核验/)).toBeTruthy()
  })

  it.each([undefined, true])('fails closed with receiveOnly=%s and keeps a visible disabled composer', async (receiveOnly) => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly }))
    vi.mocked(listImMessages).mockResolvedValue([])
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).disabled).toBe(true)
    expect(screen.getByText(/只读收件箱/)).toBeTruthy()
    expect(replyImThread).not.toHaveBeenCalled()
  })

  it.each(['permission', 'platform', 'config'])('explains the %s reply gate', async (gate) => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => {
      if (gate === 'config') throw new Error('unavailable')
      return configFixture({ deviceId, receiveOnly: false })
    })
    vi.mocked(listImThreads).mockResolvedValue(pageFixture([threadFixture({ platform: gate === 'platform' ? 'xhs' : 'xianyu' })]))
    vi.mocked(listImMessages).mockResolvedValue([])
    await renderView(gate === 'permission' ? ['viewer'] : ['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).disabled).toBe(true)
    expect(screen.getByText(/只读收件箱/).textContent).toContain({ permission: '没有设备回复权限', platform: '此平台暂不支持', config: '回复配置尚未核验' }[gate]!)
  })

  it('searches only loaded names, devices and summaries', async () => {
    await renderView(['viewer'])
    await screen.findByRole('button', { name: /买家小王/ })
    await fireEvent.update(screen.getByRole('searchbox'), 'VOG 入站正文')
    expect(screen.getByRole('button', { name: /华为买家/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /买家小王/ })).toBeNull()
    expect(screen.getByText(/搜索仅覆盖已加载会话/)).toBeTruthy()
  })

  it('pins the explicit reply target and protects another device draft while a request is pending', async () => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: false }))
    vi.mocked(listImThreads).mockResolvedValue(pageFixture([
      threadFixture(), threadFixture({ id: 'thread-2', deviceId: 'dev-huawei-vog' }),
    ]))
    vi.mocked(listImMessages).mockResolvedValue([])
    const pending = deferred<{ taskId: string }>()
    vi.mocked(replyImThread).mockReturnValue(pending.promise)
    await renderView(['device_operator'])
    const buttons = await screen.findAllByRole('button', { name: /买家小王/ })
    expect(buttons[0]!.textContent).toContain('一加 9R')
    expect(buttons[1]!.textContent).toContain('华为 VOG')
    await fireEvent.click(buttons[1]!)
    await fireEvent.update(screen.getByRole('textbox', { name: '回复内容' }), '第二台草稿')
    await fireEvent.click(buttons[0]!)
    const textarea = screen.getByRole('textbox', { name: '回复内容' })
    await fireEvent.update(textarea, '第一台回复')
    await fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })
    expect(replyImThread).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('button', { name: '核对回复' }))
    expect(screen.getByRole('region', { name: '确认回复' }).textContent).toContain('一加 9R · 闲鱼 · 买家小王')
    const submit = screen.getByRole('button', { name: '确认提交回复任务' })
    await fireEvent.click(submit)
    await fireEvent.click(submit)
    expect(replyImThread).toHaveBeenCalledTimes(1)
    expect(replyImThread).toHaveBeenCalledWith('thread-1', '第一台回复')
    await fireEvent.click(buttons[1]!)
    pending.resolve({ taskId: 'task-1' })
    await flushPromises()
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).value).toBe('第二台草稿')
    expect(screen.queryByText(/任务已提交/)).toBeNull()
    await fireEvent.click(buttons[0]!)
    expect(screen.getByRole('status').textContent).toContain('一加 9R · 闲鱼 · 买家小王：任务已提交')
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).value).toBe('')
  })

  it('preserves the draft when the same identity session is refreshed', async () => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: false }))
    vi.mocked(listImMessages).mockResolvedValue([])
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    await fireEvent.update(screen.getByRole('textbox', { name: '回复内容' }), '刷新后保留草稿')
    useSessionStore().applySession({ userId: 'user-1', tenantId: 'tenant-1', roles: ['device_operator'], mfa: true, requestId: 'refreshed-session' })
    await flushPromises()
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).value).toBe('刷新后保留草稿')
  })

  it.each(['user', 'tenant'])('discards pending reply results and drafts after a %s change', async (change) => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: false }))
    vi.mocked(listImMessages).mockResolvedValue([])
    const pending = deferred<{ taskId: string }>()
    vi.mocked(replyImThread).mockReturnValue(pending.promise)
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    await fireEvent.update(screen.getByRole('textbox', { name: '回复内容' }), '相同草稿')
    await fireEvent.click(screen.getByRole('button', { name: '核对回复' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认提交回复任务' }))
    useSessionStore().applySession({ userId: change === 'user' ? 'user-2' : 'user-1', tenantId: change === 'tenant' ? 'tenant-2' : 'tenant-1', roles: ['device_operator'], mfa: true, requestId: 'req-2' })
    await flushPromises()
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).value).toBe('')
    await fireEvent.update(screen.getByRole('textbox', { name: '回复内容' }), '相同草稿')
    await fireEvent.click(screen.getByRole('button', { name: '核对回复' }))
    pending.resolve({ taskId: 'old-session-task' })
    await flushPromises()
    expect(screen.queryByText(/任务已提交/)).toBeNull()
    expect(screen.getByRole('region', { name: '确认回复' })).toBeTruthy()
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).value).toBe('相同草稿')
  })

  it('ignores device names returned after the tenant changes', async () => {
    const oldDevices = deferred<unknown[]>()
    deviceReads.pending.mockReturnValueOnce(oldDevices.promise)
    await renderView(['viewer'])
    useSessionStore().applySession({ userId: 'user-1', tenantId: 'tenant-2', roles: ['viewer'], mfa: true, requestId: 'req-2' })
    await flushPromises()
    oldDevices.resolve([{ id: 'old-tenant-device', logical_name: '旧租户设备', state: 'REGISTERED' }])
    await flushPromises()
    expect(screen.queryByRole('option', { name: '旧租户设备' })).toBeNull()
    expect(screen.getByRole('option', { name: '一加 9R' })).toBeTruthy()
  })

  it('opens collection settings for the selected device without changing or saving its mode', async () => {
    vi.mocked(listImMessages).mockResolvedValue([])
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /华为买家/ }))
    vi.mocked(markImThreadRead).mockClear()
    await fireEvent.click(screen.getByRole('button', { name: '查看正文采集设置' }))
    await flushPromises()
    expect((screen.getByRole('combobox', { name: '设置设备' }) as HTMLSelectElement).value).toBe('dev-huawei-vog')
    expect((screen.getByRole('radio', { name: '通知监听（后台，不占手机）' }) as HTMLInputElement).checked).toBe(true)
    expect(saveImConfig).not.toHaveBeenCalled()
    expect(replyImThread).not.toHaveBeenCalled()
    expect(markImThreadRead).not.toHaveBeenCalled()
  })

  it('retains the draft and warns against duplicate sends after an uncertain network failure', async () => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: false }))
    vi.mocked(listImMessages).mockResolvedValue([])
    vi.mocked(replyImThread).mockRejectedValue(new TypeError('network'))
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('button', { name: /买家小王/ }))
    await fireEvent.update(screen.getByRole('textbox', { name: '回复内容' }), '保留草稿')
    await fireEvent.click(screen.getByRole('button', { name: '核对回复' }))
    await fireEvent.click(screen.getByRole('button', { name: '确认提交回复任务' }))
    expect((await screen.findByRole('alert')).textContent).toContain('任务可能已提交')
    expect((screen.getByRole('textbox', { name: '回复内容' }) as HTMLTextAreaElement).value).toBe('保留草稿')
    expect(replyImThread).toHaveBeenCalledTimes(1)
  })
  it('mixes three production device ids by default with unread bodies and friendly labels', async () => {
    await renderView(['security_admin'])
    expect(await screen.findByText('买家小王')).toBeTruthy()
    expect(screen.getByText('华为买家')).toBeTruthy()
    expect(screen.getByText('另一位买家')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
    expect(screen.getAllByText('闲鱼').length).toBeGreaterThan(0)
    expect(screen.getByText('一加上的入站正文')).toBeTruthy()
    expect(screen.getByText('VOG 入站正文')).toBeTruthy()
    expect(screen.getByText('ELE 入站正文')).toBeTruthy()
    expect(screen.getByRole('option', { name: '一加 9R' })).toBeTruthy()
    expect(screen.getByRole('option', { name: '全部设备' })).toBeTruthy()
    expect(vi.mocked(listImThreads)).toHaveBeenCalledWith(undefined, false, 'user')
  })

  it('keeps unknown devices distinguishable when their shortened identifiers collide', async () => {
    const ids = ['unknown-phone-device-a', 'unknown-phone-device-b']
    vi.mocked(listImThreads).mockResolvedValue(pageFixture(ids.map((deviceId, index) => threadFixture({
      id: 'unknown-thread-' + index, deviceId, peerName: '未知设备买家 ' + index,
    }))))
    await renderView(['viewer'])
    for (const id of ids) {
      const option = await screen.findByRole('option', { name: '设备 ' + id })
      expect(option.getAttribute('title')).toBe(id)
      expect(document.querySelector('.im-thread [title="设备 ' + id + ' · ' + id + '"]')).toBeTruthy()
    }
  })

  it('keeps settings collapsed and preserves drafts without filtering or saving', async () => {
    await renderView(['security_admin'])
    const toggle = await screen.findByRole('button', { name: '设备监控设置' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('combobox', { name: '设置设备' })).toBeNull()
    expect(screen.getByText(/汇总全部设备已上报的会话/)).toBeTruthy()
    expect(screen.getByText(/未分类内容在「待确认」/)).toBeTruthy()
    await fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    await fireEvent.update(screen.getByRole('combobox', { name: '设置设备' }), 'dev-huawei-vog')
    await flushPromises()
    await fireEvent.click(screen.getByLabelText('小红书'))
    await fireEvent.click(toggle)
    await fireEvent.click(toggle)
    expect((screen.getByLabelText('小红书') as HTMLInputElement).checked).toBe(true)
    expect((screen.getByLabelText('筛选设备') as HTMLSelectElement).value).toBe('')
    expect(document.querySelectorAll('.im-thread')).toHaveLength(3)
    expect(listImThreads).toHaveBeenCalledExactlyOnceWith(undefined, false, 'user')
    expect(saveImConfig).not.toHaveBeenCalled()
  })

  it('keeps classification diagnostics out of the DOM until expanded', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('仅显示正文', { classification: classificationFixture({
      category: 'HUMAN_MESSAGE', source: 'RULE', ruleCode: 'NAMED_PEER', confidence: 0.45,
    }) })])
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByText('买家小王'))
    const details = await screen.findByRole('button', { name: '分类详情' })
    expect(details.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('来源：规则')).toBeNull()
    expect(screen.queryByText('规则：NAMED_PEER')).toBeNull()
    expect(screen.queryByText(/模型原始分数/)).toBeNull()
    expect(screen.getByRole('button', { name: '修改消息分类' })).toBeTruthy()
    await fireEvent.click(details)
    expect(details.getAttribute('aria-expanded')).toBe('true')
    expect(document.getElementById(details.getAttribute('aria-controls')!)).toBeTruthy()
    expect(screen.getByText('来源：规则')).toBeTruthy()
    expect(screen.getByText('模型原始分数：0.45')).toBeTruthy()
    await fireEvent.click(details)
    expect(screen.queryByText('来源：规则')).toBeNull()
  })

  it('filters by production deviceId and never uses an adb serial', async () => {
    await renderView(['security_admin'])
    const option = await screen.findByRole('option', { name: '华为 VOG' })
    await fireEvent.update(screen.getByLabelText('筛选设备'), (option as HTMLOptionElement).value)
    await waitFor(() => expect(vi.mocked(listImThreads)).toHaveBeenLastCalledWith('dev-huawei-vog', false, 'user'))
    expect(vi.mocked(listImThreads).mock.calls.flat().join('|')).not.toContain('APH0219624006517')
  })

  it('hides reply controls when the server is receive-only', async () => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: true }))
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('真实入站展示夹具')])
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    expect(await screen.findByText(/只读收件箱/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '发送回复' })).toBeNull()
    expect(vi.mocked(replyImThread)).not.toHaveBeenCalled()
  })

  it('badges duty-mode devices in the thread list', async () => {
    vi.mocked(fetchImConfig).mockResolvedValue(configFixture({ mode: 'DUTY', dutyStart: '00:00', dutyEnd: '23:59' }))
    await renderView(['security_admin'])
    expect((await screen.findAllByText('值班中')).length).toBeGreaterThan(0)
  })

  it('shows no-body copy and backfills it from the opened conversation', async () => {
    vi.mocked(listImThreads).mockResolvedValueOnce(pageFixture())
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('完整正文：这个还在吗')])
    await renderView(['security_admin'])
    await screen.findByText('暂无正文')
    await fireEvent.click(screen.getByText('买家小王'))
    await waitFor(() => expect(screen.getAllByText('完整正文：这个还在吗').length).toBeGreaterThan(1))
    expect(vi.mocked(markImThreadRead)).toHaveBeenCalledWith('thread-1')
    expect(screen.queryByText('暂无正文')).toBeNull()
  })

  it('polls every five seconds, keeps selection, and refreshes selected messages', async () => {
    vi.useFakeTimers()
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('轮询前正文')])
    await renderView(['security_admin'])
    await vi.waitFor(() => expect(screen.getByText('买家小王')).toBeTruthy())
    await fireEvent.click(screen.getByText('买家小王'))
    await vi.waitFor(() => expect(screen.getAllByText('轮询前正文').length).toBeGreaterThan(0))
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('轮询后正文')])

    await vi.advanceTimersByTimeAsync(5_000)
    expect(vi.mocked(listImThreads).mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(vi.mocked(listImMessages).mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('轮询后正文').length).toBeGreaterThan(0)
    expect(document.querySelector('.im-thread.active')).toBeTruthy()
  })

  it('does not overlap slow polling requests', async () => {
    vi.useFakeTimers()
    const view = await renderView(['security_admin'])
    await vi.waitFor(() => expect(screen.getByText('买家小王')).toBeTruthy())
    let resolvePoll!: (value: ImThreadPage) => void
    vi.mocked(listImThreads).mockImplementationOnce(() => new Promise((resolve) => { resolvePoll = resolve }))
    const baseline = vi.mocked(listImThreads).mock.calls.length
    await vi.advanceTimersByTimeAsync(15_000)
    expect(vi.mocked(listImThreads)).toHaveBeenCalledTimes(baseline + 1)
    resolvePoll(pageFixture())
    await vi.advanceTimersByTimeAsync(0)
    view.unmount()
  })

  it('stops while hidden, refreshes immediately when visible, and cleans up on unmount', async () => {
    vi.useFakeTimers()
    const view = await renderView(['security_admin'])
    await vi.runAllTicks()
    const baseline = vi.mocked(listImThreads).mock.calls.length
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(10_000)
    expect(vi.mocked(listImThreads)).toHaveBeenCalledTimes(baseline)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.runAllTicks()
    expect(vi.mocked(listImThreads)).toHaveBeenCalledTimes(baseline + 1)
    view.unmount()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(vi.mocked(listImThreads)).toHaveBeenCalledTimes(baseline + 1)
  })

  it('retains old threads, selected conversation and messages after poll failures', async () => {
    vi.useFakeTimers()
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('保留的正文')])
    await renderView(['security_admin'])
    await vi.waitFor(() => expect(screen.getByText('买家小王')).toBeTruthy())
    await fireEvent.click(screen.getByText('买家小王'))
    await vi.waitFor(() => expect(screen.getAllByText('保留的正文').length).toBeGreaterThan(0))
    vi.mocked(listImThreads).mockRejectedValueOnce(new ImApiError(503, '线程轮询失败'))
    vi.mocked(listImMessages).mockRejectedValueOnce(new ImApiError(503, '消息轮询失败'))

    await vi.advanceTimersByTimeAsync(5_000)
    expect(screen.getAllByText('买家小王').length).toBeGreaterThan(0)
    expect(screen.getAllByText('保留的正文').length).toBeGreaterThan(0)
    expect(document.querySelector('.im-thread.active')).toBeTruthy()
    expect(screen.getByText('线程轮询失败')).toBeTruthy()
    await vi.advanceTimersByTimeAsync(5_000)
    expect(screen.getByText('消息轮询失败')).toBeTruthy()
    expect(screen.getAllByText('保留的正文').length).toBeGreaterThan(0)
  })

  it('keeps the monitor config read-only for viewer roles', async () => {
    const { container } = await renderView(['viewer'])
    await fireEvent.click(await screen.findByRole('button', { name: '设备监控设置' }))
    await screen.findByText('监听总开关')
    expect(screen.queryByRole('button', { name: '保存设置' })).toBeNull()
    expect(screen.getByText('当前角色只读，仅能查看监控设置。')).toBeTruthy()
    const disabledControls = container.querySelectorAll('.im-config input:disabled, .im-config select:disabled')
    expect(disabledControls.length).toBeGreaterThan(0)
  })

  it('blocks saving an empty platform selection with a visible validation error', async () => {
    vi.mocked(saveImConfig).mockResolvedValue(configFixture())
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByRole('button', { name: '设备监控设置' }))
    await screen.findByText('监听总开关')
    await fireEvent.click(screen.getByLabelText('闲鱼'))
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    expect(screen.getByText('至少选择一个监听平台')).toBeTruthy()
    expect(vi.mocked(saveImConfig)).not.toHaveBeenCalled()
  })

  it('saves a valid draft and reports backend failures visibly', async () => {
    vi.mocked(saveImConfig).mockRejectedValueOnce(new ImApiError(409, '监听平台包含不支持的取值（HTTP 409）'))
    const { container } = await renderView(['security_admin'])
    await fireEvent.click(await screen.findByRole('button', { name: '设备监控设置' }))
    await screen.findByText('监听总开关')
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await waitFor(() => expect(vi.mocked(saveImConfig)).toHaveBeenCalledTimes(1))
    expect(vi.mocked(saveImConfig)).toHaveBeenCalledWith('dev-alpha-0001', {
      enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00',
    })
    expect(screen.getByText(/监听平台包含不支持的取值/)).toBeTruthy()
    expect(container.querySelector('.im-config-feedback.error')).toBeTruthy()

    vi.mocked(saveImConfig).mockResolvedValueOnce(configFixture({ mode: 'DUTY' }))
    await fireEvent.click(screen.getByLabelText('值班模式（驻守消息页）'))
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await waitFor(() => expect(screen.getByText(/已保存，手机下一轮同步生效/)).toBeTruthy())
    expect(vi.mocked(saveImConfig)).toHaveBeenLastCalledWith('dev-alpha-0001', {
      enabled: true, platforms: ['xianyu'], mode: 'DUTY', dutyStart: '09:00', dutyEnd: '23:00',
    })
  })

  it.each(['resolve', 'reject'] as const)('ignores a late config save %s after switching devices', async (outcome) => {
    const pending = deferred<ImMonitorConfig>()
    const otherConfig = configFixture({ deviceId: 'dev-huawei-vog', enabled: false })
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) =>
      deviceId === otherConfig.deviceId ? otherConfig : configFixture({ deviceId }))
    vi.mocked(saveImConfig).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(otherConfig)
    const { container } = await renderView(['security_admin'])
    await fireEvent.click(await screen.findByRole('button', { name: '设备监控设置' }))
    await screen.findByText('监听总开关')
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await fireEvent.update(container.querySelector('.im-config select')!, otherConfig.deviceId)
    await flushPromises()
    expect((screen.getByLabelText('监听总开关') as HTMLInputElement).checked).toBe(false)

    if (outcome === 'resolve') pending.resolve(configFixture())
    else pending.reject(new ImApiError(503, 'old device save failed'))
    await flushPromises()

    expect((screen.getByLabelText('监听总开关') as HTMLInputElement).checked).toBe(false)
    expect(screen.queryByText(/已保存，手机下一轮同步生效|old device save failed/)).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    expect(saveImConfig).toHaveBeenLastCalledWith(otherConfig.deviceId, expect.objectContaining({ enabled: false }))
  })

  it('shows a config fetch failure even without a form and allows retry', async () => {
    vi.mocked(fetchImConfig).mockRejectedValue(new ImApiError(503, '监控配置暂不可用'))
    await renderView(['device_operator'])
    expect((await screen.findByRole('alert')).textContent).toContain('监控配置暂不可用')
    expect(screen.queryByLabelText('监听总开关')).toBeNull()
    expect(screen.getByText('买家小王')).toBeTruthy()

    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId }))
    await fireEvent.click(screen.getByRole('button', { name: '设备监控设置' }))
    await fireEvent.click(screen.getByRole('button', { name: '重试加载设置' }))
    expect(await screen.findByLabelText('监听总开关')).toBeTruthy()
    expect(screen.queryByText('监控配置暂不可用')).toBeNull()
  })

  it('loads older conversations and preserves the loaded pages on refresh', async () => {
    const first = Array.from({ length: 50 }, (_, index) => threadFixture({
      id: `thread-${index}`, peerName: `买家-${index}`, unreadCount: 0,
    }))
    const older = threadFixture({ id: 'thread-older', peerName: '较早的买家', unreadCount: 0 })
    const counts = { all: 51, user: 51, notice: 0, review: 0 }
    vi.mocked(listImThreads).mockResolvedValueOnce(pageFixture(first, counts))
      .mockResolvedValueOnce(pageFixture([older], counts))
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('较早的会话正文')])
    await renderView(['viewer'])
    await flushPromises()
    await fireEvent.click(await screen.findByRole('button', { name: '加载更多会话' }))
    expect(listImThreads).toHaveBeenLastCalledWith(undefined, false, 'user', 'thread-49')
    await fireEvent.click(await screen.findByText('较早的买家'))
    await screen.findAllByText('较早的会话正文')
    expect(screen.queryByRole('button', { name: '加载更多会话' })).toBeNull()

    vi.mocked(listImThreads).mockResolvedValueOnce(pageFixture(first, counts))
      .mockResolvedValueOnce(pageFixture([older], counts))
    await fireEvent.click(screen.getByRole('button', { name: '刷新收件箱' }))
    await flushPromises()
    expect(document.querySelectorAll('.im-thread')).toHaveLength(51)
    expect(document.querySelector('.im-thread.active')?.textContent).toContain('较早的买家')
    expect(screen.getAllByText('较早的会话正文').length).toBeGreaterThan(0)
  })

  it.each(['resolve', 'reject'] as const)('ignores a stale older-page %s after switching buckets', async (outcome) => {
    const first = Array.from({ length: 50 }, (_, index) => threadFixture({ id: `page-${index}`, peerName: `初始买家-${index}` }))
    const pending = deferred<ImThreadPage>()
    vi.mocked(listImThreads).mockResolvedValueOnce(pageFixture(first))
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(pageFixture([threadFixture({ peerName: '新分类买家' })]))
    await renderView(['viewer'])
    await flushPromises()
    await fireEvent.click(screen.getByRole('button', { name: '加载更多会话' }))
    await fireEvent.click(screen.getByRole('tab', { name: '通知 / 营销 5' }))
    await screen.findByText('新分类买家')
    if (outcome === 'resolve') pending.resolve(pageFixture([threadFixture({ peerName: '过期买家' })]))
    else pending.reject(new ImApiError(503, 'stale page failure'))
    await flushPromises()
    expect(screen.getByText('新分类买家')).toBeTruthy()
    expect(screen.queryByText('过期买家')).toBeNull()
    expect(screen.queryByText('stale page failure')).toBeNull()
    expect(document.querySelectorAll('.im-thread')).toHaveLength(1)
  })

  it('exposes the DM-channel filter note with the affected platforms', async () => {
    vi.mocked(fetchImConfig).mockResolvedValue(configFixture({ platforms: ['xhs', 'wechat'] }))
    await renderView(['viewer'])
    await fireEvent.click(await screen.findByRole('button', { name: '设备监控设置' }))
    await screen.findByText('监听总开关')
    await fireEvent.click(screen.getByText('监听范围与过滤说明'))
    expect(screen.getByText(/只上报私信类通知通道/)).toBeTruthy()
    expect(screen.getByText(/当前受过滤平台：小红书、微信（仅收不发）/)).toBeTruthy()
  })

  it('shows full-result bucket counts and queries every bucket on both reads', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('分类消息')])
    await renderView(['viewer'])
    expect(await screen.findByRole('tab', { name: '用户消息 8', selected: true })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '通知 / 营销 5' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '待确认 3' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '全部 13' })).toBeTruthy()
    for (const [label, bucket] of [['用户消息', 'user'], ['通知 / 营销', 'notice'], ['待确认', 'review'], ['全部', 'all']]) {
      await fireEvent.click(screen.getByRole('tab', { name: new RegExp(label!) }))
      await fireEvent.click(await screen.findByText('买家小王'))
      await waitFor(() => expect(listImMessages).toHaveBeenLastCalledWith('thread-1', bucket))
      expect(listImThreads).toHaveBeenLastCalledWith(undefined, false, bucket)
    }
    await fireEvent.click(screen.getByLabelText('只看未读'))
    await waitFor(() => expect(listImThreads).toHaveBeenLastCalledWith(undefined, true, 'all'))
  })

  it('uses server bucket summaries and keeps a mixed thread in multiple buckets', async () => {
    vi.mocked(listImThreads).mockImplementation(async (_device, _unread, bucket) => pageFixture([
      threadFixture({
        lastMessageText: bucket === 'notice' ? '通知摘要' : '用户摘要',
        lastMessageClassification: classificationFixture({ category: bucket === 'notice' ? 'SYSTEM_NOTICE' : 'HUMAN_MESSAGE' }),
      }),
    ]))
    vi.mocked(listImMessages).mockImplementation(async (_id, bucket) => [
      messageFixture(bucket === 'notice' ? '通知正文' : '用户正文'),
      ...(bucket === 'user' ? [messageFixture('历史出站', { id: 'out', direction: 'OUT' as const })] : []),
    ])
    await renderView(['viewer'])
    await fireEvent.click(await screen.findByText('买家小王'))
    expect(await screen.findByText('用户正文')).toBeTruthy()
    expect(screen.getByText('用户摘要')).toBeTruthy()
    expect(screen.getByText('历史出站')).toBeTruthy()
    await fireEvent.click(screen.getByRole('tab', { name: '通知 / 营销 5' }))
    await fireEvent.click(await screen.findByText('买家小王'))
    expect(await screen.findByText('通知正文')).toBeTruthy()
    expect(screen.getByText('通知摘要')).toBeTruthy()
    expect(screen.queryByText('历史出站')).toBeNull()
    expect(screen.queryByText('用户正文')).toBeNull()
  })

  it('keeps legacy unknown messages discoverable without inventing counts or scores', async () => {
    vi.mocked(listImThreads).mockResolvedValue(pageFixture([threadFixture()], null))
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('历史通知')])
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByRole('tab', { name: '待确认 —' }))
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(await screen.findByRole('button', { name: '分类详情' }))
    expect(screen.getByText('来源：未分类')).toBeTruthy()
    expect(screen.getByText('历史通知', { selector: '.im-text' })).toBeTruthy()
    expect(screen.queryByText(/模型原始分数：/)).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '修改消息分类' }))
    vi.mocked(classifyImMessage).mockResolvedValue(messageFixture('历史通知'))
    await fireEvent.click(screen.getByRole('button', { name: '待确认' }))
    await waitFor(() => expect(classifyImMessage).toHaveBeenCalledWith('m-1', 'UNKNOWN', 0))
    await fireEvent.click(screen.getByRole('tab', { name: '全部 —' }))
    expect(listImThreads).toHaveBeenLastCalledWith(undefined, false, 'all')
  })

  it('displays the effective source separately from a low raw model score and pending status', async () => {
    vi.mocked(listImMessages).mockResolvedValue([
      messageFixture('人工决定', { classification: classificationFixture({
        category: 'SYSTEM_NOTICE', source: 'MANUAL', status: 'MANUAL',
        predictedCategory: 'HUMAN_MESSAGE', confidence: 0.43, modelStatus: 'NEEDS_REVIEW', version: 4,
      }) }),
      messageFixture('规则决定', { id: 'm-2', classification: classificationFixture({
        source: 'RULE', category: 'PROMOTION', ruleCode: 'OFFICIAL_MARKETING', modelStatus: 'PENDING',
      }) }),
      messageFixture('模型决定', { id: 'm-3', classification: classificationFixture({
        source: 'MODEL', category: 'HUMAN_MESSAGE', confidence: 0.99,
      }) }),
    ])
    await renderView(['viewer'])
    await fireEvent.click(await screen.findByText('买家小王'))
    for (const button of await screen.findAllByRole('button', { name: '分类详情' })) await fireEvent.click(button)
    expect(screen.getByText('来源：人工')).toBeTruthy()
    expect(screen.getByText('模型预测：用户消息')).toBeTruthy()
    expect(screen.getByText('模型原始分数：0.43')).toBeTruthy()
    expect(screen.getByText('模型状态：NEEDS_REVIEW')).toBeTruthy()
    const ruleBubble = screen.getByText('规则决定').closest('.im-bubble') as HTMLElement
    expect(within(ruleBubble).getByText('来源：规则')).toBeTruthy()
    expect(within(ruleBubble).getByText('规则：OFFICIAL_MARKETING')).toBeTruthy()
    expect(within(ruleBubble).queryByText(/模型原始分数/)).toBeNull()
    expect(screen.getByText('来源：模型')).toBeTruthy()
    expect(screen.queryByText(/准确率：/)).toBeNull()
  })

  it.each([
    ['用户消息', 'HUMAN_MESSAGE'],
    ['系统通知', 'SYSTEM_NOTICE'],
    ['营销通知', 'PROMOTION'],
    ['待确认', 'UNKNOWN'],
    ['恢复自动', null],
  ] as const)('corrects one IN message using %s and its frozen expectedVersion', async (label, category) => {
    const message = messageFixture('入站', { classification: classificationFixture({ version: 7 }) })
    vi.mocked(listImMessages).mockResolvedValue([message, messageFixture('出站', { id: 'out', direction: 'OUT' })])
    vi.mocked(classifyImMessage).mockResolvedValue(message)
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: true }))
    await renderView(['device_operator'])
    await fireEvent.click(await screen.findByText('买家小王'))
    expect((await screen.findAllByRole('button', { name: '修改消息分类' })).length).toBe(1)
    await fireEvent.click(screen.getByRole('button', { name: '修改消息分类' }))
    await fireEvent.click(screen.getByRole('button', { name: label }))
    await screen.findByText('分类已更新')
    expect(classifyImMessage).toHaveBeenCalledExactlyOnceWith('m-1', category, 7)
    expect(reclassifyImMessage).not.toHaveBeenCalled()
    expect(replyImThread).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: '发送回复' })).toBeNull()
  })

  it('reclassifies without resetting a manual override, then refreshes changed membership and counts', async () => {
    const message = messageFixture('需要重算', { classification: classificationFixture({ source: 'MANUAL', version: 9 }) })
    vi.mocked(listImMessages).mockResolvedValue([message])
    vi.mocked(reclassifyImMessage).mockResolvedValue({ ...message, classification: classificationFixture({
      source: 'MANUAL', category: 'SYSTEM_NOTICE', modelStatus: 'PENDING', version: 10,
    }) })
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(await screen.findByRole('button', { name: '修改消息分类' }))
    vi.mocked(listImThreads).mockResolvedValue(pageFixture([], { all: 13, user: 7, notice: 6, review: 3 }))
    await fireEvent.click(screen.getByRole('button', { name: '重新分类' }))
    await screen.findByText('重新分类已提交')
    expect(reclassifyImMessage).toHaveBeenCalledExactlyOnceWith('m-1', 9)
    expect(classifyImMessage).not.toHaveBeenCalled()
    expect(screen.getByRole('tab', { name: '用户消息 7' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '通知 / 营销 6' })).toBeTruthy()
    expect(screen.queryByText('需要重算')).toBeNull()
    expect(screen.getByText('当前分类暂无会话。')).toBeTruthy()
  })

  it('refreshes a mixed thread after a correction without dropping its remaining matching messages', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('改走这条'), messageFixture('保留这条', { id: 'm-2' })])
    vi.mocked(classifyImMessage).mockResolvedValue(messageFixture('改走这条', { classification: classificationFixture({ category: 'PROMOTION', version: 1 }) }))
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click((await screen.findAllByRole('button', { name: '修改消息分类' }))[0]!)
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('保留这条', { id: 'm-2' })])
    await fireEvent.click(screen.getByRole('button', { name: '营销通知' }))
    await screen.findByText('分类已更新')
    expect(screen.queryByText('改走这条')).toBeNull()
    expect(screen.getByText('保留这条')).toBeTruthy()
    expect(document.querySelector('.im-thread.active')).toBeTruthy()
    expect(listImMessages).toHaveBeenLastCalledWith('thread-1', 'user')
  })

  it('does not offer correction or reply actions to read-only actors', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('只读消息')])
    await renderView(['viewer'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await screen.findByText('只读消息')
    expect(screen.queryByRole('button', { name: '修改消息分类' })).toBeNull()
    expect(screen.queryByRole('button', { name: '发送回复' })).toBeNull()
    expect(classifyImMessage).not.toHaveBeenCalled()
    expect(reclassifyImMessage).not.toHaveBeenCalled()
  })

  it('fails closed for malformed concurrency versions', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('无效版本', {
      classification: classificationFixture({ version: -1 }),
    })])
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    const trigger = await screen.findByRole('button', { name: '修改消息分类' })
    expect((trigger as HTMLButtonElement).disabled).toBe(true)
    expect(classifyImMessage).not.toHaveBeenCalled()
  })

  it.each([403, 404, 503])('retains message data and surfaces classification HTTP %s without a send', async (status) => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('保留正文')])
    vi.mocked(classifyImMessage).mockRejectedValue(new ImApiError(status, `拒绝分类 HTTP ${status}`))
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(await screen.findByRole('button', { name: '修改消息分类' }))
    await fireEvent.click(screen.getByRole('button', { name: '系统通知' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', `拒绝分类 HTTP ${status}`)
    expect(screen.getByText('保留正文')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '分类详情' }))
    expect(screen.getByText('来源：未分类')).toBeTruthy()
    expect(replyImThread).not.toHaveBeenCalled()
  })

  it('refreshes after 409 and requires an explicit retry using the new version', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('冲突消息', { classification: classificationFixture({ version: 2 }) })])
    vi.mocked(classifyImMessage).mockRejectedValueOnce(new ImApiError(409, 'version mismatch'))
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(await screen.findByRole('button', { name: '修改消息分类' }))
    const updated = messageFixture('冲突消息', { classification: classificationFixture({ version: 3, source: 'MANUAL', category: 'SYSTEM_NOTICE' }) })
    vi.mocked(listImMessages).mockResolvedValue([updated])
    await fireEvent.click(screen.getByRole('button', { name: '用户消息' }))
    await fireEvent.click(await screen.findByRole('button', { name: '分类详情' }))
    await screen.findByText('来源：人工')
    expect(screen.getByRole('alert').textContent).toContain('本次修改未保存')
    expect(classifyImMessage).toHaveBeenCalledTimes(1)
    vi.mocked(classifyImMessage).mockResolvedValue(updated)
    await fireEvent.click(screen.getByRole('button', { name: '修改消息分类' }))
    await fireEvent.click(screen.getByRole('button', { name: '用户消息' }))
    await screen.findByText('分类已更新')
    expect(classifyImMessage).toHaveBeenLastCalledWith('m-1', 'HUMAN_MESSAGE', 3)
  })

  it('shows both a version conflict and a failed refresh without claiming freshness', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('冲突保留')])
    vi.mocked(reclassifyImMessage).mockRejectedValue(new ImApiError(409, 'conflict'))
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(await screen.findByRole('button', { name: '修改消息分类' }))
    vi.mocked(listImThreads).mockRejectedValue(new ImApiError(503, '刷新失败'))
    await fireEvent.click(screen.getByRole('button', { name: '重新分类' }))
    expect(await screen.findByText('刷新失败')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('已请求刷新')
    expect(screen.getByText('冲突保留')).toBeTruthy()
    expect(screen.queryByText('分类已更新')).toBeNull()
  })

  it('disables duplicate corrections and ignores an older message poll after mutation', async () => {
    vi.useFakeTimers()
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('原正文')])
    await renderView(['security_admin'])
    await flushPromises()
    await fireEvent.click(screen.getByText('买家小王'))
    await flushPromises()
    const oldPoll = deferred<ImMessage[]>()
    vi.mocked(listImMessages).mockImplementationOnce(() => oldPoll.promise)
    await vi.advanceTimersByTimeAsync(5_000)
    const correction = deferred<ImMessage>()
    vi.mocked(classifyImMessage).mockImplementationOnce(() => correction.promise)
    await fireEvent.click(screen.getByRole('button', { name: '修改消息分类' }))
    await fireEvent.click(screen.getByRole('button', { name: '系统通知' }))
    expect((screen.getByRole('button', { name: '修改消息分类' }) as HTMLButtonElement).disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(classifyImMessage).toHaveBeenCalledTimes(1)
    const updated = messageFixture('原正文', { classification: classificationFixture({ source: 'MANUAL', version: 1 }) })
    vi.mocked(listImMessages).mockResolvedValue([updated])
    correction.resolve(updated)
    await flushPromises()
    oldPoll.resolve([messageFixture('过期轮询')])
    await flushPromises()
    expect(screen.queryByText('过期轮询')).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '分类详情' }))
    expect(screen.getByText('来源：人工')).toBeTruthy()
    expect(screen.getByText('分类已更新')).toBeTruthy()
  })

  it('ignores stale thread results and counts after switching bucket then device', async () => {
    const old = deferred<ImThreadPage>()
    vi.mocked(listImThreads).mockImplementationOnce(() => old.promise)
    await renderView(['viewer'])
    await fireEvent.click(screen.getByRole('tab', { name: /通知 \/ 营销/ }))
    await fireEvent.update(screen.getByLabelText('筛选设备')!, 'dev-huawei-vog')
    await flushPromises()
    old.resolve(pageFixture([threadFixture({ peerName: '过期设备' })], { all: 99, user: 99, notice: 99, review: 99 }))
    await flushPromises()
    expect(screen.queryByText('过期设备')).toBeNull()
    expect(screen.getByRole('tab', { name: '通知 / 营销 5', selected: true })).toBeTruthy()
    expect(listImThreads).toHaveBeenLastCalledWith('dev-huawei-vog', false, 'notice')
  })

  it.each(['resolve', 'reject'] as const)('ignores stale message %s after leaving and reopening the same mixed thread in another bucket', async (outcome) => {
    const old = deferred<ImMessage[]>()
    vi.mocked(listImMessages).mockImplementationOnce(() => old.promise).mockResolvedValue([messageFixture('当前通知')])
    await renderView(['viewer'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(screen.getByRole('tab', { name: '通知 / 营销 5' }))
    await fireEvent.click(await screen.findByText('买家小王'))
    await screen.findByText('当前通知')
    if (outcome === 'resolve') old.resolve([messageFixture('旧分类正文')])
    else old.reject(new ImApiError(503, '旧分类错误'))
    await flushPromises()
    expect(screen.queryByText('旧分类正文')).toBeNull()
    expect(screen.queryByText('旧分类错误')).toBeNull()
    expect(screen.getByText('当前通知')).toBeTruthy()
  })

  it('clears the old conversation immediately while another device request is pending', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('上一台设备消息')])
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await screen.findByText('上一台设备消息')
    const next = deferred<ImThreadPage>()
    vi.mocked(listImThreads).mockImplementationOnce(() => next.promise)
    await fireEvent.update(screen.getByLabelText('筛选设备')!, 'dev-huawei-vog')
    expect(screen.queryByText('上一台设备消息')).toBeNull()
    expect(screen.queryByRole('button', { name: '修改消息分类' })).toBeNull()
    next.resolve(pageFixture([]))
    await flushPromises()
  })

  it.each(['resolve', 'reject'] as const)('ignores a late correction %s after switching devices', async (outcome) => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('旧设备消息')])
    const pending = deferred<ImMessage>()
    vi.mocked(classifyImMessage).mockImplementationOnce(() => pending.promise)
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    await fireEvent.click(await screen.findByRole('button', { name: '修改消息分类' }))
    await fireEvent.click(screen.getByRole('button', { name: '系统通知' }))
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('新设备消息', { id: 'm-new', threadId: 'thread-2' })])
    await fireEvent.update(screen.getByLabelText('筛选设备')!, 'dev-huawei-vog')
    await fireEvent.click(await screen.findByText('华为买家'))
    await screen.findByText('新设备消息')
    if (outcome === 'resolve') pending.resolve(messageFixture('迟到纠正正文'))
    else pending.reject(new ImApiError(409, '迟到冲突'))
    await flushPromises()
    expect(screen.queryByText('迟到纠正正文')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText('分类已更新')).toBeNull()
    expect(screen.getByText('新设备消息')).toBeTruthy()
  })
})
