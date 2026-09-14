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

export class ImApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
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
    let detail = '请求失败'
    if (payload && typeof payload === 'object' && 'detail' in payload && typeof (payload as {detail: unknown}).detail === 'string') {
      detail = (payload as {detail: string}).detail
    }
    if (response.status === 409 && detail.includes('THREAD_REPLY_RATE_LIMITED')) {
      detail = '该会话 60 秒内只能回复一条，请稍后再试'
    } else if (response.status === 409 && detail.includes('DEVICE_BUSY')) {
      detail = '设备正在执行任务，等任务结束后再回复'
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
  return data.items ?? []
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

export interface ImMonitorConfig {
  deviceId: string
  enabled: boolean
  platforms: string[]
  mode: 'NOTIFICATION' | 'DUTY'
  dutyStart: string
  dutyEnd: string
  updatedAt: string | null
}

export async function fetchImConfig(deviceId: string): Promise<ImMonitorConfig> {
  return request<ImMonitorConfig>(`/config?deviceId=${encodeURIComponent(deviceId)}`)
}

export async function saveImConfig(deviceId: string, config: {
  enabled: boolean
  platforms: string[]
  mode: string
  dutyStart: string
  dutyEnd: string
}): Promise<ImMonitorConfig> {
  const headers = new Headers(controlApiHeaders())
  headers.set('Content-Type', 'application/json')
  const response = await fetch(
    `${controlApiBaseUrl()}/api/v1/im/config?deviceId=${encodeURIComponent(deviceId)}`,
    { method: 'PUT', headers, credentials: 'same-origin', body: JSON.stringify(config) },
  )
  if (!response.ok) throw new ImApiError(response.status, `保存失败（HTTP ${response.status}）`)
  return response.json() as Promise<ImMonitorConfig>
}
