import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

// Local DTOs frozen at pa-im/20260913.1. Shared generated clients are Root-owned.
export interface ImThread {
  id: string
  deviceId: string
  platform: string
  peerKey: string
  peerName: string
  lastMessageAt: string
  lastDirection: 'IN' | 'OUT'
  unreadCount: number
  /**
   * 最近一条消息的正文摘要。后端线程视图当前不返回该字段；
   * 该字段位为 Android 端正文回填（通知模式只拿到推送摘要）预留，
   * 一旦后端补充 lastMessageText，Web 侧无需再改即可直接展示。
   */
  lastMessageText?: string | null
  /** 摘要尚不可用（待 Android 端回填正文）时为 true，UI 显示「摘要待补全」。 */
  summaryPending?: boolean
}

export interface ImMessage {
  id: string
  threadId: string
  direction: 'IN' | 'OUT'
  contentType: string
  text: string
  occurredAt: string
  replyTaskId: string | null
}

export interface ImMonitorConfig {
  deviceId: string
  enabled: boolean
  platforms: string[]
  mode: 'NOTIFICATION' | 'DUTY'
  dutyStart: string
  dutyEnd: string
  updatedAt: string | null
}

export type ImMonitorConfigDraft = Omit<ImMonitorConfig, 'deviceId' | 'updatedAt'>

export const IM_PLATFORM_OPTIONS = [
  { key: 'xianyu', label: '闲鱼' },
  { key: 'xhs', label: '小红书' },
  { key: 'douyin', label: '抖音' },
  { key: 'wechat', label: '微信（仅收不发）' },
] as const

export type ImPlatformKey = (typeof IM_PLATFORM_OPTIONS)[number]['key']

const PLATFORM_LABELS: ReadonlyMap<string, string> = new Map(
  IM_PLATFORM_OPTIONS.map((option) => [option.key, option.label]),
)

const ALLOWED_PLATFORM_KEYS: ReadonlySet<string> = new Set(PLATFORM_LABELS.keys())

export function imPlatformLabel(platform: string): string {
  return PLATFORM_LABELS.get(platform) ?? platform
}

/**
 * 非闲鱼平台在手机端只上报私信类通知通道（channel 含 message/msg/im/chat/私信），
 * 信息流推送被设备端过滤；闲鱼 DM 通知无区分通道，全部上报。
 */
export function imPlatformDmFiltered(platform: string): boolean {
  return platform !== 'xianyu' && ALLOWED_PLATFORM_KEYS.has(platform)
}

/** 归一化线程视图：填充摘要字段位的默认值，未回填正文时标记 summaryPending。 */
export function normalizeImThread(raw: ImThread): ImThread {
  const text = typeof raw.lastMessageText === 'string' && raw.lastMessageText.trim()
    ? raw.lastMessageText
    : null
  return { ...raw, lastMessageText: text, summaryPending: text === null }
}

const CLOCK_PATTERN = /^[0-2][0-9]:[0-5][0-9]$/

/**
 * 客户端预检，镜像后端 ImConfigIn / ImService 的校验
 * （platforms 1..4 且取值受限、mode 枚举、duty 时钟格式）。
 */
export function validateImConfigDraft(draft: ImMonitorConfigDraft): string[] {
  const errors: string[] = []
  const platforms = Array.isArray(draft.platforms) ? draft.platforms : []
  if (platforms.length === 0) errors.push('至少选择一个监听平台')
  if (platforms.length > IM_PLATFORM_OPTIONS.length) {
    errors.push(`最多只能选择 ${IM_PLATFORM_OPTIONS.length} 个平台`)
  }
  const unknown = platforms.filter((key) => !ALLOWED_PLATFORM_KEYS.has(key))
  if (unknown.length > 0) errors.push(`不支持的平台：${unknown.join('、')}`)
  if (draft.mode !== 'NOTIFICATION' && draft.mode !== 'DUTY') errors.push('监听模式无效')
  if (draft.mode === 'DUTY') {
    if (!CLOCK_PATTERN.test(draft.dutyStart ?? '')) errors.push('值班开始时间格式应为 HH:MM')
    if (!CLOCK_PATTERN.test(draft.dutyEnd ?? '')) errors.push('值班结束时间格式应为 HH:MM')
  }
  return errors
}


export type ImDutyStatus = 'off' | 'inside' | 'outside'

