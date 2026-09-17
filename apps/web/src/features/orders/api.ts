import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'
import { normalizeHistoryResult, type FleetOrderHistoryResult } from './model'

/**
 * O10 订单历史切片 API 层：GET /api/v1/fleet/orders/history。
 * 查询参数按后端 fleet_orders.py 保持 snake_case（device_id / status_text /
 * account_key / limit / cursor）；游标是不透明令牌，只透传。错误口径与
 * src/api/orders.ts 一致：fail-closed，如实展示后端 detail。
 */

export interface FleetOrderHistoryQuery {
  deviceId?: string
  direction?: 'SOLD' | 'BOUGHT' | ''
  statusText?: string
  accountKey?: string
  limit?: number
  cursor?: string
}

export class FleetOrdersApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

function responseDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return null
  const detail = (payload as { detail: unknown }).detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return null
}

export async function listFleetOrderHistory(query: FleetOrderHistoryQuery = {}): Promise<FleetOrderHistoryResult> {
  if (!controlApiConfigured) throw new FleetOrdersApiError(0, '未配置 Control API，无法读取订单历史')
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  const params = new URLSearchParams()
  if (query.deviceId) params.set('device_id', query.deviceId)
  if (query.direction) params.set('direction', query.direction)
  if (query.statusText) params.set('status_text', query.statusText)
  if (query.accountKey) params.set('account_key', query.accountKey)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.cursor) params.set('cursor', query.cursor)
  const search = params.toString()
  const response = await fetch(`${controlApiBaseUrl()}/api/v1/fleet/orders/history${search ? `?${search}` : ''}`, {
    method: 'GET',
    headers,
    credentials: 'same-origin',
  })
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    /* handled below */
  }
  if (!response.ok) {
    const detail = responseDetail(payload) ?? '请求失败'
    throw new FleetOrdersApiError(response.status, `${detail}（HTTP ${response.status}）`)
  }
  return normalizeHistoryResult(payload)
}
