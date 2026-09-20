import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

export type CheckStatus = 'PASS' | 'WARNING' | 'BLOCKED'

export interface WatermarkRenderInput {
  text: string
  position: 'top_left' | 'top_right' | 'center' | 'bottom_left' | 'bottom_right'
  opacity: number
  fontSize: number
  margin: number
  ruleVersionId?: string
}

export interface MediaAssetSummary {
  id: string
  sha256: string
  objectKey: string
  contentType: string
  sizeBytes: number
  sourceAssetId: string | null
  metadata: Record<string, unknown>
}

export interface WatermarkRenderResult {
  derivativeId: string
  sourceAssetId: string
  outputAsset: MediaAssetSummary
  profile: WatermarkRenderInput
  profileSha256: string
  previewSha256: string
  publishDerivativeSha256: string
}

export interface MediaPoolFreezeInput {
  taskKey: string
  groupId: string
  count: number
  seed?: string
}

export interface MediaPoolFreezeResult {
  taskKey: string
  groupId: string
  seed: string
  count: number
  mediaAssetIds: string[]
  snapshotSha256: string
  replayed: boolean
}

export interface PublishPreflightInput {
  productId: string
  accountId: string
  deviceId: string
  platform: 'xianyu' | 'xiaohongshu'
}

export interface PreflightCheck {
  id: string
  category: 'fields' | 'content' | 'media' | 'account' | 'device'
  status: CheckStatus
  detail: string
}

export interface PublishPreflightResult {
  ready: boolean
  checks: PreflightCheck[]
  snapshot: {
    productId: string
    productRevision: number
    mediaAssetIds: string[]
    accountId: string
    bindingVersion: number | null
    deviceId: string
    platform: 'xianyu' | 'xiaohongshu'
  }
  snapshotSha256: string
}

export class MediaAssetsApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

function problemDetail(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null
  return typeof Reflect.get(value, 'detail') === 'string' ? String(Reflect.get(value, 'detail')) : null
}

async function post<T>(path: string, body: unknown): Promise<T> {
  if (!controlApiConfigured) {
    throw new MediaAssetsApiError(0, '未配置 Control API，媒体资产工作台不可用')
  }
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'application/json')
  headers.set('Content-Type', 'application/json')
  const response = await fetch(`${controlApiBaseUrl()}${path}`, {
    method: 'POST',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify(body),
  })
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!response.ok) {
    throw new MediaAssetsApiError(
      response.status,
      `${problemDetail(payload) ?? '媒体资产请求失败'}（HTTP ${response.status}）`,
    )
  }
  return payload as T
}

export function renderWatermark(
  sourceAssetId: string,
  input: WatermarkRenderInput,
): Promise<WatermarkRenderResult> {
  return post(
    `/api/v1/media-assets/${encodeURIComponent(sourceAssetId)}/watermark:render`,
    input,
  )
}

export function freezeMediaPool(input: MediaPoolFreezeInput): Promise<MediaPoolFreezeResult> {
  return post('/api/v1/media-assets/pools:freeze', input)
}

export function runPublishPreflight(input: PublishPreflightInput): Promise<PublishPreflightResult> {
  return post('/api/v1/media-assets/publish:preflight', input)
}
