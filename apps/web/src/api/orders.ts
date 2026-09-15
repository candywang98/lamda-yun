import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

// Local DTOs frozen at order-sync/20260915.1 (integration alignment, W1 afca8c2).
// Shared generated clients are Root-owned. 订单后端按仓库 camelCase 惯例序列化行视图；
// 查询参数按契约 §4 保持 snake_case（device_id/direction/status_text/limit/offset）。

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

/**
 * 契约 §4 列表行视图（W1 `orders_service._order_view` 实测线格式，camelCase）。
 * 列表项不含 raw；raw 仅在 GET /api/v1/orders/{id} 详情视图返回。
 */
export interface OrderRow {
  id: string
  deviceId: string
  platform: string
  direction: OrderDirection
  orderKey: string
  itemTitle: string | null
  buyerName: string | null
  amountCents: number | null
  statusText: string | null
  occurredAt: string | null
  createdAt: string
  updatedAt: string
}

/** 契约 §4 详情视图：列表行 + raw（行原文最小化快照）。 */
export interface OrderDetail extends OrderRow {
  raw: unknown
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

interface RequestOutcome {
  payload: unknown
  headers: Headers
}

async function performRequest(path: string, options: RequestOptions = {}): Promise<RequestOutcome> {
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
  return { payload, headers: response.headers }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { payload } = await performRequest(path, options)
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
  const data = await request<OrderListResult | null>(`/api/v1/orders${search ? `?${search}` : ''}`)
  return { items: data?.items ?? [], total: typeof data?.total === 'number' ? data.total : (data?.items ?? []).length }
}

/** 契约 §4：GET /api/v1/orders/{id}，含 raw；404 语义见后端。 */
export async function fetchOrder(id: string): Promise<OrderDetail> {
  return request<OrderDetail>(`/api/v1/orders/${encodeURIComponent(id)}`)
}

/**
 * 契约 §6：POST /api/v1/xianyu/orders:collect（Idempotency-Key 头，模式同 maintenance:run）。
 * 请求体后端 populate_by_name 双兼容，按契约保持 snake_case；响应 201（新建）/200（重放）
 * 并带 Idempotency-Replayed 响应头。
 */
export interface XianyuOrderCollectInput {
  deviceId: string
  direction: OrderDirection
  maxRows: number
}

export interface XianyuOrderCollectTask {
  taskId: string
  /** businessState 优先，缺省回退 runner status。 */
  state: string | null
  createdAt: string | null
  [key: string]: unknown
}

export interface XianyuOrderCollectResult {
  runId: string
  deviceId: string
  direction: OrderDirection
  maxRows: number
  commandType: string | null
  targetCount: number
  taskIds: string[]
  tasks: XianyuOrderCollectTask[]
  /** true = 幂等重放（HTTP 200）；false = 新建（HTTP 201）。来自 Idempotency-Replayed 响应头。 */
  idempotencyReplayed: boolean
}

export async function startXianyuOrderCollect(
  input: XianyuOrderCollectInput,
  idempotencyKey: string,
): Promise<XianyuOrderCollectResult> {
  const outcome = await performRequest('/api/v1/xianyu/orders:collect', {
    body: { device_id: input.deviceId, direction: input.direction, max_rows: input.maxRows },
    idempotencyKey,
  })
  const replayed = outcome.headers.get('Idempotency-Replayed')
  return {
    ...(typeof outcome.payload === 'object' && outcome.payload !== null ? outcome.payload : {}),
    idempotencyReplayed: replayed === 'true',
  } as XianyuOrderCollectResult
}

/**
 * 契约 §6：GET /api/v1/xianyu/orders/runs/{run_id} 聚合状态（W1 实测形状：
 * runId/deviceId/direction/maxRows/commandType/taskCount/summary/allTerminal/tasks）。
 */
export interface XianyuOrderRunTask {
  taskId: string
  state: string | null
  runnerStatus: string | null
  errorCode: string | null
  stallReason: string | null
  createdAt: string | null
  completedAt: string | null
  [key: string]: unknown
}

export interface XianyuOrderRunView {
  runId: string
  deviceId: string | null
  direction: OrderDirection | null
  maxRows: number | null
  commandType: string | null
  taskCount: number
  summary: Record<string, number>
  allTerminal: boolean
  tasks: XianyuOrderRunTask[]
  [key: string]: unknown
}

export async function fetchXianyuOrderRun(runId: string): Promise<XianyuOrderRunView> {
  return request<XianyuOrderRunView>(`/api/v1/xianyu/orders/runs/${encodeURIComponent(runId)}`)
}