/** 镜像 Android ImMonitorConfig.dutyActive，支持跨零点值班窗口。 */
export function imDutyStatus(
  config: Pick<ImMonitorConfig, 'enabled' | 'mode' | 'dutyStart' | 'dutyEnd'>,
  now: Date = new Date(),
): ImDutyStatus {
  if (!config.enabled || config.mode !== 'DUTY') return 'off'
  if (!CLOCK_PATTERN.test(config.dutyStart ?? '') || !CLOCK_PATTERN.test(config.dutyEnd ?? '')) return 'outside'
  const minutes = now.getHours() * 60 + now.getMinutes()
  const [startHours, startMinutes] = config.dutyStart.split(':').map(Number)
  const [endHours, endMinutes] = config.dutyEnd.split(':').map(Number)
  const start = startHours * 60 + startMinutes
  const end = endHours * 60 + endMinutes
  const active = start <= end ? minutes >= start && minutes < end : minutes >= start || minutes < end
  return active ? 'inside' : 'outside'
}

export function imDutyStatusLabel(status: ImDutyStatus): string {
  return { off: '', inside: '值班中', outside: '值班外' }[status]
}

export class ImApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

function responseDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return null
  const detail = (payload as { detail: unknown }).detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) =>
        item && typeof item === 'object' && 'msg' in item && typeof (item as { msg: unknown }).msg === 'string'
          ? (item as { msg: string }).msg
          : '',
      )
      .filter(Boolean)
    if (parts.length > 0) return parts.join('；')
  }
  return null
}

const CONFIG_ERROR_LABELS: ReadonlyArray<[string, string]> = [
  ['platforms must be a non-empty list', '至少选择一个监听平台'],
  ['platforms contains an unsupported value', '监听平台包含不支持的取值'],
  ['mode is invalid', '监听模式无效'],
  ['duty window is invalid', '值班时间段格式无效'],
  ['device was not found', '设备不存在或无权访问'],
]

function configErrorDetail(status: number, payload: unknown): string {
  const detail = responseDetail(payload)
  if (detail) {
    for (const [needle, label] of CONFIG_ERROR_LABELS) {
      if (detail.includes(needle)) return `${label}（HTTP ${status}）`
    }
    return `${detail}（HTTP ${status}）`
  }
  return `保存监听设置失败（HTTP ${status}）`
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  if (!controlApiConfigured) throw new ImApiError(0, '未配置 Control API，无法打开消息收件箱')
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${controlApiBaseUrl()}/api/v1/im${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    credentials: 'same-origin',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const text = await response.text()
  let payload: unknown = null
  try { payload = text ? JSON.parse(text) : null } catch { /* handled below */ }
  if (!response.ok) {
    const detail = responseDetail(payload) ?? '请求失败'
    if (response.status === 409 && detail.includes('THREAD_REPLY_RATE_LIMITED')) {
      throw new ImApiError(response.status, '该会话 60 秒内只能回复一条，请稍后再试')
    }
    if (response.status === 409 && detail.includes('DEVICE_BUSY')) {
      throw new ImApiError(response.status, '设备正在执行任务，等任务结束后再回复')
    }
    throw new ImApiError(response.status, `${detail}（HTTP ${response.status}）`)
  }
  return payload as T
}

export async function listImThreads(deviceId?: string, unread = false): Promise<ImThread[]> {
  const params = new URLSearchParams()
  if (deviceId) params.set('deviceId', deviceId)
  if (unread) params.set('unread', 'true')
  const query = params.toString()
  const data = await request<{ items: ImThread[] }>(`/threads${query ? `?${query}` : ''}`)
  return (data.items ?? []).map(normalizeImThread)
}

export async function listImMessages(threadId: string): Promise<ImMessage[]> {
  const data = await request<{ items: ImMessage[] }>(`/threads/${threadId}/messages?limit=200`)
  return data.items ?? []
}

export async function markImThreadRead(threadId: string): Promise<void> {
  await request(`/threads/${threadId}:mark-read`, {})
}

export async function replyImThread(threadId: string, text: string): Promise<{ taskId: string }> {
  return request<{ taskId: string }>(`/threads/${threadId}:reply`, { text })
}

export async function fetchImConfig(deviceId: string): Promise<ImMonitorConfig> {
  return request<ImMonitorConfig>(`/config?deviceId=${encodeURIComponent(deviceId)}`)
}

export async function saveImConfig(deviceId: string, config: ImMonitorConfigDraft): Promise<ImMonitorConfig> {
  const headers = new Headers(controlApiHeaders())
  headers.set('Content-Type', 'application/json')
  headers.set('Accept', 'application/json')
  const response = await fetch(
    `${controlApiBaseUrl()}/api/v1/im/config?deviceId=${encodeURIComponent(deviceId)}`,
    { method: 'PUT', headers, credentials: 'same-origin', body: JSON.stringify(config) },
  )
  const text = await response.text()
  let payload: unknown = null
  try { payload = text ? JSON.parse(text) : null } catch { /* handled below */ }
  if (!response.ok) throw new ImApiError(response.status, configErrorDetail(response.status, payload))
  return payload as ImMonitorConfig
}
