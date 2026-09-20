import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

/** P43/P44 fleet listing collection web client (listing-collect/20260920.1). */

export interface FleetListingItem {
  itemKey: string
  dedupeMarker: string
  title: string | null
  priceCents: number | null
  priceText: string | null
  statusText: string | null
  snapshotCount: number
  firstSeenAt: string
  lastSeenAt: string
}

export interface FleetListingHistoryResult {
  items: FleetListingItem[]
  total: number
  nextCursor: string | null
}

export class FleetListingsApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

function responseDetail(payload: unknown): string | null {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
  }
  return null
}

export async function listFleetListings(
  query: { deviceId?: string; limit?: number; cursor?: string } = {},
): Promise<FleetListingHistoryResult> {
  if (!controlApiConfigured) throw new FleetListingsApiError(0, '未配置 Control API，无法读取宝贝列表')
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  const params = new URLSearchParams()
  if (query.deviceId) params.set('device_id', query.deviceId)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.cursor) params.set('cursor', query.cursor)
  const search = params.toString()
  const response = await fetch(
    `${controlApiBaseUrl()}/api/v1/fleet/listings/history${search ? `?${search}` : ''}`,
    { method: 'GET', headers, credentials: 'same-origin' },
  )
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    /* handled below */
  }
  if (!response.ok || !payload || typeof payload !== 'object') {
    const detail = responseDetail(payload) ?? '请求失败'
    throw new FleetListingsApiError(response.status, `${detail}（HTTP ${response.status}）`)
  }
  const body = payload as { items?: unknown; total?: unknown; nextCursor?: unknown }
  const items = Array.isArray(body.items) ? (body.items as FleetListingItem[]) : []
  return {
    items,
    total: typeof body.total === 'number' ? body.total : items.length,
    nextCursor: typeof body.nextCursor === 'string' ? body.nextCursor : null,
  }
}

/** Dispatch one read-only collect task to a device (xy-tasks-24). */
export async function dispatchListingCollectTask(input: {
  deviceId: string
  idempotencyKey: string
}): Promise<{ taskId: string }> {
  if (!controlApiConfigured) throw new FleetListingsApiError(0, '未配置 Control API，无法派发采集任务')
  const headers = new Headers(controlApiHeaders())
  headers.set('Content-Type', 'application/json')
  headers.set('Idempotency-Key', input.idempotencyKey)
  const response = await fetch(`${controlApiBaseUrl()}/api/v1/mobile/tasks`, {
    method: 'POST',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify({
      deviceId: input.deviceId,
      targetPackage: 'com.taobao.idlefish',
      commandType: 'xianyu.collect_listings',
      totalTimeoutMs: 900000,
      steps: [
        {
          stepId: 'open-profile',
          timeoutMs: 30000,
          action: 'ui.tap',
          locatorRef: 'xianyu_profile_tab',
        },
        {
          stepId: 'open-published',
          timeoutMs: 30000,
          action: 'ui.tap',
          locatorRef: 'xianyu_my_published',
        },
        {
          stepId: 'wait-onsale-tab',
          timeoutMs: 30000,
          action: 'ui.wait',
          locatorRef: 'xianyu_pub_tab_onsale',
          condition: 'EXISTS',
          pollMs: 500,
        },
        {
          stepId: 'collect-all',
          timeoutMs: 600000,
          action: 'ui.collectListings',
          tab: 'onsale',
          maxScreens: 40,
        },
      ],
    }),
  })
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    /* handled below */
  }
  if (!response.ok) {
    const detail = responseDetail(payload) ?? '派发失败'
    throw new FleetListingsApiError(response.status, `${detail}（HTTP ${response.status}）`)
  }
  const body = payload as { taskId?: string; id?: string }
  const taskId = body.taskId ?? body.id ?? ''
  return { taskId }
}
