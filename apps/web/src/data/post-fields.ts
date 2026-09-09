import type { JsonObject, JsonValue } from '@cloudctl/api-contracts'

export interface PostRecord {
  id: string
  title: string
  body: string
  images: string[]
  imageAssetIds: string[]
  videoName: string
  videoUrl: string
  videoAssetId: string
  topics: string[]
  location: string
  notes: string
  groupName: string
  sourceLinks: string[]
  createdAt: string
  updatedAt: string
  status: string
}

export function emptyPost(partial: Partial<PostRecord> = {}): PostRecord {
  const now = new Date().toISOString()
  return {
    id: partial.id ?? crypto.randomUUID(),
    title: partial.title ?? '',
    body: partial.body ?? '',
    images: partial.images ?? [],
    imageAssetIds: partial.imageAssetIds ?? [],
    videoName: partial.videoName ?? '',
    videoUrl: partial.videoUrl ?? '',
    videoAssetId: partial.videoAssetId ?? '',
    topics: partial.topics ?? [],
    location: partial.location ?? '',
    notes: partial.notes ?? '',
    groupName: partial.groupName ?? '默认分组',
    sourceLinks: partial.sourceLinks ?? [],
    createdAt: partial.createdAt ?? now,
    updatedAt: partial.updatedAt ?? now,
    status: partial.status ?? 'ACTIVE',
  }
}

function asString(value: JsonValue | undefined, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asStringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function looksLikeAssetId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
    || (/^[0-9a-zA-Z._:-]{1,36}$/.test(value) && !value.includes('/'))
}

function mediaAssetIdsFromPost(post: PostRecord): string[] {
  return postImageIds(post).filter(looksLikeAssetId).slice(0, 20)
}

function contentImageIds(payload: JsonObject): string[] {
  const assetIds = asStringList(payload.mediaAssetIds)
  if (assetIds.length > 0) return assetIds
  const legacyAssetIds = asStringList(payload.imageAssetIds)
  if (legacyAssetIds.length > 0) return legacyAssetIds
  return asStringList(payload.images)
}

export function payloadFromPost(post: PostRecord): JsonObject {
  const body = post.body.trim() || post.title.trim() || '未命名帖子'
  return {
    kind: 'post',
    body,
    mediaAssetIds: mediaAssetIdsFromPost(post),
    targetApp: 'unspecified',
    draftState: post.status === 'REVIEW' ? '待复核' : '草稿',
  }
}

export function postFromPayload(id: string, title: string, payload: JsonObject, meta?: Partial<PostRecord>): PostRecord {
  return emptyPost({
    id,
    title,
    body: asString(payload.body),
    images: contentImageIds(payload),
    imageAssetIds: contentImageIds(payload),
    videoName: asString(payload.videoName),
    videoUrl: asString(payload.videoAssetId) || asString(payload.videoUrl),
    videoAssetId: asString(payload.videoAssetId) || asString(payload.videoUrl),
    topics: asStringList(payload.topics),
    location: asString(payload.location),
    notes: asString(payload.notes),
    groupName: asString(payload.groupName, '默认分组'),
    sourceLinks: asStringList(payload.sourceLinks),
    createdAt: meta?.createdAt,
    updatedAt: meta?.updatedAt,
    status: meta?.status ?? 'ACTIVE',
  })
}

export function postImageIds(post: Pick<PostRecord, 'images' | 'imageAssetIds'>): string[] {
  const assetIds = Array.isArray(post.imageAssetIds) ? post.imageAssetIds : []
  const images = Array.isArray(post.images) ? post.images : []
  return [...(assetIds.length > 0 ? assetIds : images)]
}

export function clipText(value: string, max = 18): string {
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

export function formatDateTime(value: string | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 19)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
