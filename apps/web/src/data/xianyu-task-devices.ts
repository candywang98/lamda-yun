import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'

export type XianyuApp = 'main'
export type XianyuSchedule = '立即执行'

export interface XianyuTaskDevice {
  id: string
  name: string
  account: string
  online: boolean
}

export function deviceLabel(device: XianyuTaskDevice, showAccount = false): string {
  if (!showAccount) return device.name
  const account = device.account.trim()
  return `${device.name}(${account || '未初始化'})`
}

export function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]
}

export function invertSelection(current: string[], allIds: string[]): string[] {
  return current.length === allIds.length ? [] : [...allIds]
}

export function persistJson(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    return { ...fallback, ...(JSON.parse(raw) as Partial<T>) }
  } catch {
    return fallback
  }
}

export async function fetchXianyuTaskDevices(): Promise<XianyuTaskDevice[]> {
  if (!controlApiConfigured) return []
  try {
    const api = createControlApiClient()
    return (await api.devices()).map((item) => {
      const mapped = mapControlDevice(item)
      const account = mapped.account && mapped.account !== '通过账号 API 查看' ? mapped.account : ''
      return { id: mapped.id, name: mapped.name, account, online: mapped.presence === 'ONLINE' }
    })
  } catch {
    return []
  }
}

export function recordTask(key: string, payload: unknown) {
  const task = { id: crypto.randomUUID(), createdAt: new Date().toISOString(), payload }
  try {
    const current = JSON.parse(localStorage.getItem(key) ?? '[]') as unknown[]
    const next = Array.isArray(current) ? [task, ...current].slice(0, 50) : [task]
    persistJson(key, next)
  } catch {
    persistJson(key, [task])
  }
}
