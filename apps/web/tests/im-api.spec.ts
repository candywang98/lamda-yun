import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchImConfig,
  imDutyStatus,
  imPlatformDmFiltered,
  imPlatformLabel,
  ImApiError,
  normalizeImThread,
  saveImConfig,
  validateImConfigDraft,
  type ImMonitorConfig,
  type ImMonitorConfigDraft,
  type ImThread,
} from '@/api/im'

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  operationsMockEnabled: false,
  createControlApiClient: () => ({}),
}))

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

describe('im api helpers', () => {
  it('normalizes absent or blank server summaries to null', () => {
    expect(normalizeImThread(threadFixture()).lastMessageText).toBeNull()
    expect(normalizeImThread(threadFixture({ lastMessageText: '在的，可以拍' })).lastMessageText)
      .toBe('在的，可以拍')
    expect(normalizeImThread(threadFixture({ lastMessageText: '   ' })).lastMessageText).toBeNull()
  })

  it('labels platform sources and DM-channel filtering', () => {
    expect(imPlatformLabel('xianyu')).toBe('闲鱼')
    expect(imPlatformLabel('xhs')).toBe('小红书')
    expect(imPlatformLabel('douyin')).toBe('抖音')
    expect(imPlatformLabel('wechat')).toContain('微信')
    expect(imPlatformLabel('unknown-feed')).toBe('unknown-feed')
    expect(imPlatformDmFiltered('xianyu')).toBe(false)
    expect(imPlatformDmFiltered('xhs')).toBe(true)
    expect(imPlatformDmFiltered('douyin')).toBe(true)
    expect(imPlatformDmFiltered('wechat')).toBe(true)
  })

  it('validates monitor config drafts like the backend contract', () => {
    expect(validateImConfigDraft({ enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00' })).toEqual([])
    expect(validateImConfigDraft({ enabled: true, platforms: ['xianyu', 'xhs', 'douyin', 'wechat'], mode: 'DUTY', dutyStart: '22:00', dutyEnd: '06:00' })).toEqual([])

    expect(validateImConfigDraft({ enabled: true, platforms: [], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00' }))
      .toEqual(['至少选择一个监听平台'])
    expect(validateImConfigDraft({ enabled: true, platforms: ['xianyu', 'xhs', 'douyin', 'wechat', 'baidu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00' }))
      .toContain('最多只能选择 4 个平台')
    expect(validateImConfigDraft({ enabled: true, platforms: ['weibo'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00' }))
      .toEqual(['不支持的平台：weibo'])
    expect(validateImConfigDraft({ enabled: true, platforms: ['xianyu'], mode: 'ALWAYS' as ImMonitorConfigDraft['mode'], dutyStart: '09:00', dutyEnd: '23:00' }))
      .toEqual(['监听模式无效'])
    expect(validateImConfigDraft({ enabled: true, platforms: ['xianyu'], mode: 'DUTY', dutyStart: '9:00', dutyEnd: '0900' }))
      .toEqual(['值班开始时间格式应为 HH:MM', '值班结束时间格式应为 HH:MM'])
  })

  it('derives duty status including cross-midnight windows', () => {
    const base = { enabled: true, mode: 'DUTY' as const, dutyStart: '22:00', dutyEnd: '06:00' }
    expect(imDutyStatus(base, new Date(2026, 8, 14, 23, 30))).toBe('inside')
    expect(imDutyStatus(base, new Date(2026, 8, 14, 3, 30))).toBe('inside')
    expect(imDutyStatus(base, new Date(2026, 8, 14, 12, 0))).toBe('outside')
    expect(imDutyStatus({ ...base, mode: 'NOTIFICATION' }, new Date(2026, 8, 14, 23, 30))).toBe('off')
    expect(imDutyStatus({ ...base, enabled: false }, new Date(2026, 8, 14, 23, 30))).toBe('off')
    expect(imDutyStatus({ ...base, dutyStart: '09:00', dutyEnd: '18:00' }, new Date(2026, 8, 14, 17, 59))).toBe('inside')
    expect(imDutyStatus({ ...base, dutyStart: '09:00', dutyEnd: '18:00' }, new Date(2026, 8, 14, 18, 0))).toBe('outside')
  })
})

describe('im config api wiring', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('PUTs the config draft and returns the stored view', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(configFixture({
      platforms: ['xianyu', 'xhs'], mode: 'DUTY', dutyStart: '22:00', dutyEnd: '06:00',
    })), { status: 200 }))
    const saved = await saveImConfig('dev-alpha-0001', {
      enabled: true, platforms: ['xianyu', 'xhs'], mode: 'DUTY', dutyStart: '22:00', dutyEnd: '06:00',
    })
    expect(saved.mode).toBe('DUTY')
    expect(saved.platforms).toEqual(['xianyu', 'xhs'])
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/im/config?deviceId=dev-alpha-0001')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({
      enabled: true, platforms: ['xianyu', 'xhs'], mode: 'DUTY', dutyStart: '22:00', dutyEnd: '06:00',
    })
  })

  it('surfaces backend conflict details on save failures', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'platforms contains an unsupported value' }), { status: 409 }),
    )
    const error = await saveImConfig('dev-alpha-0001', {
      enabled: true, platforms: ['weibo'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00',
    }).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(ImApiError)
    expect((error as ImApiError).status).toBe(409)
    expect((error as ImApiError).message).toContain('监听平台包含不支持的取值')
    expect((error as ImApiError).message).toContain('HTTP 409')
  })

  it('maps a missing device to a readable error', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'device was not found' }), { status: 404 }),
    )
    const error = await saveImConfig('dev-missing', {
      enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00',
    }).catch((cause: unknown) => cause)
    expect((error as ImApiError).status).toBe(404)
    expect((error as ImApiError).message).toContain('设备不存在或无权访问')
  })

  it('flattens FastAPI 422 field problems into a readable message', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({
        detail: [
          { type: 'pattern_regex', loc: ['body', 'duty_start'], msg: "String should match pattern '^[0-2][0-9]:[0-5][0-9]$'" },
        ],
      }), { status: 422 }),
    )
    const error = await saveImConfig('dev-alpha-0001', {
      enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '9:00', dutyEnd: '23:00',
    }).catch((cause: unknown) => cause)
    expect((error as ImApiError).status).toBe(422)
    expect((error as ImApiError).message).toContain("String should match pattern")
    expect((error as ImApiError).message).toContain('HTTP 422')
  })

  it('fetches the per-device config over GET', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(configFixture({ mode: 'DUTY' })), { status: 200 }))
    const config = await fetchImConfig('dev-alpha-0001')
    expect(config.mode).toBe('DUTY')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/im/config?deviceId=dev-alpha-0001')
    expect(init.method).toBe('GET')
  })
})
