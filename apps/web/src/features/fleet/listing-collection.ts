import type { ListingCollectDevice } from '@/data/listing-info-collect'
import { deviceLabel } from '@/data/listing-info-collect'
import type { FleetListingItem } from './listings-api'

export interface ListingCollectAttempt {
  deviceId: string
  deviceName: string
  idempotencyKey: string
  state: 'pending' | 'dispatching' | 'accepted' | 'unresolved'
  taskId: string | null
  error: string
}

export function newListingCollectBatch(devices: readonly ListingCollectDevice[]): ListingCollectAttempt[] {
  const batchId = crypto.randomUUID()
  return [...new Map(devices.map((device) => [device.id, device])).values()].map((device) => ({
    deviceId: device.id,
    deviceName: deviceLabel(device),
    idempotencyKey: `listing-collect-${batchId}-${device.id}`,
    state: 'pending',
    taskId: null,
    error: '',
  }))
}

function presentString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

export function listingHistoryRows(items: readonly FleetListingItem[], request: number) {
  return items.map((item, index) => ({
    // Legacy rows have no cross-request identity. Keep every occurrence, even identical itemKeys.
    key: presentString(item.id) ? `id:${item.id}` : `legacy:${request}:${index}`,
    item,
  }))
}

export function listingSourceLabel(item: FleetListingItem, names: ReadonlyMap<string, string>): string {
  if (!presentString(item.deviceId)) return '未知来源'
  const name = names.get(item.deviceId)
  return name ? `${name}（${item.deviceId}）` : item.deviceId
}

export function listingPlatformLabel(item: FleetListingItem): string {
  if (!presentString(item.platform)) return '未知平台'
  return item.platform === 'xianyu' ? '闲鱼' : item.platform
}
