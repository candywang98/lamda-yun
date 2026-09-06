import { persistJson, readJson, recordTask, type XianyuSchedule } from './xianyu-task-devices'

export type BrowseType = 'discover' | 'follow' | 'local'
export type ChannelType = '推荐' | '视频' | '直播' | '附近'
export type MultiOpen = 'off' | 'clone'

export const CHANNEL_OPTIONS: ChannelType[] = ['推荐', '视频', '直播', '附近']

export const DEFAULT_COMMENT_POOL = '好喜欢你的分享，干货满满！#太赞了，学到了很多新知识！#你的推荐真的超级实用，感谢！#每次看你的帖子都有新收获！#分享得很详细，棒棒哒！#照片拍得好美，文案也很用心！#这也太好看了吧，马上种草！#好实用的技巧，立马收藏！#你的风格我超喜欢，期待更多分享！#每次看你的帖子都觉得很有启发！'

export interface XiaohongshuNurtureConfig {
  deviceIds: string[]
  browseType: BrowseType
  channel: ChannelType
  multiOpen: MultiOpen
  flipCount: number
  clickRate: number
  likeRate: number
  collectRate: number
  commentRate: number
  comments: string
  schedule: XianyuSchedule
}

export const XHS_NURTURE_CONFIG_KEY = 'cloudctl.xiaohongshu-nurture.config'
export const XHS_NURTURE_TASKS_KEY = 'cloudctl.xiaohongshu-nurture.tasks'

export function emptyNurtureConfig(partial: Partial<XiaohongshuNurtureConfig> = {}): XiaohongshuNurtureConfig {
  return {
    deviceIds: [],
    browseType: 'discover',
    channel: '推荐',
    multiOpen: 'off',
    flipCount: 20,
    clickRate: 30,
    likeRate: 30,
    collectRate: 30,
    commentRate: 0,
    comments: DEFAULT_COMMENT_POOL,
    schedule: '立即执行',
    ...partial,
  }
}

function clampRate(value: number): number {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric < 0) return 0
  return Math.min(100, Math.round(numeric))
}

export function loadNurtureConfig(): XiaohongshuNurtureConfig {
  return emptyNurtureConfig(readJson<Partial<XiaohongshuNurtureConfig>>(XHS_NURTURE_CONFIG_KEY, {}))
}

export function saveNurtureConfig(config: XiaohongshuNurtureConfig): XiaohongshuNurtureConfig {
  const next = emptyNurtureConfig({
    ...config,
    flipCount: Math.max(1, Number(config.flipCount) || 1),
    clickRate: clampRate(config.clickRate),
    likeRate: clampRate(config.likeRate),
    collectRate: clampRate(config.collectRate),
    commentRate: clampRate(config.commentRate),
    comments: config.comments.trim() || DEFAULT_COMMENT_POOL,
  })
  persistJson(XHS_NURTURE_CONFIG_KEY, next)
  return next
}

export function recordNurtureTask(config: XiaohongshuNurtureConfig) {
  recordTask(XHS_NURTURE_TASKS_KEY, saveNurtureConfig(config))
}

export function commentCandidates(comments: string): string[] {
  return comments.split('#').map((item) => item.trim()).filter(Boolean)
}
