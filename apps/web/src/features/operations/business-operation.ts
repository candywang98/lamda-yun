import type {
  BatchOperationCreate,
  JsonObject,
  JsonValue,
  OperationCatalogEntry,
  OperationFeatureEntry,
  OperationTaskCreate,
} from '@cloudctl/api-contracts'
import type { OperationDefinition } from '@/data/operations-catalog'
import type { OperationPageParameterValues } from '@/data/operation-parameters'
import { buildOperationParameters } from '@/data/operation-parameters'

export type BusinessOperationAvailability = 'ENABLED' | 'PENDING' | 'POLICY_BLOCKED' | 'OUT_OF_SCOPE'
export type OperationConnection = 'connecting' | 'live' | 'mock' | 'unavailable'

export interface AvailabilityResult {
  state: BusinessOperationAvailability
  reason: string
  canMint: boolean
}

export interface BusinessOperationContext {
  deviceScope: string
  executionApp: string
  schedule: string
  snapshot: string
  reason: string
  source: 'web'
  mode: OperationDefinition['mode']
  sourcePage: number
  sourceRoute: string
}

export interface BusinessOperationRequestSnapshot extends JsonObject {
  operationKey: string
  featureId: string
  resourceIds: string[]
  parameters: JsonObject
  context: BusinessOperationContext & JsonObject
  batch: boolean
}

const AVAILABILITY_PREFIX = /^\[(PENDING|POLICY_BLOCKED|OUT_OF_SCOPE)\]\s*(.*)$/s

function unavailable(state: Exclude<BusinessOperationAvailability, 'ENABLED'>, reason: string): AvailabilityResult {
  return { state, reason, canMint: false }
}

export function resolveBusinessOperationAvailability(input: {
  operation: OperationDefinition
  connection: OperationConnection
  catalog?: OperationCatalogEntry
  feature?: OperationFeatureEntry
}): AvailabilityResult {
  const { operation, connection, catalog, feature } = input
  const backendReason = feature?.reason.match(AVAILABILITY_PREFIX)
  if (backendReason) {
    return unavailable(
      backendReason[1] as Exclude<BusinessOperationAvailability, 'ENABLED'>,
      backendReason[2] || feature?.reason || '后端未提供可用性原因',
    )
  }
  if (operation.risk === 'blocked' || feature?.policy === 'blocked') {
    return unavailable('POLICY_BLOCKED', feature?.reason || '生产策略明确阻断该能力')
  }
  if (!operation.backendOperationKey || feature?.policy === 'unmapped') {
    return unavailable('OUT_OF_SCOPE', feature?.reason || '该入口没有已登记的后端操作映射')
  }
  if (connection === 'mock') {
    return unavailable('PENDING', 'Mock 模式只展示表单，不创建业务操作')
  }
  if (connection === 'connecting') return unavailable('PENDING', '正在读取 Control API 可用性目录')
  if (connection === 'unavailable') return unavailable('PENDING', 'Control API 未配置或连接失败')
  if (!feature) return unavailable('PENDING', '后端功能目录未返回当前 featureId')
  if (!catalog) return unavailable('PENDING', '后端操作目录未返回当前 operationKey')
  if (feature.operationKey !== operation.backendOperationKey || !catalog.featureIds.includes(operation.id)) {
    return unavailable('PENDING', '后端目录未确认 featureId 与 operationKey 映射')
  }
  if (feature.risk !== operation.risk || catalog.risk !== operation.risk) {
    return unavailable('PENDING', '前后端风险等级不一致')
  }
  if (!catalog.allowedParameters.includes('pageParameters')) {
    return unavailable('PENDING', '后端目录未声明 pageParameters 参数合同')
  }
  if (!feature.authorized || !catalog.authorized) {
    return unavailable('PENDING', feature.reason || '当前身份没有该操作权限')
  }
  if (!feature.executable || !feature.allowed || !catalog.allowed || !catalog.executorAvailable) {
    return unavailable('PENDING', feature.reason || '操作执行器尚不可用')
  }
  return { state: 'ENABLED', reason: feature.reason || '后端已确认可执行', canMint: true }
}

function cloneJson<T extends JsonValue>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function deepFreeze<T>(value: T): Readonly<T> {
  if (value !== null && typeof value === 'object') {
    Object.freeze(value)
    for (const child of Object.values(value)) deepFreeze(child)
  }
  return value
}

export function freezeBusinessOperationRequest(input: {
  operation: OperationDefinition
  catalog: OperationCatalogEntry
  pageParameters: OperationPageParameterValues
  resourceIds: string[]
  context: BusinessOperationContext
}): Readonly<BusinessOperationRequestSnapshot> {
  if (!input.operation.backendOperationKey) throw new Error('当前功能没有后端 operationKey')
  const resourceIds = [...new Set(input.resourceIds.map((value) => value.trim()).filter(Boolean))]
  if (resourceIds.length === 0) throw new Error('至少需要一个资源 ID')
  if (resourceIds.length > 1 && !input.catalog.batchAllowed) throw new Error('该后端操作不允许批量提交')
  const snapshot: BusinessOperationRequestSnapshot = {
    operationKey: input.operation.backendOperationKey,
    featureId: input.operation.id,
    resourceIds,
    parameters: buildOperationParameters(input.operation.pageProfile, input.pageParameters, input.catalog),
    context: JSON.parse(JSON.stringify(input.context)) as BusinessOperationContext & JsonObject,
    batch: resourceIds.length > 1,
  }
  return deepFreeze(cloneJson(snapshot))
}

function canonicalize(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonicalize(value[key] as JsonValue)]),
    )
  }
  return value
}

export function canonicalOperationRequestJson(snapshot: BusinessOperationRequestSnapshot): string {
  return JSON.stringify(canonicalize(snapshot))
}

export async function canonicalOperationRequestHash(snapshot: BusinessOperationRequestSnapshot): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalOperationRequestJson(snapshot))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('')
}

export function operationApiRequest(snapshot: BusinessOperationRequestSnapshot): OperationTaskCreate | BatchOperationCreate {
  if (snapshot.batch) {
    return {
      operationKey: snapshot.operationKey,
      featureId: snapshot.featureId,
      resourceIds: [...snapshot.resourceIds],
      parameters: cloneJson(snapshot.parameters),
      context: cloneJson(snapshot.context),
    }
  }
  return {
    operationKey: snapshot.operationKey,
    featureId: snapshot.featureId,
    resourceId: snapshot.resourceIds[0]!,
    parameters: cloneJson(snapshot.parameters),
    context: cloneJson(snapshot.context),
  }
}
