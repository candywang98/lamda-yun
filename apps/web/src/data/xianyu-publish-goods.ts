import {
  persistJson,
  readJson,
  recordTask,
  type XianyuSchedule,
} from './xianyu-task-devices'
import type { JsonObject, ProductView, SessionInfo } from '@cloudctl/api-contracts'
import { controlApiConfigured, createControlApiClient } from '@/api/control'

export type PublishAllocation = 'default' | 'even'
export type OnOff = 'on' | 'off'
export type InspectMode = 'none' | 'on' | 'off'
export type PublishFormMode = 'direct' | 'draft'
export type AddressMode = 'default' | 'device' | 'random' | 'multi'

export const VIDEO_MUSIC_OPTIONS = [
  '随机音乐',
  '欢快-Spring+In+My+Step',
  '舒缓-Ukulele+Beach',
  '动感-About+That+Oldie',
  '舒缓-Every+Step',
  '轻松-Tracks+Of+My+Fears',
  '浪漫-Wigs',
  '动感-Bonanza',
  '动感-Out+for+Blood',
] as const

export const FAN_DISCOUNT_OPTIONS = ['不优惠', '优惠1%', '优惠3%', '优惠5%', '优惠10%'] as const

export interface XianyuPublishGoodsConfig {
  deviceIds: string[]
  productIds: string[]
  allocation: PublishAllocation
  app: 'main'
  smartVideo: OnOff
  music: (typeof VIDEO_MUSIC_OPTIONS)[number]
  circle: string
  fanDiscount: (typeof FAN_DISCOUNT_OPTIONS)[number]
  intervalSeconds: number
  multiSpec: OnOff
  autoShortTitle: OnOff
  aiPolish: OnOff
  stripEmoji: OnOff
  inspect: InspectMode
  imageLabels: OnOff
  watermark: OnOff
  creativeCopy: OnOff
  formMode: PublishFormMode
  clearCache: OnOff
  insertImage: string
  descPool: string
  randomCover: OnOff
  randomTitle: OnOff
  addressMode: AddressMode
  addressPool: string
  schedule: XianyuSchedule
}

export const XY_PUBLISH_GOODS_CONFIG_KEY = 'cloudctl.xianyu-publish-goods.config'
export const XY_PUBLISH_GOODS_TASKS_KEY = 'cloudctl.xianyu-publish-goods.tasks'
export const PUBLISH_QUEUE_BOUNDARY = 'HUMAN_PRICE_HUMAN_COMMIT' as const

export interface XianyuPublishQueueItem {
  readonly description: string
  readonly price: string
  readonly mediaAssetIds?: readonly string[]
  readonly deliveryId?: string
  readonly completionBoundary: typeof PUBLISH_QUEUE_BOUNDARY
}

export interface XianyuPublishQueueRequest {
  readonly queueId: string
  readonly deviceId: string
  readonly accountId: string
  readonly items: readonly XianyuPublishQueueItem[]
}

export interface PublishQueueScope {
  tenantId: string
  userId: string
  apiEnvironment: string
}

export function publishQueueScope(session: SessionInfo | null): PublishQueueScope | null {
  const configuredUrl = import.meta.env.VITE_CONTROL_API_URL?.trim()
  if (!controlApiConfigured || !configuredUrl || !session
    || !validText(session.tenantId, 36) || !validText(session.userId, 36)) return null
  return {
    tenantId: session.tenantId, userId: session.userId,
    apiEnvironment: `${window.location.origin}|${configuredUrl.replace(/\/$/, '')}`,
  }
}

export interface XianyuPublishQueueTarget {
  targetId: string
  queueId: string
  position: number
  deviceId: string
  accountId: string
  state: string
  item: XianyuPublishQueueItem
  taskIds: string[]
  externalItemId: string | null
}

export interface XianyuPublishQueueView {
  queueId: string
  deviceId: string
  accountId: string
  replayed: boolean
  serialAdvanceBlocked: boolean
  targets: XianyuPublishQueueTarget[]
}

