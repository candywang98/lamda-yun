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

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  operationsMockEnabled: false,
  createControlApiClient: () => ({
    devices: vi.fn(async () => [
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
    const view = render(ImInboxView, { global: { plugins: [pinia] } })
    const session = useSessionStore()
    session.applySession({ userId: 'user-1', tenantId: 'tenant-1', roles, mfa: true, requestId: 'req-1' })
    return view
  }

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
    expect(screen.getByRole('option', { name: /一加 9R.*dev-alpha/ })).toBeTruthy()
    expect(screen.getByRole('option', { name: '全部设备' })).toBeTruthy()
    expect(vi.mocked(listImThreads)).toHaveBeenCalledWith(undefined, false, 'user')
  })

  it('filters by production deviceId and never uses an adb serial', async () => {
    await renderView(['security_admin'])
    const option = await screen.findByRole('option', { name: /华为 VOG.*dev-huawei/ })
    await fireEvent.update(screen.getAllByLabelText('设备')[0], (option as HTMLOptionElement).value)
    await waitFor(() => expect(vi.mocked(listImThreads)).toHaveBeenLastCalledWith('dev-huawei-vog', false, 'user'))
    expect(vi.mocked(listImThreads).mock.calls.flat().join('|')).not.toContain('APH0219624006517')
  })

  it('hides reply controls when the server is receive-only', async () => {
    vi.mocked(fetchImConfig).mockImplementation(async (deviceId) => configFixture({ deviceId, receiveOnly: true }))
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('真实入站展示夹具')])
    await renderView(['security_admin'])
    await fireEvent.click(await screen.findByText('买家小王'))
    expect(await screen.findByText('只读收件箱')).toBeTruthy()
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
    await screen.findByText('监听总开关')
    expect(screen.queryByRole('button', { name: '保存设置' })).toBeNull()
    expect(screen.getByText('当前角色只读，仅能查看监控设置。')).toBeTruthy()
    const disabledControls = container.querySelectorAll('.im-config input:disabled, .im-config select:disabled')
    expect(disabledControls.length).toBeGreaterThan(0)
  })

  it('blocks saving an empty platform selection with a visible validation error', async () => {
    vi.mocked(saveImConfig).mockResolvedValue(configFixture())
    await renderView(['security_admin'])
    await screen.findByText('监听总开关')
    await fireEvent.click(screen.getByLabelText('闲鱼'))
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    expect(screen.getByText('至少选择一个监听平台')).toBeTruthy()
    expect(vi.mocked(saveImConfig)).not.toHaveBeenCalled()
  })

  it('saves a valid draft and reports backend failures visibly', async () => {
    vi.mocked(saveImConfig).mockRejectedValueOnce(new ImApiError(409, '监听平台包含不支持的取值（HTTP 409）'))
    const { container } = await renderView(['security_admin'])
    await screen.findByText('监听总开关')
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await waitFor(() => expect(vi.mocked(saveImConfig)).toHaveBeenCalledTimes(1))
    expect(vi.mocked(saveImConfig)).toHaveBeenCalledWith('dev-alpha-0001', {
      enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00',
    })
    expect(screen.getByText(/监听平台包含不支持的取值/)).toBeTruthy()
    expect(container.querySelector('.im-config-feedback.error')).toBeTruthy()

    vi.mocked(saveImConfig).mockResolvedValueOnce(configFixture({ mode: 'DUTY' }))
    await fireEvent.click(screen.getByLabelText('值班模式（驻守消息页，全文零漏收）'))
    await fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    await waitFor(() => expect(screen.getByText(/已保存，手机下一轮同步生效/)).toBeTruthy())
    expect(vi.mocked(saveImConfig)).toHaveBeenLastCalledWith('dev-alpha-0001', {
      enabled: true, platforms: ['xianyu'], mode: 'DUTY', dutyStart: '09:00', dutyEnd: '23:00',
    })
  })

  it('exposes the DM-channel filter note with the affected platforms', async () => {
    vi.mocked(fetchImConfig).mockResolvedValue(configFixture({ platforms: ['xhs', 'wechat'] }))
    await renderView(['viewer'])
    await screen.findByText('监听总开关')
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
    expect(await screen.findByText('来源：未分类')).toBeTruthy()
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
    expect(await screen.findByText('来源：人工')).toBeTruthy()
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
    await screen.findByText('来源：未分类')
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
    expect(screen.getByText('来源：人工')).toBeTruthy()
    expect(screen.getByText('分类已更新')).toBeTruthy()
  })

  it('ignores stale thread results and counts after switching bucket then device', async () => {
    const old = deferred<ImThreadPage>()
    vi.mocked(listImThreads).mockImplementationOnce(() => old.promise)
    await renderView(['viewer'])
    await fireEvent.click(screen.getByRole('tab', { name: /通知 \/ 营销/ }))
    await fireEvent.update(screen.getAllByLabelText('设备')[0]!, 'dev-huawei-vog')
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
    await fireEvent.update(screen.getAllByLabelText('设备')[0]!, 'dev-huawei-vog')
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
    await fireEvent.update(screen.getAllByLabelText('设备')[0]!, 'dev-huawei-vog')
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
