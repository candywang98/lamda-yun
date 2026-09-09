import { persistJson, readJson, recordTask, type XianyuApp, type XianyuSchedule } from './xianyu-task-devices'

export type XianyuExtraKind =
  | 'register'
  | 'dikou'
  | 'promote'
  | 'xiaodao'
  | 'price-cut'
  | 'review'
  | 'restart'
  | 'delete-feed'
  | 'delete-message'
  | 'delete-comment'
  | 'draft-up'
  | 'reedit'
  | 'wuyoumai'
  | 'fast-reedit'
  | 'fast-down'

export const ADDRESS_POOL_OPTIONS = ['关闭', '地址池一', '地址池二', '地址池三', '地址池四', '地址池五', '地址池六'] as const
export const WUYOUMAI_TYPES = ['全部托管', '全部退出', '打开页面，不操作'] as const

export const XIAODAO_OPTIONS = ['开启小刀', '关闭小刀', '固定数值', '打开页面，不操作'] as const
export const DIKOU_TYPES = ['不抵扣', '10%', '20%', '30%', '打开页面，不操作'] as const
export const PROMOTE_PACKAGES = ['特惠套餐50-75人', '高级套餐100-150人', '超级套餐300-450人'] as const

export const DEFAULT_REVIEW_BODY = '一位非常棒的买家#交易非常顺利#希望能再次遇到像您这样的好买家！#感谢您的信任和购买#期待再次与您交易#交易过程十分顺畅#是一次非常愉快的交易体验，期待未来有更多合作机会！#非常感谢您的支持，我们会继续提供更好的商品和服务！#沟通顺畅，交易愉快#非常感谢您的信任，交易愉快#交易非常愉快，期待再次合作#感谢您的购买，您的满意是我们不断前进的动力#非常棒的买家#非常感谢您的支持，希望商品能让您满意！#非常感谢您的信任和支持，我们会继续努力做得更好！#您的满意是我们工作的最大动力，期待您的再次购买'

export interface XianyuExtraConfig {
  deviceIds: string[]
  app: XianyuApp
  schedule: XianyuSchedule
  jumpTask: 'on' | 'off'
  dikouType: (typeof DIKOU_TYPES)[number]
  dikouTarget: '未开启抵扣宝贝' | '已开启抵扣宝贝'
  intervalSeconds: number
  promoteItem: '曝光最高宝贝' | '浏览最高宝贝' | '想要最高宝贝'
  promotePackage: (typeof PROMOTE_PACKAGES)[number]
  xiaodaoType: string
  percentCut: string
  amountCut: string
  target: string
  privateMessage: string
  reviewBody: string
  reviewTarget: '我卖出的' | '我买到的'
  messageAction: '删除对话框' | '点开小红点'
  quantity: number
  rounds: number
  addressPool: (typeof ADDRESS_POOL_OPTIONS)[number]
  autoShortTitle: 'on' | 'off'
  wuyoumaiType: (typeof WUYOUMAI_TYPES)[number]
}

export const XY_EXTRA_CONFIG_KEY = 'cloudctl.xianyu-extra-task.config'
export const XY_EXTRA_TASKS_KEY = 'cloudctl.xianyu-extra-task.tasks'

export function defaultInterval(kind: XianyuExtraKind): number {
  if (kind === 'dikou' || kind === 'price-cut' || kind === 'fast-reedit') return 5
  if (kind === 'review') return 6
  if (kind === 'reedit') return 120
  return 1
}

export function emptyExtraConfig(kind: XianyuExtraKind, partial: Partial<XianyuExtraConfig> = {}): XianyuExtraConfig {
  return {
    deviceIds: [],
    schedule: '立即执行',
    jumpTask: 'on',
    dikouType: '30%',
    dikouTarget: '未开启抵扣宝贝',
    intervalSeconds: defaultInterval(kind),
    promoteItem: '浏览最高宝贝',
    promotePackage: '特惠套餐50-75人',
    xiaodaoType: '',
    percentCut: '',
    amountCut: '0.1',
    target: '全部宝贝',
    privateMessage: '可以互相好评一下吗~',
    reviewBody: DEFAULT_REVIEW_BODY,
    reviewTarget: '我卖出的',
    messageAction: '删除对话框',
    quantity: 60,
    rounds: 1,
    addressPool: '关闭',
    autoShortTitle: 'off',
    wuyoumaiType: '全部托管',
    ...partial,
    app: 'main' as const,
  }
}

export function loadExtraConfig(kind: XianyuExtraKind): XianyuExtraConfig {
  const all = readJson<Record<string, Partial<XianyuExtraConfig>>>(XY_EXTRA_CONFIG_KEY, {})
  return emptyExtraConfig(kind, all[kind])
}

export function saveExtraConfig(kind: XianyuExtraKind, config: XianyuExtraConfig): XianyuExtraConfig {
  const next = emptyExtraConfig(kind, config)
  const all = readJson<Record<string, XianyuExtraConfig>>(XY_EXTRA_CONFIG_KEY, {})
  persistJson(XY_EXTRA_CONFIG_KEY, { ...all, [kind]: next })
  return next
}

export function recordExtraTask(kind: XianyuExtraKind, config: XianyuExtraConfig) {
  recordTask(XY_EXTRA_TASKS_KEY, { kind, ...config })
}

export const extraKindByOperationId: Record<string, XianyuExtraKind> = {
  'xy-tasks-09': 'register',
  'xy-tasks-10': 'dikou',
  'xy-tasks-11': 'promote',
  'xy-tasks-12': 'xiaodao',
  'xy-tasks-13': 'price-cut',
  'xy-tasks-14': 'review',
  'xy-tasks-15': 'restart',
  'xy-tasks-16': 'delete-feed',
  'xy-tasks-17': 'delete-message',
  'xy-tasks-18': 'delete-comment',
  'xy-tasks-19': 'draft-up',
  'xy-tasks-20': 'reedit',
  'xy-tasks-21': 'wuyoumai',
  'xy-tasks-22': 'fast-reedit',
  'xy-tasks-23': 'fast-down',
}
