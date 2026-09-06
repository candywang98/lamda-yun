export type ListingApp = 'main' | 'sub' | 'main-then-sub'

export interface ListingCollectDevice {
  id: string
  name: string
  account: string
  online: boolean
}

export interface ListingCollectConfig {
  deviceIds: string[]
  app: ListingApp
  schedule: '立即执行'
}

export const LISTING_COLLECT_CONFIG_KEY = 'cloudctl.listing-info-collect.config'
export const LISTING_COLLECT_TASKS_KEY = 'cloudctl.listing-info-collect.tasks'

export function emptyListingCollectConfig(partial: Partial<ListingCollectConfig> = {}): ListingCollectConfig {
  return {
    deviceIds: [],
    app: 'main',
    schedule: '立即执行',
    ...partial,
  }
}

export function loadListingCollectConfig(): ListingCollectConfig {
  try {
    return emptyListingCollectConfig(JSON.parse(localStorage.getItem(LISTING_COLLECT_CONFIG_KEY) ?? '{}') as Partial<ListingCollectConfig>)
  } catch {
    return emptyListingCollectConfig()
  }
}

export function saveListingCollectConfig(config: ListingCollectConfig): ListingCollectConfig {
  const next = emptyListingCollectConfig(config)
  localStorage.setItem(LISTING_COLLECT_CONFIG_KEY, JSON.stringify(next))
  return next
}

export function deviceLabel(device: ListingCollectDevice): string {
  const account = device.account.trim()
  if (!account) return device.name
  return `${device.name}(${account})`
}

export function recordListingCollectTask(config: ListingCollectConfig): void {
  const task = {
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    ...config,
  }
  try {
    const current = JSON.parse(localStorage.getItem(LISTING_COLLECT_TASKS_KEY) ?? '[]') as unknown[]
    const next = Array.isArray(current) ? [task, ...current].slice(0, 50) : [task]
    localStorage.setItem(LISTING_COLLECT_TASKS_KEY, JSON.stringify(next))
  } catch {
    localStorage.setItem(LISTING_COLLECT_TASKS_KEY, JSON.stringify([task]))
  }
}
