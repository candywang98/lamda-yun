import { CloudCtlApiError, type MediaAssetView } from '@cloudctl/api-contracts'
import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders, createControlApiClient } from '@/api/control'
import { requireApiMode } from '@/api/runtime-mode'

const previewCache = new Map<string, string>()

function looksLikeAssetId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

export async function fetchMediaBlob(assetId: string): Promise<Blob> {
  requireApiMode('读取媒体')
  const response = await fetch(`${controlApiBaseUrl()}/api/v1/media/assets/${encodeURIComponent(assetId)}/content`, {
    headers: controlApiHeaders(),
  })
  if (!response.ok) {
    throw new CloudCtlApiError(response.status, {
      type: 'urn:cloudctl:problem:media_download',
      title: 'Media download failed',
      status: response.status,
      code: 'MEDIA_DOWNLOAD_FAILED',
      detail: `读取媒体失败：${response.status}`,
      correlation_id: '',
      retryable: false,
      fields: {},
    })
  }
  return response.blob()
}

export async function resolveMediaPreviewUrl(value: string): Promise<string> {
  const source = value.trim()
  if (!source) return ''
  if (!looksLikeAssetId(source)) return source
  const cached = previewCache.get(source)
  if (cached) return cached
  const url = URL.createObjectURL(await fetchMediaBlob(source))
  previewCache.set(source, url)
  return url
}

function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  return hex(await crypto.subtle.digest('SHA-256', data))
}

export async function uploadMediaFile(file: File, metadata: Record<string, string> = {}): Promise<MediaAssetView> {
  requireApiMode('上传媒体')
  if (!controlApiConfigured) {
    throw new Error('未配置 Control API，无法创建 MediaAsset')
  }
  const api = createControlApiClient()
  const buffer = await file.arrayBuffer()
  const digest = await sha256Hex(buffer)
  const grant = await api.initiateMediaUpload({
    fileName: file.name.replace(/[\\/]/g, '_').replace(/[!]{1,}/g, '_'),
    sha256: digest,
    contentType: file.type || 'application/octet-stream',
    sizeBytes: file.size,
    metadata,
  })
  if ('asset' in grant && grant.state === 'COMPLETED') {
    return (grant as unknown as { asset: MediaAssetView }).asset
  }
  const apiBase = controlApiBaseUrl()
  let uploadUrl = grant.uploadUrl
  if (!/^https?:\/\//i.test(uploadUrl)) {
    uploadUrl = `${apiBase}${uploadUrl.startsWith('/') ? '' : '/'}${uploadUrl}`
  }
  const headers = new Headers(grant.uploadHeaders ?? {})
  const put = await fetch(uploadUrl, {
    method: 'PUT',
    headers,
    body: file,
  })
  if (!put.ok) {
    throw new CloudCtlApiError(put.status, {
      type: 'urn:cloudctl:problem:media_upload',
      title: 'Media upload failed',
      status: put.status,
      code: 'MEDIA_UPLOAD_FAILED',
      detail: `对象存储上传失败：${put.status}`,
      correlation_id: '',
      retryable: false,
      fields: {},
    })
  }
  return api.completeMediaUpload(grant.id)
}
