import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchImConfig,
  listImMessages,
  listImThreads,
  markImThreadRead,
  replyImThread,
  saveImConfig,
  ImApiError,
  type ImMessage,
  type ImMonitorConfig,
  type ImThread,
} from '@/api/im'
import { useSessionStore } from '@/stores/session'
import ImInboxView from '@/views/ImInboxView.vue'

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  operationsMockEnabled: false,
  createControlApiClient: () => ({
    devices: vi.fn(async () => [{ id: 'dev-alpha-0001', logical_name: '一加 9R', state: 'REGISTERED' }]),
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
    summaryPending: true,
    ...overrides,
  }
}

function messageFixture(text: string): ImMessage {
  return {
    id: 'm-1',
    threadId: 'thread-1',
    direction: 'IN',
    contentType: 'TEXT',
    text,
    occurredAt: '2026-09-14T09:59:00.000Z',
    replyTaskId: null,
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

describe('ImInboxView', () => {
  beforeEach(() => {
    vi.mocked(listImThreads).mockReset().mockResolvedValue([
      threadFixture(),
      threadFixture({
        id: 'thread-2', platform: 'xhs', peerName: '红书买家', unreadCount: 0,
        lastMessageText: '你好，还在吗？', summaryPending: false, lastMessageAt: '2026-09-14T09:30:00.000Z',
      }),
    ])
    vi.mocked(fetchImConfig).mockReset().mockImplementation(async (deviceId: string) => configFixture({ deviceId }))
    vi.mocked(saveImConfig).mockReset()
    vi.mocked(listImMessages).mockReset()
    vi.mocked(markImThreadRead).mockReset().mockResolvedValue(undefined)
    vi.mocked(replyImThread).mockReset()
  })

  async function renderView(roles: string[]) {
    const pinia = createPinia()
    const view = render(ImInboxView, { global: { plugins: [pinia] } })
    const session = useSessionStore()
    session.applySession({ userId: 'user-1', tenantId: 'tenant-1', roles, mfa: true, requestId: 'req-1' })
    return view
  }

  it('shows unread badges, platform chips and pending summaries in the thread list', async () => {
    await renderView(['security_admin'])
    expect(await screen.findByText('买家小王')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
    expect(screen.getAllByText('闲鱼').length).toBeGreaterThan(0)
    expect(screen.getAllByText('小红书').length).toBeGreaterThan(0)
    expect(screen.getByText('摘要待补全')).toBeTruthy()
    expect(screen.getByText('你好，还在吗？')).toBeTruthy()
  })

  it('badges duty-mode devices in the thread list', async () => {
    vi.mocked(fetchImConfig).mockResolvedValue(configFixture({ mode: 'DUTY', dutyStart: '00:00', dutyEnd: '23:59' }))
    await renderView(['security_admin'])
    expect((await screen.findAllByText('值班中')).length).toBeGreaterThan(0)
  })

  it('backfills the thread summary from the opened conversation', async () => {
    vi.mocked(listImMessages).mockResolvedValue([messageFixture('完整正文：这个还在吗')])
    await renderView(['security_admin'])
    await screen.findByText('摘要待补全')
    await fireEvent.click(screen.getByText('买家小王'))
    await waitFor(() => expect(screen.getAllByText('完整正文：这个还在吗').length).toBeGreaterThan(1))
    expect(vi.mocked(markImThreadRead)).toHaveBeenCalledWith('thread-1')
    expect(screen.queryByText('摘要待补全')).toBeNull()
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
})
