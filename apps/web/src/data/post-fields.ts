import type { JsonObject, JsonValue } from '@cloudctl/api-contracts'

export interface PostRecord {
  id: string
  title: string
  body: string
  images: string[]
  videoName: string
  videoUrl: string
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
    videoName: partial.videoName ?? '',
    videoUrl: partial.videoUrl ?? '',
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

export function payloadFromPost(post: PostRecord): JsonObject {
  return {
    kind: 'post',
    body: post.body,
    images: post.images,
    videoName: post.videoName,
    videoUrl: post.videoUrl,
    topics: post.topics,
    location: post.location,
    notes: post.notes,
    groupName: post.groupName,
    sourceLinks: post.sourceLinks,
  }
}

export function postFromPayload(id: string, title: string, payload: JsonObject, meta?: Partial<PostRecord>): PostRecord {
  return emptyPost({
    id,
    title,
    body: asString(payload.body),
    images: asStringList(payload.images),
    videoName: asString(payload.videoName),
    videoUrl: asString(payload.videoUrl),
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
