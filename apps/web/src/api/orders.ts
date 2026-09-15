import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

// Local DTOs frozen at order-sync/20260915.1. Shared generated clients are Root-owned.
// 订单后端按契约返回 snake_case 字段（contract §2/§4），与 im 的 camelCase 线格式不同。

export type OrderDirection = 'SOLD' | 'BOUGHT'

export const ORDER_DIRECTION_OPTIONS = [
  { key: 'SOLD', label: '我卖出的' },
  { key: 'BOUGHT', label: '我买到的' },
] as const

const DIRECTION_KEYS: ReadonlySet<string> = new Set(ORDER_DIRECTION_OPTIONS.map((option) => option.key))

export function isOrderDirection(value: string): value is OrderDirection {
  return DIRECTION_KEYS.has(value)
}

export function orderDirectionLabel(direction: string): string {
  if (direction === 'SOLD') return '我卖出的'
  if (direction === 'BOUGHT') return '我买到的'
  return direction
}

/** 契约 §2：xianyu_order 行视图。字段与后端 snake_case 线格式一致。 */
export interface OrderRow {
  id: string
  tenant_id: string
  device_id: string
  platform: string
  direction: OrderDirection
  order_key: string
  item_title: string | null
  buyer_name: string | null
  amount_cents: number | null
  status_text: string | null
  occurred_at: string | null
  raw: unknown
  created_at: string
  updated_at: string
}

export interface OrderListResult {
  items: OrderRow[]
  total: number
}

export interface OrderListQuery {
  deviceId?: string
  direction?: OrderDirection | ''
  statusText?: string
  limit?: number
  offset?: number
}

/** 金额分转元展示：整数运算避免浮点误差，空值显示占位符。 */
export function formatOrderAmount(amountCents: number | null | undefined): string {
  if (typeof amountCents !== 'number' || !Number.isFinite(amountCents)) return '—'
  const sign = amountCents < 0 ? '-' : ''
  const abs = Math.abs(Math.trunc(amountCents))
  const yuan = Math.trunc(abs / 100)
  const cents = abs % 100
  return `${sign}¥${yuan}.${String(cents).padStart(2, '0')}`
}

/** 订单时间本地化展示；occurred_at 解析失败时后端存空，显示占位符。 */
export function formatOrderTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
}

export class OrdersApiError extends Error {
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

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  idempotencyKey?: string
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!controlApiConfigured) throw new OrdersApiError(0, '未配置 Control API，无法读取订单')
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  if (options.body !== undefined) headers.set('Content-Type', 'application/json')
  if (options.idempotencyKey) headers.set('Idempotency-Key', options.idempotencyKey)
  const response = await fetch(`${controlApiBaseUrl()}${path}`, {
    method: options.method ?? (options.body !== undefined ? 'POST' : 'GET'),
    headers,
    credentials: 'same-origin',
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
  })
  const text = await response.text()
  let payload: unknown = null
  try { payload = text ? JSON.parse(text) : null } catch { /* handled below */ }
  if (!response.ok) {
    const detail = responseDetail(payload) ?? '请求失败'
    if (response.status === 404) {
      throw new OrdersApiError(response.status, `订单不存在或已被删除（HTTP ${response.status}）`)
    }
    throw new OrdersApiError(response.status, `${detail}（HTTP ${response.status}）`)
  }
  return payload as T
}

/** 契约 §4：GET /api/v1/orders，limit 1..100 默认 20，按 occurred_at/created_at DESC。 */
export async function listOrders(query: OrderListQuery = {}): Promise<OrderListResult> {
  const params = new URLSearchParams()
  if (query.deviceId) params.set('device_id', query.deviceId)
  if (query.direction) params.set('direction', query.direction)
  if (query.statusText) params.set('status_text', query.statusText)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  const search = params.toString()
  const data = await request<OrderListResult>(`/api/v1/orders${search ? `?${search}` : ''}`)
  return { items: data?.items ?? [], total: typeof data?.total === 'number' ? data.total : (data?.items ?? []).length }
}

/** 契约 §4：GET /api/v1/orders/{id}，404 语义见后端。 */
export async function fetchOrder(id: string): Promise<OrderRow> {
  return request<OrderRow>(`/api/v1/orders/${encodeURIComponent(id)}`)
}

/** 契约 §6：POST /api/v1/xianyu/orders:collect（Idempotency-Key 头，模式同 maintenance:run）。 */
export interface XianyuOrderCollectInput {
  deviceId: string
  direction: OrderDirection
  maxRows: number
}

export interface XianyuOrderCollectResult {
  run_id: string
}

export async function startXianyuOrderCollect(
  input: XianyuOrderCollectInput,
  idempotencyKey: string,
): Promise<XianyuOrderCollectResult> {
  return request<XianyuOrderCollectResult>('/api/v1/xianyu/orders:collect', {
    body: { device_id: input.deviceId, direction: input.direction, max_rows: input.maxRows },
    idempotencyKey,
  })
}

/**
 * 契约 §6：GET /api/v1/xianyu/orders/runs/{run_id} 聚合状态。
 * 响应形状契约未冻结，仅约束 run_id 定位；这里按宽松视图透传，
 * 等 W1 冻结 run 视图后再收紧（未决项）。
 */
export interface XianyuOrderRunView {
  run_id: string
  status?: string
  [key: string]: unknown
}

export async function fetchXianyuOrderRun(runId: string): Promise<XianyuOrderRunView> {
  return request<XianyuOrderRunView>(`/api/v1/xianyu/orders/runs/${encodeURIComponent(runId)}`)
}