export function emptyPublishGoodsConfig(partial: Partial<XianyuPublishGoodsConfig> = {}): XianyuPublishGoodsConfig {
  return {
    deviceIds: [],
    productIds: [],
    allocation: 'even',
    smartVideo: 'off',
    music: '随机音乐',
    circle: '',
    fanDiscount: '优惠1%',
    intervalSeconds: 1,
    multiSpec: 'on',
    autoShortTitle: 'off',
    aiPolish: 'off',
    stripEmoji: 'on',
    inspect: 'none',
    imageLabels: 'on',
    watermark: 'off',
    creativeCopy: 'off',
    formMode: 'direct',
    clearCache: 'on',
    insertImage: '',
    descPool: '',
    randomCover: 'off',
    randomTitle: 'off',
    addressMode: 'default',
    addressPool: '',
    schedule: '立即执行',
    ...partial,
    app: 'main' as const,
  }
}

export function loadPublishGoodsConfig(): XianyuPublishGoodsConfig {
  return emptyPublishGoodsConfig(readJson(XY_PUBLISH_GOODS_CONFIG_KEY, {}))
}

export function savePublishGoodsConfig(config: XianyuPublishGoodsConfig): XianyuPublishGoodsConfig {
  const next = emptyPublishGoodsConfig(config)
  persistJson(XY_PUBLISH_GOODS_CONFIG_KEY, next)
  return next
}

export function recordPublishGoodsTask(config: XianyuPublishGoodsConfig) {
  recordTask(XY_PUBLISH_GOODS_TASKS_KEY, config)
}

export function buildXianyuPublishQueueItems(products: ProductView[], productIds: string[]): XianyuPublishQueueItem[] {
  if (productIds.length === 0 || productIds.length > 50) throw new Error('每个队列需要 1 至 50 件商品')
  if (new Set(productIds).size !== productIds.length) throw new Error('不能重复选择同一件商品')
  return productIds.map((productId) => {
    const product = products.find((item) => item.id === productId)
    if (!product || product.status !== 'ACTIVE') throw new Error(`商品 ${productId} 不在当前 API 可用商品目录中`)
    const description = product.description
    const price = product.price
    if (!validText(description, 1024)) throw new Error(`商品“${product.title}”描述须为 1 至 1024 字符且不能包含 NUL`)
    if (typeof price !== 'string' || !/^[0-9]+(\.[0-9]{1,2})?$/.test(price)) throw new Error(`商品“${product.title}”价格无效`)
    const mediaAssetIds = product.mediaAssetIds
    if (!Array.isArray(mediaAssetIds) || mediaAssetIds.length > 49
      || mediaAssetIds.some((id) => typeof id !== 'string' || !id.trim())
      || new Set(mediaAssetIds).size !== mediaAssetIds.length) {
      throw new Error(`商品“${product.title}”媒体资产须为至多 49 个不重复的非空 ID`)
    }
    return {
      description,
      price,
      completionBoundary: PUBLISH_QUEUE_BOUNDARY,
      ...(mediaAssetIds.length > 0 ? { mediaAssetIds: [...mediaAssetIds] } : {}),
    }
  })
}

