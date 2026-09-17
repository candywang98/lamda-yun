import { formatOrderAmount, formatOrderTime, type OrderDirection } from '@/api/orders'

/**
 * O10（fleet-first-20260916.1）订单历史切片的纯模型层。
 *
 * 后端事实（services/control-api/src/cloudctl_api/fleet_orders.py，只读消费）：
 * - GET /api/v1/fleet/orders/history 返回 items / total / offset / nextCursor /
 *   windows / dedupeMarkers；游标是不透明 base64 令牌，客户端只透传，不解码。
 * - 每个窗口（run）带 startedAt/endedAt、screensPresent、missingScreens、
 *   emptyScreens、partialScreens —— 历史报表必须注明采集窗口与缺失页，
 *   本文件把这些机器字段折叠成人读标注。
 * - 订单行的 dedupeMarker：REAL_ID（真实可见订单号）或 MISSING_ID（slice1 复合
 *   键降级，绝不拼凑假订单号）。
 */

export const ORDERS_HISTORY_UI_VERSION = 'orders-history/v1@20260917.1'

/** 历史行视图（fleet_orders._history_item_view，camelCase）。 */
export interface FleetOrderHistoryItem {
  id: string
  deviceId: string
  platform: string
  direction: OrderDirection | string
  orderKey: string
  itemTitle: string | null
  buyerName: string | null
  amountCents: number | null
  statusText: string | null
  occurredAt: string | null
  dedupeMarker: string | null
  createdAt: string
  updatedAt: string
}

/** 一个采集 run 的窗口标注原料（fleet_orders._window_view）。 */
export interface FleetOrderWindow {
  runKey: string
  accountKey: string
  deviceId: string
  direction: string
  startedAt: string | null
  endedAt: string | null
  screensPresent: number[]
  missingScreens: number[]
  emptyScreens: number[]
  partialScreens: number[]
  newKeys: number
  updatedKeys: number
  overlap: number
}

export interface FleetOrderHistoryResult {
  items: FleetOrderHistoryItem[]
  total: number
  offset: number
  nextCursor?: string
  windows: FleetOrderWindow[]
  dedupeMarkers: { realId: number; missingId: number }
}

/** 后端字段缺省/为空时的防御性归一（缺字段按空处理，不编造）。 */
export function normalizeHistoryResult(payload: unknown): FleetOrderHistoryResult {
  const raw = (payload && typeof payload === 'object' ? payload : {}) as Partial<FleetOrderHistoryResult>
  const windows = Array.isArray(raw.windows) ? raw.windows : []
  return {
    items: Array.isArray(raw.items) ? raw.items : [],
    total: typeof raw.total === 'number' ? raw.total : 0,
    offset: typeof raw.offset === 'number' ? raw.offset : 0,
    ...(typeof raw.nextCursor === 'string' && raw.nextCursor ? { nextCursor: raw.nextCursor } : {}),
    windows: windows.map((window) => ({
      ...window,
      screensPresent: Array.isArray(window.screensPresent) ? window.screensPresent : [],
      missingScreens: Array.isArray(window.missingScreens) ? window.missingScreens : [],
      emptyScreens: Array.isArray(window.emptyScreens) ? window.emptyScreens : [],
      partialScreens: Array.isArray(window.partialScreens) ? window.partialScreens : [],
    })),
    dedupeMarkers: {
      realId: typeof raw.dedupeMarkers?.realId === 'number' ? raw.dedupeMarkers.realId : 0,
      missingId: typeof raw.dedupeMarkers?.missingId === 'number' ? raw.dedupeMarkers.missingId : 0,
    },
  }
}

function screensLabel(screens: number[]): string {
  return screens.length > 0 ? screens.join('、') : '无'
}

/**
 * 采集窗口 + 缺失页标注（O10 §3）：窗口起止、已采屏、缺失屏、空页、部分可见屏、
 * 键计数。缺什么说什么；全齐时说全齐。
 */
export function windowAnnotation(window: FleetOrderWindow): string {
  const parts: string[] = []
  parts.push(`已采第 ${screensLabel(window.screensPresent)} 屏`)
  if (window.missingScreens.length > 0) {
    parts.push(`缺失第 ${window.missingScreens.join('、')} 屏`)
  }
  if (window.emptyScreens.length > 0) {
    parts.push(`第 ${window.emptyScreens.join('、')} 屏为空页`)
  }
  if (window.partialScreens.length > 0) {
    parts.push(`第 ${window.partialScreens.join('、')} 屏有部分可见行`)
  }
  parts.push(`新增 ${window.newKeys} 键`)
  if (window.updatedKeys > 0) {
    parts.push(`状态变化 ${window.updatedKeys} 键`)
  }
  if (window.startedAt && window.endedAt) {
    parts.push(`窗口 ${window.startedAt} ~ ${window.endedAt}`)
  } else {
    parts.push('窗口时间缺失')
  }
  return parts.join(' · ')
}

/** 窗口是否有缺失页（用于醒目徽标）。 */
export function hasMissingScreens(window: FleetOrderWindow): boolean {
  return window.missingScreens.length > 0
}

/** 去重标记摘要：真实订单号 vs 缺 ID 降级键（宁缺勿假，不混称）。 */
export function dedupeMarkerSummary(markers: { realId: number; missingId: number }): string {
  return `真实订单号 ${markers.realId} 条 · 缺 ID 降级 ${markers.missingId} 条`
}

/** 行级去重标记的人读标签。 */
export function dedupeMarkerLabel(marker: string | null | undefined): string {
  if (marker === 'REAL_ID') return '真实订单号'
  if (marker === 'MISSING_ID') return '缺 ID 降级'
  return marker || '—'
}

/** 游标分页：还有下一页（以后端 nextCursor 为准，客户端不解码）。 */
export function hasNextPage(result: FleetOrderHistoryResult): boolean {
  return typeof result.nextCursor === 'string' && result.nextCursor.length > 0
}

/** 行金额展示（复用 slice1 的分转元口径）。 */
export function historyAmountLabel(amountCents: number | null | undefined): string {
  return formatOrderAmount(amountCents)
}

/** 行时间展示（occurred_at 解析失败后端存空 → 占位符）。 */
export function historyTimeLabel(value: string | null | undefined): string {
  return formatOrderTime(value)
}
