export type RuntimeDataMode = 'api' | 'mock' | 'unavailable'

const configuredUrl = (import.meta.env.VITE_CONTROL_API_URL?.trim() ?? '').replace(/\/$/, '')
const mockFlag = import.meta.env.VITE_OPERATIONS_MOCK_ENABLED === 'true'
const isDev = import.meta.env.DEV

export const controlApiConfigured = configuredUrl.length > 0

export function controlApiBaseUrl(): string {
  if (isDev && controlApiConfigured) return ''
  return configuredUrl
}
export const operationsMockEnabled = isDev && mockFlag && !controlApiConfigured
export const runtimeDataMode: RuntimeDataMode = controlApiConfigured
  ? 'api'
  : (isDev && mockFlag) || operationsMockEnabled
    ? 'mock'
    : 'unavailable'

export function localBusinessDataAllowed(): boolean {
  return runtimeDataMode === 'mock'
}

export function requireApiMode(action: string): void {
  if (runtimeDataMode === 'api') return
  if (runtimeDataMode === 'mock') return
  throw new Error(`${action} 失败：未配置 VITE_CONTROL_API_URL，生产环境禁止写入 localStorage`)
}

export function requireWritableApi(action: string): void {
  if (runtimeDataMode === 'api') return
  if (runtimeDataMode === 'mock') return
  throw new Error(`${action} 失败：未配置 VITE_CONTROL_API_URL，生产环境禁止写入 localStorage`)
}
