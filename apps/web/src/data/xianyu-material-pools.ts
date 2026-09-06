import { persistJson, readJson } from './xianyu-task-devices'

export interface DeviceAddressRow {
  deviceId: string
  groupNo: string
  note: string
  addresses: string[]
}

export interface DescriptionItem {
  id: string
  text: string
}

export const DEVICE_ADDRESS_KEY = 'cloudctl.xianyu-device-address-pool'
export const DESCRIPTION_POOL_KEY = 'cloudctl.xianyu-description-pool'
export const TAG_POOL_KEY = 'cloudctl.xianyu-tag-pool'

export const DESCRIPTION_POOL_COUNT = 6
export const TAG_POOL_COUNT = 6
export const MAX_DEVICE_ADDRESSES = 50
export const MAX_TAGS_PER_POOL = 10

export function loadDeviceAddressMap(): Record<string, DeviceAddressRow> {
  return readJson<Record<string, DeviceAddressRow>>(DEVICE_ADDRESS_KEY, {})
}

export function saveDeviceAddressMap(map: Record<string, DeviceAddressRow>) {
  persistJson(DEVICE_ADDRESS_KEY, map)
}

export function emptyDescriptionPools(): DescriptionItem[][] {
  return Array.from({ length: DESCRIPTION_POOL_COUNT }, () => [])
}

export function loadDescriptionPools(): DescriptionItem[][] {
  const raw = readJson<DescriptionItem[][]>(DESCRIPTION_POOL_KEY, emptyDescriptionPools())
  return emptyDescriptionPools().map((_, index) => Array.isArray(raw[index]) ? raw[index]! : [])
}

export function saveDescriptionPools(pools: DescriptionItem[][]) {
  persistJson(DESCRIPTION_POOL_KEY, pools)
}

export function emptyTagPools(): string[][] {
  return [
    ['黄金首饰', '黄金回收', '黄金项链', '黄金戒指', '周大福'],
    [],
    [],
    [],
    [],
    [],
  ]
}

export function loadTagPools(): string[][] {
  const raw = readJson<string[][]>(TAG_POOL_KEY, emptyTagPools())
  return emptyTagPools().map((fallback, index) => Array.isArray(raw[index]) ? raw[index]! : fallback)
}

export function saveTagPools(pools: string[][]) {
  persistJson(TAG_POOL_KEY, pools)
}

export const FORBIDDEN_WORDS: Array<{ word: string; level: '高危' | '风险'; reason: string }> = [
  { word: '微信', level: '高危', reason: '引流联系方式' },
  { word: '加微', level: '高危', reason: '引流联系方式' },
  { word: 'QQ', level: '高危', reason: '引流联系方式' },
  { word: '站外交易', level: '高危', reason: '站外交易' },
  { word: '刀具', level: '高危', reason: '管制刀具' },
  { word: '毒品', level: '高危', reason: '毒品' },
  { word: '国家级', level: '风险', reason: '虚假主张' },
  { word: '最高级', level: '风险', reason: '虚假主张' },
  { word: '全网最低', level: '风险', reason: '虚假主张' },
  { word: '销量第一', level: '风险', reason: '虚假主张' },
  { word: '国家免检', level: '风险', reason: '虚假主张' },
  { word: '治疗', level: '风险', reason: '疾病治疗宣称' },
  { word: '高仿', level: '风险', reason: '高仿假货' },
  { word: '中奖', level: '风险', reason: '诱导中奖' },
]

export interface ForbiddenHit {
  word: string
  level: '高危' | '风险'
  reason: string
}

export function detectForbiddenWords(text: string): ForbiddenHit[] {
  const source = text.trim()
  if (!source) return []
  return FORBIDDEN_WORDS.filter((item) => source.includes(item.word))
}

export function downloadCsv(filename: string, rows: string[][]) {
  const csv = rows.map((line) => line.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(',')).join('\n')
  const link = document.createElement('a')
  link.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`
  link.download = filename
  link.click()
}
