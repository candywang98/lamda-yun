export const displaySettingItems = [
  { id: 'topNotice', label: '顶栏黄色提示条', detail: '「功能配置如有疑问…」那一行' },
  { id: 'contextStrip', label: '页面路径条', detail: '运营目录 / 模块 / LIVE API 那一行' },
  { id: 'policyBanner', label: '执行策略提示', detail: '蓝色条：可模拟、未配置 API、无执行适配器' },
  { id: 'apiErrorBanner', label: 'Control API 错误提示', detail: '红色条：请求未完成、不允许回退 Mock' },
  { id: 'runResultBanner', label: '任务回执提示', detail: '提交成功后的 Mock / 后端任务状态条' },
  { id: 'sourcePanel', label: '竞品页面依据', detail: 'PDF 页码、原始路由和工作流程' },
  { id: 'auditPanel', label: '后端审计', detail: '任务提交后的不可变事件列表' },
] as const

export type DisplaySettingId = (typeof displaySettingItems)[number]['id']
export type DisplaySettings = Record<DisplaySettingId, boolean>

export const defaultDisplaySettings: DisplaySettings = {
  topNotice: true,
  contextStrip: false,
  policyBanner: false,
  apiErrorBanner: true,
  runResultBanner: true,
  sourcePanel: false,
  auditPanel: false,
}

export const displaySettingsStorageKey = 'cloudctl:operation-display-settings'
export const navigationVisibilityStorageKey = 'cloudctl:operation-navigation-visibility'

export interface NavigationVisibility {
  hiddenModules: string[]
  hiddenOperations: string[]
}

export const defaultNavigationVisibility: NavigationVisibility = {
  hiddenModules: [],
  hiddenOperations: [],
}

export function parseDisplaySettings(raw: string | null): DisplaySettings {
  if (!raw) return { ...defaultDisplaySettings }
  try {
    const parsed = JSON.parse(raw) as Partial<DisplaySettings>
    return {
      ...defaultDisplaySettings,
      ...Object.fromEntries(
        displaySettingItems
          .filter((item) => typeof parsed[item.id] === 'boolean')
          .map((item) => [item.id, Boolean(parsed[item.id])]),
      ),
    }
  } catch {
    return { ...defaultDisplaySettings }
  }
}

export function parseNavigationVisibility(raw: string | null): NavigationVisibility {
  if (!raw) return { hiddenModules: [], hiddenOperations: [] }
  try {
    const parsed = JSON.parse(raw) as Partial<NavigationVisibility>
    return {
      hiddenModules: Array.isArray(parsed.hiddenModules) ? parsed.hiddenModules.filter((item) => typeof item === 'string') : [],
      hiddenOperations: Array.isArray(parsed.hiddenOperations) ? parsed.hiddenOperations.filter((item) => typeof item === 'string') : [],
    }
  } catch {
    return { hiddenModules: [], hiddenOperations: [] }
  }
}
