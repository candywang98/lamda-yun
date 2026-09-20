import { controlApiBaseUrl, controlApiConfigured, controlApiHeaders } from '@/api/control'

export type ImportRowStatus = 'IMPORT' | 'SKIP_EXISTING' | 'ERROR'

export interface ImportRowError {
  field: string
  code: string
  message: string
}

export interface ContentImportItemInput {
  spuCode: string
  title: string
  description?: string
  category: string
  price: string
  stock: number
  imageUrls?: string[]
  groupId?: string
}

export interface ContentImportResultRow {
  index: number
  spuCode: string
  title: string
  status: ImportRowStatus
  errors: ImportRowError[]
  productId?: string
}

export interface ContentImportSummary {
  total: number
  importCount: number
  skipExistingCount: number
  errorCount: number
}

export interface ContentImportResult {
  mode: 'DRY_RUN' | 'APPLY'
  apply: boolean
  replayed: boolean
  importKey: string
  groupId: string | null
  rows: ContentImportResultRow[]
  summary: ContentImportSummary
  policy: string
}

export interface RevisionEntry {
  eventId: string
  revision: number | null
  action: string
  actorType: string
  actorId: string
  requestId: string
  result: string
  afterHash: string | null
  occurredAt: string | null
  snapshot: Record<string, unknown>
}

export interface RevisionHistory {
  productId: string
  currentRevision: number
  total: number
  limit: number
  offset: number
  items: RevisionEntry[]
}

export class ContentIOApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

function problemDetail(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null
  return typeof Reflect.get(value, 'detail') === 'string'
    ? String(Reflect.get(value, 'detail'))
    : null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!controlApiConfigured) {
    throw new ContentIOApiError(0, '未配置 Control API，内容导入导出不可用')
  }
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', init?.body ? 'application/json' : '*/*')
  if (init?.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${controlApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  })
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!response.ok) {
    throw new ContentIOApiError(
      response.status,
      `${problemDetail(payload) ?? '内容导入导出请求失败'}（HTTP ${response.status}）`,
    )
  }
  return payload as T
}

export function runContentImport(
  items: ContentImportItemInput[],
  options: { apply?: boolean; importKey?: string; groupId?: string } = {},
): Promise<ContentImportResult> {
  return request<ContentImportResult>('/api/v1/content-io/products:import', {
    method: 'POST',
    body: JSON.stringify({
      items,
      apply: options.apply ?? false,
      ...(options.importKey ? { importKey: options.importKey } : {}),
      ...(options.groupId ? { groupId: options.groupId } : {}),
    }),
  })
}

export function fetchProductRevisions(
  productId: string,
  limit: number,
  offset: number,
): Promise<RevisionHistory> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request<RevisionHistory>(
    `/api/v1/content-io/products/${encodeURIComponent(productId)}/revisions?${params}`,
  )
}

export async function downloadProductCsv(
  statusFilter?: 'ACTIVE' | 'ARCHIVED',
): Promise<{ fileName: string; rowCount: number }> {
  if (!controlApiConfigured) {
    throw new ContentIOApiError(0, '未配置 Control API，导出不可用')
  }
  const params = statusFilter ? `?status=${statusFilter}` : ''
  const headers = new Headers(controlApiHeaders())
  headers.set('Accept', 'text/csv')
  const response = await fetch(
    `${controlApiBaseUrl()}/api/v1/content-io/products:export${params}`,
    { headers, credentials: 'same-origin' },
  )
  if (!response.ok) {
    throw new ContentIOApiError(response.status, `导出失败（HTTP ${response.status}）`)
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="([^"]+)"/)
  const csv = await response.text()
  const rowCount = Math.max(0, csv.trimEnd().split('\n').length - 1)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = match?.[1] ?? 'products.csv'
  anchor.click()
  URL.revokeObjectURL(url)
  return { fileName: anchor.download, rowCount }
}
