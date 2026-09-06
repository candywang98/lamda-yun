import type { PostRecord } from '@/data/post-fields'

export const POST_GROUPS_STORAGE_KEY = 'cloudctl.local-post-groups'
export const DEFAULT_POST_GROUP_NAME = '默认分组'

export interface PostGroup {
  id: string
  name: string
  remark: string
  createdAt: string
  system?: boolean
}

export const DEFAULT_POST_GROUP: PostGroup = {
  id: '46625',
  name: DEFAULT_POST_GROUP_NAME,
  remark: '系统建立的分组',
  createdAt: '2026-01-12T22:24:46.000Z',
  system: true,
}

function loadStored(): PostGroup[] {
  try {
    const raw = localStorage.getItem(POST_GROUPS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as PostGroup[]
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item) => item && typeof item.id === 'string' && typeof item.name === 'string')
  } catch {
    return []
  }
}

function saveStored(groups: PostGroup[]) {
  localStorage.setItem(POST_GROUPS_STORAGE_KEY, JSON.stringify(groups))
}

function numericId(existing: Set<string>): string {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const id = String(10000 + Math.floor(Math.random() * 90000))
    if (!existing.has(id)) return id
  }
  return String(Date.now()).slice(-5)
}

export function postGroupName(post: PostRecord): string {
  return post.groupName.trim() || DEFAULT_POST_GROUP_NAME
}

export function sortPostGroups(groups: PostGroup[]): PostGroup[] {
  return [...groups].sort((left, right) => right.createdAt.localeCompare(left.createdAt) || right.id.localeCompare(left.id))
}

export function mergePostGroups(stored: PostGroup[], posts: PostRecord[]): PostGroup[] {
  const byName = new Map<string, PostGroup>()
  byName.set(DEFAULT_POST_GROUP_NAME, { ...DEFAULT_POST_GROUP })
  for (const group of stored) {
    const name = group.name.trim() || DEFAULT_POST_GROUP_NAME
    const current = byName.get(name)
    if (!current || (!current.system && group.system)) {
      byName.set(name, { ...group, name })
    }
  }
  const usedIds = new Set([...byName.values()].map((item) => item.id))
  for (const post of posts) {
    const name = postGroupName(post)
    if (byName.has(name)) continue
    const createdAt = post.createdAt || post.updatedAt || new Date().toISOString()
    const id = numericId(usedIds)
    usedIds.add(id)
    byName.set(name, {
      id,
      name,
      remark: name === DEFAULT_POST_GROUP_NAME ? DEFAULT_POST_GROUP.remark : '',
      createdAt,
    })
  }
  return sortPostGroups([...byName.values()])
}

export function resolvePostGroups(posts: PostRecord[] = []): PostGroup[] {
  return mergePostGroups(loadStored(), posts)
}

export function listPostGroups(posts: PostRecord[] = []): PostGroup[] {
  const groups = resolvePostGroups(posts)
  saveStored(groups)
  return groups
}

export function createPostGroup(input: { name: string; remark?: string }, posts: PostRecord[] = []): PostGroup {
  const name = input.name.trim()
  if (!name) throw new Error('请填写分组名')
  const groups = listPostGroups(posts)
  if (groups.some((item) => item.name === name)) throw new Error('分组名已存在')
  const created: PostGroup = {
    id: numericId(new Set(groups.map((item) => item.id))),
    name,
    remark: input.remark?.trim() ?? '',
    createdAt: new Date().toISOString(),
  }
  saveStored(sortPostGroups([created, ...groups]))
  return created
}

export function updatePostGroup(id: string, patch: { name?: string; remark?: string }, posts: PostRecord[] = []): PostGroup {
  const groups = listPostGroups(posts)
  const index = groups.findIndex((item) => item.id === id)
  if (index < 0) throw new Error('分组不存在')
  const current = groups[index]!
  const name = patch.name === undefined ? current.name : patch.name.trim()
  if (!name) throw new Error('请填写分组名')
  if (groups.some((item) => item.id !== id && item.name === name)) throw new Error('分组名已存在')
  const next: PostGroup = {
    ...current,
    name,
    remark: patch.remark === undefined ? current.remark : patch.remark.trim(),
  }
  groups[index] = next
  saveStored(sortPostGroups(groups))
  return next
}

export function deletePostGroup(id: string, posts: PostRecord[] = []): PostGroup[] {
  const groups = listPostGroups(posts)
  const current = groups.find((item) => item.id === id)
  if (!current) throw new Error('分组不存在')
  if (current.system || current.name === DEFAULT_POST_GROUP_NAME) throw new Error('系统分组不能删除')
  const next = groups.filter((item) => item.id !== id)
  saveStored(next)
  return next
}

export function postsUsingGroup(posts: PostRecord[], name: string): PostRecord[] {
  return posts.filter((item) => postGroupName(item) === name)
}

export function replacePostGroupName(post: PostRecord, from: string, to: string): PostRecord | null {
  if (postGroupName(post) !== from) return null
  return { ...post, groupName: to }
}