function validText(value: unknown, max: number): value is string {
  return typeof value === 'string' && !!value.trim() && !value.includes('\0') && [...value].length <= max
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

const targetStates = new Set(['PENDING', 'IN_FLIGHT', 'FAILED_UNCONFIRMED', 'SUCCEEDED_CONFIRMED', 'FAILED_CONFIRMED', 'CANCELLED'])
const boundaries = new Set(['FULL_AUTO', 'AUTO_FILL_HUMAN_PRICE', 'AUTO_FILL_HUMAN_COMMIT', PUBLISH_QUEUE_BOUNDARY])

export function parseXianyuPublishQueue(raw: unknown, expected: XianyuPublishQueueRequest): XianyuPublishQueueView {
  const invalid = () => new Error(`队列 ${expected.queueId} 响应不完整或与请求不一致；结果未确认，请重试查询同一队列`)
  if (!isRecord(raw) || raw.queueId !== expected.queueId || raw.deviceId !== expected.deviceId
    || raw.accountId !== expected.accountId || typeof raw.replayed !== 'boolean'
    || typeof raw.serialAdvanceBlocked !== 'boolean' || !Array.isArray(raw.targets)
    || raw.targets.length !== expected.items.length) throw invalid()
  const targetIds = new Set<string>()
  const positions = new Set<number>()
  const targets = raw.targets.map((target: unknown): XianyuPublishQueueTarget => {
    if (!isRecord(target) || !validText(target.targetId, 36) || targetIds.has(target.targetId)
      || target.queueId !== expected.queueId || target.deviceId !== expected.deviceId || target.accountId !== expected.accountId
      || typeof target.position !== 'number' || !Number.isInteger(target.position) || positions.has(target.position)
      || typeof target.state !== 'string' || !targetStates.has(target.state)
      || !Array.isArray(target.taskIds) || !target.taskIds.every((id: unknown) => validText(id, 36))
      || new Set(target.taskIds).size !== target.taskIds.length
      || !(target.externalItemId === null || validText(target.externalItemId, 64))
      || !(target.recordedBoundary === null || typeof target.recordedBoundary === 'string' && boundaries.has(target.recordedBoundary))
      || typeof target.boundaryDowngraded !== 'boolean' || !isRecord(target.judgment) || !isRecord(target.result)
      || !(target.confirmedAt === null || typeof target.confirmedAt === 'string' && Number.isFinite(Date.parse(target.confirmedAt)))
      || !isRecord(target.item)) throw invalid()
    const item = expected.items[target.position]
    if (!item || target.claimedBoundary !== item.completionBoundary
      || target.item.description !== item.description || target.item.price !== item.price
      || target.item.completionBoundary !== item.completionBoundary || target.item.deliveryId !== item.deliveryId
      || JSON.stringify(target.item.mediaAssetIds) !== JSON.stringify(item.mediaAssetIds)
      || Object.keys(target.item).some((key) => !['description', 'price', 'completionBoundary', 'mediaAssetIds', 'deliveryId'].includes(key))) throw invalid()
    targetIds.add(target.targetId)
    positions.add(target.position)
    return {
      targetId: target.targetId, queueId: expected.queueId, position: target.position,
      deviceId: expected.deviceId, accountId: expected.accountId, state: target.state,
      item, taskIds: [...target.taskIds], externalItemId: target.externalItemId,
    }
  })
  if (raw.serialAdvanceBlocked !== targets.some((target) => target.state === 'IN_FLIGHT')) throw invalid()
  return {
    queueId: expected.queueId, deviceId: expected.deviceId, accountId: expected.accountId,
    replayed: raw.replayed, serialAdvanceBlocked: raw.serialAdvanceBlocked,
    targets: targets.sort((a, b) => a.position - b.position),
  }
}

export function prepareXianyuPublishQueue(input: {
  deviceId: string
  accountId: string
  items: readonly XianyuPublishQueueItem[]
}): XianyuPublishQueueRequest {
  if (!validText(input.deviceId, 36) || !validText(input.accountId, 36)) throw new Error('设备和 accountId 必须明确且有效')
  if (input.items.length < 1 || input.items.length > 50) throw new Error('每个队列需要 1 至 50 件商品')
  return Object.freeze({
    queueId: crypto.randomUUID(), deviceId: input.deviceId, accountId: input.accountId,
    items: Object.freeze(input.items.map((item) => Object.freeze({
      description: item.description, price: item.price, completionBoundary: PUBLISH_QUEUE_BOUNDARY,
      ...(item.mediaAssetIds?.length ? {
        mediaAssetIds: Object.freeze([...item.mediaAssetIds]),
        // Staging identity only, never a media delivery receipt.
        deliveryId: crypto.randomUUID(),
      } : {}),
    }))),
  })
}

async function fingerprint(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(value))
  const hash = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

// Persist request identities only. Products and account authority must be reloaded from API.
export async function persistXianyuPublishQueue(
  scope: PublishQueueScope | null,
  input: { deviceId: string; accountId: string; items: readonly XianyuPublishQueueItem[] },
  productIds: readonly string[],
  known?: XianyuPublishQueueRequest,
): Promise<XianyuPublishQueueRequest> {
  if (!scope || !validText(scope.tenantId, 36) || !validText(scope.userId, 36) || !scope.apiEnvironment) {
    throw new Error('缺少已验证的租户、用户或 API 环境，不能创建队列')
  }
  const scopeHash = await fingerprint([scope.tenantId, scope.userId, scope.apiEnvironment])
  const requestHash = await fingerprint({
    productIds, deviceId: input.deviceId, accountId: input.accountId,
    items: input.items.map((item) => ({
      description: item.description, price: item.price, mediaAssetIds: item.mediaAssetIds ?? [],
      completionBoundary: PUBLISH_QUEUE_BOUNDARY,
    })),
  })
  const key = `cloudctl.xianyu-publish-queue.v1.${scopeHash}.${requestHash}`
  try {
    const storage = window.sessionStorage
    const existing = storage.getItem(key)
    let request: XianyuPublishQueueRequest
    let serialized: string
    if (existing !== null) {
      const record: unknown = JSON.parse(existing)
      const uuid = (value: unknown): value is string => typeof value === 'string'
        && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
      if (!isRecord(record) || record.version !== 1 || record.scopeHash !== scopeHash
        || record.requestHash !== requestHash || !uuid(record.queueId)
        || !Array.isArray(record.deliveryIds) || record.deliveryIds.length !== input.items.length
        || !record.deliveryIds.every((id: unknown, index: number) => input.items[index]!.mediaAssetIds?.length ? uuid(id) : id === null)
        || new Set(record.deliveryIds.filter((id) => id !== null)).size !== record.deliveryIds.filter((id) => id !== null).length
        || record.deliveryIds.includes(record.queueId)) throw new Error('corrupt retry record')
      if (record.identityHash !== await fingerprint([scopeHash, requestHash, record.queueId, record.deliveryIds])) {
        throw new Error('retry record checksum mismatch')
      }
      const deliveryIds = record.deliveryIds
      request = Object.freeze({
        queueId: record.queueId, deviceId: input.deviceId, accountId: input.accountId,
        items: Object.freeze(input.items.map((item, index) => Object.freeze({
          description: item.description, price: item.price, completionBoundary: PUBLISH_QUEUE_BOUNDARY,
          ...(item.mediaAssetIds?.length ? {
            mediaAssetIds: Object.freeze([...item.mediaAssetIds]), deliveryId: String(deliveryIds[index]),
          } : {}),
        }))),
      })
      if (known && JSON.stringify(request) !== JSON.stringify(known)) throw new Error('retry identity changed')
      serialized = existing
    } else {
      if (known) throw new Error('retry record lost')
      request = prepareXianyuPublishQueue(input)
      const deliveryIds = request.items.map((item) => item.deliveryId ?? null)
      serialized = JSON.stringify({
        version: 1, scopeHash, requestHash, queueId: request.queueId,
        deliveryIds, identityHash: await fingerprint([scopeHash, requestHash, request.queueId, deliveryIds]),
      })
    }
    // Write and read back before POST, including retries; storage failures are not ignorable.
    storage.setItem(key, serialized)
    if (storage.getItem(key) !== serialized) throw new Error('retry record verification failed')
    return request
  } catch {
    throw new Error('队列重试身份存储失败或损坏；已阻止请求，请保留当前标签页记录供核查')
  }
}

export async function createXianyuPublishQueue(input: XianyuPublishQueueRequest): Promise<XianyuPublishQueueView> {
  if (!controlApiConfigured) throw new Error('当前未连接 Control API，不能创建服务端队列')
  const body: JsonObject = {
    queueId: input.queueId,
    deviceId: input.deviceId,
    accountId: input.accountId,
    items: input.items.map((item) => ({
      description: item.description, price: item.price, completionBoundary: PUBLISH_QUEUE_BOUNDARY,
      ...(item.mediaAssetIds ? { mediaAssetIds: [...item.mediaAssetIds], deliveryId: item.deliveryId! } : {}),
    })),
  }
  return parseXianyuPublishQueue(await createControlApiClient().createXianyuPublishQueue(body), input)
}

export async function getXianyuPublishQueue(input: XianyuPublishQueueRequest): Promise<XianyuPublishQueueView> {
  if (!controlApiConfigured) throw new Error('当前未连接 Control API，不能查询服务端队列')
  return parseXianyuPublishQueue(await createControlApiClient().xianyuPublishQueue(input.queueId), input)
}

export function allocateProducts(productIds: string[], deviceIds: string[], allocation: PublishAllocation): Array<{ deviceId: string; productId: string }> {
  if (productIds.length === 0 || deviceIds.length === 0) return []
  if (allocation === 'default') {
    return deviceIds.flatMap((deviceId) => productIds.map((productId) => ({ deviceId, productId })))
  }
  return productIds.map((productId, index) => ({
    deviceId: deviceIds[index % deviceIds.length]!,
    productId,
  }))
}
