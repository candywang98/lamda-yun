export type PostPublishPlatform = 'xianyu' | 'xiaohongshu'
export type PostPublishAllocation = 'default' | 'even'
export type PostPublishFormMode = 'direct' | 'draft'

export interface PostPublishDevice {
  id: string
  name: string
  online: boolean
}

export interface PostPublishConfig {
  deviceIds: string[]
  postIds: string[]
  allocation: PostPublishAllocation
  app: 'main'
  multiOpen: boolean
  autoVideo: boolean
  watermark: boolean
  intervalSeconds: number
  formMode: PostPublishFormMode
  schedule: '立即执行'
}

export interface PostPublishAssignment {
  deviceId: string
  postId: string
}

export function emptyPublishConfig(partial: Partial<PostPublishConfig> = {}): PostPublishConfig {
  return {
    deviceIds: [],
    postIds: [],
    allocation: 'default',
    autoVideo: false,
    watermark: false,
    intervalSeconds: 1,
    formMode: 'direct',
    schedule: '立即执行',
    ...partial,
    app: 'main' as const,
    multiOpen: false,
  }
}

export function configStorageKey(platform: PostPublishPlatform): string {
  return `cloudctl.post-publish.${platform}`
}

export function loadPublishConfig(platform: PostPublishPlatform): PostPublishConfig {
  try {
    return emptyPublishConfig(JSON.parse(localStorage.getItem(configStorageKey(platform)) ?? '{}') as Partial<PostPublishConfig>)
  } catch {
    return emptyPublishConfig()
  }
}

export function savePublishConfig(platform: PostPublishPlatform, config: PostPublishConfig): PostPublishConfig {
  const next = emptyPublishConfig({
    ...config,
    intervalSeconds: Math.max(1, Number(config.intervalSeconds) || 1),
  })
  localStorage.setItem(configStorageKey(platform), JSON.stringify(next))
  return next
}

export function allocatePosts(postIds: string[], deviceIds: string[], allocation: PostPublishAllocation): PostPublishAssignment[] {
  if (postIds.length === 0 || deviceIds.length === 0) return []
  if (allocation === 'default') {
    return deviceIds.flatMap((deviceId) => postIds.map((postId) => ({ deviceId, postId })))
  }
  const base = Math.floor(postIds.length / deviceIds.length)
  const extra = postIds.length % deviceIds.length
  const counts = deviceIds.map((_, index) => base + (index < extra ? 1 : 0))
  const assignments: PostPublishAssignment[] = []
  let cursor = 0
  deviceIds.forEach((deviceId, index) => {
    for (let offset = 0; offset < counts[index]!; offset += 1) {
      assignments.push({ deviceId, postId: postIds[cursor]! })
      cursor += 1
    }
  })
  return assignments
}

export function platformCopy(platform: PostPublishPlatform) {
  if (platform === 'xianyu') {
    return {
      title: '发布某鱼帖子',
      itemLabel: '帖子',
      itemUnit: '条',
      destination: '闲鱼',
      pickerPlaceholder: '点击选择帖子',
      groupPlaceholder: '帖子分组',
      tableGroup: '帖子分组',
      tableMedia: '帖子图片/视频',
      helpLead: '此功能可将系统中的帖子发布到闲鱼',
    }
  }
  return {
    title: '发布红薯笔记',
    itemLabel: '笔记',
    itemUnit: '篇',
    destination: '红薯',
    pickerPlaceholder: '点击选择笔记',
    groupPlaceholder: '笔记分组',
    tableGroup: '笔记分组',
    tableMedia: '笔记图片/视频',
    helpLead: '此功能可将系统中的笔记发布到红薯',
  }
}
