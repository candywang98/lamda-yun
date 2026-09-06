import {
  persistJson,
  readJson,
  recordTask,
  type XianyuApp,
  type XianyuSchedule,
} from './xianyu-task-devices'

export type XianyuSimpleKind = 'polish' | 'shelf-up' | 'shelf-down' | 'delete-goods' | 'bind'

export interface XianyuSimpleConfig {
  deviceIds: string[]
  app: XianyuApp
  intervalSeconds: number
  schedule: XianyuSchedule
  exposure: number
  views: number
  wants: number
  keyword: string
  target: string
  memberName: string
}

export const XY_SIMPLE_CONFIG_KEY = 'cloudctl.xianyu-simple-task.config'
export const XY_SIMPLE_TASKS_KEY = 'cloudctl.xianyu-simple-task.tasks'

export function emptySimpleConfig(partial: Partial<XianyuSimpleConfig> = {}): XianyuSimpleConfig {
  return {
    deviceIds: [],
    app: 'main',
    intervalSeconds: 5,
    schedule: '立即执行',
    exposure: 10,
    views: 0,
    wants: 0,
    keyword: '',
    target: '全部宝贝',
    memberName: '',
    ...partial,
  }
}

export function defaultInterval(kind: XianyuSimpleKind): number {
  if (kind === 'polish') return 5
  return 1
}

export function loadSimpleConfig(kind: XianyuSimpleKind): XianyuSimpleConfig {
  const all = readJson<Record<string, Partial<XianyuSimpleConfig>>>(XY_SIMPLE_CONFIG_KEY, {})
  return emptySimpleConfig({ intervalSeconds: defaultInterval(kind), ...all[kind] })
}

export function saveSimpleConfig(kind: XianyuSimpleKind, config: XianyuSimpleConfig): XianyuSimpleConfig {
  const next = emptySimpleConfig(config)
  const all = readJson<Record<string, XianyuSimpleConfig>>(XY_SIMPLE_CONFIG_KEY, {})
  persistJson(XY_SIMPLE_CONFIG_KEY, { ...all, [kind]: next })
  return next
}

export function recordSimpleTask(kind: XianyuSimpleKind, config: XianyuSimpleConfig) {
  recordTask(XY_SIMPLE_TASKS_KEY, { kind, ...config })
}
