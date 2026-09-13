import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

// Local DTOs frozen at p10-live/20260913.1.
export type LiveState = 'VIEWING' | 'REMOTE' | 'CLOSED'

export interface LiveSessionStatus {
  sessionId: string
  deviceId: string
  state: LiveState
  ageSeconds: number
  remainingSeconds: number
}

export class LiveApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function request<T>(method: string, path: string): Promise<T> {
  if (!controlApiConfigured) throw new LiveApiError(0, '未配置 Control API，无法使用实时观看')
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  const response = await fetch(`${controlApiBaseUrl()}${path}`, {
    method,
    headers,
    credentials: 'same-origin',
  })
  const text = await response.text()
  const payload = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = payload && typeof payload.detail === 'string' ? payload.detail : '请求失败'
    throw new LiveApiError(response.status, `${detail}（HTTP ${response.status}）`)
  }
  return payload as T
}

export function openLiveSession(deviceId: string): Promise<LiveSessionStatus> {
  return request('POST', `/api/v1/devices/${deviceId}/live`)
}

export function liveSessionStatus(deviceId: string, sid: string): Promise<LiveSessionStatus> {
  return request('GET', `/api/v1/devices/${deviceId}/live/${sid}`)
}

export function takeLiveControl(deviceId: string, sid: string): Promise<LiveSessionStatus> {
  return request('POST', `/api/v1/devices/${deviceId}/live/${sid}:take-control`)
}

export function releaseLiveControl(deviceId: string, sid: string): Promise<LiveSessionStatus> {
  return request('POST', `/api/v1/devices/${deviceId}/live/${sid}:release`)
}

export function stopLiveSession(deviceId: string, sid: string): Promise<LiveSessionStatus> {
  return request('POST', `/api/v1/devices/${deviceId}/live/${sid}:stop`)
}

export function liveStreamUrl(deviceId: string, sid: string): string {
  return `${controlApiBaseUrl().replace('https://', 'wss://')}/api/v1/devices/${deviceId}/live/${sid}/stream`
}
