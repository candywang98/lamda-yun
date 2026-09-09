import {
  persistJson,
  readJson,
  recordTask,
  type XianyuApp,
  type XianyuSchedule,
} from './xianyu-task-devices'

export type PublishAllocation = 'default' | 'even'
export type OnOff = 'on' | 'off'
export type InspectMode = 'none' | 'on' | 'off'
export type PublishFormMode = 'direct' | 'draft'
export type AddressMode = 'default' | 'device' | 'random' | 'multi'

export const VIDEO_MUSIC_OPTIONS = [
  '随机音乐',
  '欢快-Spring+In+My+Step',
  '舒缓-Ukulele+Beach',
  '动感-About+That+Oldie',
  '舒缓-Every+Step',
  '轻松-Tracks+Of+My+Fears',
  '浪漫-Wigs',
  '动感-Bonanza',
  '动感-Out+for+Blood',
] as const

export const FAN_DISCOUNT_OPTIONS = ['不优惠', '优惠1%', '优惠3%', '优惠5%', '优惠10%'] as const

export interface XianyuPublishGoodsConfig {
  deviceIds: string[]
  productIds: string[]
  allocation: PublishAllocation
  app: 'main'
  smartVideo: OnOff
  music: (typeof VIDEO_MUSIC_OPTIONS)[number]
  circle: string
  fanDiscount: (typeof FAN_DISCOUNT_OPTIONS)[number]
  intervalSeconds: number
  multiSpec: OnOff
  autoShortTitle: OnOff
  aiPolish: OnOff
  stripEmoji: OnOff
  inspect: InspectMode
  imageLabels: OnOff
  watermark: OnOff
  creativeCopy: OnOff
  formMode: PublishFormMode
  clearCache: OnOff
  insertImage: string
  descPool: string
  randomCover: OnOff
  randomTitle: OnOff
  addressMode: AddressMode
  addressPool: string
  schedule: XianyuSchedule
}

export const XY_PUBLISH_GOODS_CONFIG_KEY = 'cloudctl.xianyu-publish-goods.config'
export const XY_PUBLISH_GOODS_TASKS_KEY = 'cloudctl.xianyu-publish-goods.tasks'

export function emptyPublishGoodsConfig(partial: Partial<XianyuPublishGoodsConfig> = {}): XianyuPublishGoodsConfig {
  return {
    deviceIds: [],
    productIds: [],
    allocation: 'even',
    smartVideo: 'off',
    music: '随机音乐',
    circle: '',
    fanDiscount: '优惠1%',
    intervalSeconds: 1,
    multiSpec: 'on',
    autoShortTitle: 'off',
    aiPolish: 'off',
    stripEmoji: 'on',
    inspect: 'none',
    imageLabels: 'on',
    watermark: 'off',
    creativeCopy: 'off',
    formMode: 'direct',
    clearCache: 'on',
    insertImage: '',
    descPool: '',
    randomCover: 'off',
    randomTitle: 'off',
    addressMode: 'default',
    addressPool: '',
    schedule: '立即执行',
    ...partial,
    app: 'main' as const,
  }
}

export function loadPublishGoodsConfig(): XianyuPublishGoodsConfig {
  return emptyPublishGoodsConfig(readJson(XY_PUBLISH_GOODS_CONFIG_KEY, {}))
}

export function savePublishGoodsConfig(config: XianyuPublishGoodsConfig): XianyuPublishGoodsConfig {
  const next = emptyPublishGoodsConfig(config)
  persistJson(XY_PUBLISH_GOODS_CONFIG_KEY, next)
  return next
}

export function recordPublishGoodsTask(config: XianyuPublishGoodsConfig) {
  recordTask(XY_PUBLISH_GOODS_TASKS_KEY, config)
}

export function allocateProducts(productIds: string[], deviceIds: string[], allocation: PublishAllocation): Array<{ deviceId: string; productId: string }> {
  if (productIds.length === 0 || deviceIds.length === 0) return []
  if (allocation === 'default') {
    return deviceIds.flatMap((deviceId) => productIds.map((productId) => ({ deviceId, productId })))
  }
  return productIds.map((productId, index) => ({
    deviceId: deviceIds[index % deviceIds.length]!,
    productId,
  }))
}
