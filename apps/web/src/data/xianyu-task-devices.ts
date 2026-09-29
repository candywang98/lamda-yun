import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { mapControlDevice } from '@/api/devices'

export type XianyuApp = 'main'
export type XianyuSchedule = '立即执行'

export interface XianyuTaskDevice {
  id: string
  name: string
  account: string
  accountId: string | null
  accountError?: string
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

export async function fetchXianyuTaskDevices(onError?: (message: string) => void): Promise<XianyuTaskDevice[]> {
  if (!controlApiConfigured) return []
  try {
    const api = createControlApiClient()
    const [deviceResult, accountResult] = await Promise.allSettled([api.devices(), api.accounts()])
    if (deviceResult.status !== 'fulfilled' || !Array.isArray(deviceResult.value)) {
      onError?.('Control API 设备列表读取失败')
      return []
    }
    const rawDevices = deviceResult.value
    const accountsAvailable = accountResult.status === 'fulfilled' && Array.isArray(accountResult.value)
    const rawAccounts = accountsAvailable ? accountResult.value : []
    if (!accountsAvailable) onError?.('账号列表读取失败；设备仍可查看，但不能创建队列')
    const accountByDevice = new Map<string, { id: string; label: string }[]>()
    for (const account of rawAccounts) {
      if (account === null || typeof account !== 'object' || Array.isArray(account)) continue
      const accountId = typeof account.id === 'string' ? account.id.trim() : ''
      const platform = typeof account.platform === 'string' ? account.platform.trim().toLowerCase() : ''
      if (!accountId || platform !== 'xianyu' || account.status !== 'AUTHORIZED' || account.revokedAt !== null) continue
      const label = typeof account.displayLabel === 'string' ? account.displayLabel : accountId
      const bindings = Array.isArray(account.bindings) ? account.bindings : []
      for (const binding of bindings) {
        if (binding === null || typeof binding !== 'object' || Array.isArray(binding)) continue
        const deviceId = typeof binding.deviceId === 'string' ? binding.deviceId.trim() : ''
        if (!deviceId || binding.status !== 'BOUND' || binding.accountId !== accountId
          || binding.platform !== 'xianyu' || binding.historical !== false || binding.unboundAt !== null) continue
        const list = accountByDevice.get(deviceId) ?? []
        if (!list.some((item) => item.id === accountId)) list.push({ id: accountId, label })
        accountByDevice.set(deviceId, list)
      }
    }
    return rawDevices.filter((item) => item !== null && typeof item === 'object'
      && typeof item.id === 'string' && !!item.id.trim()).map((item) => {
      const mapped = mapControlDevice(item)
      const accounts = accountByDevice.get(mapped.id) ?? []
      const account = accounts.length === 1 ? accounts[0]! : null
      return {
        id: mapped.id,
        name: mapped.name,
        account: account?.label ?? '',
        accountId: account?.id ?? null,
        accountError: account ? undefined : !accountsAvailable
          ? '账号列表读取失败；不能创建队列'
          : accounts.length > 1 ? '设备存在多个 BOUND 闲鱼账号；不能确定 accountId'
            : '设备没有唯一 BOUND 闲鱼账号 accountId',
        online: mapped.presence === 'ONLINE',
      }
    })
  } catch {
    onError?.('Control API 设备或账号数据读取失败')
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
