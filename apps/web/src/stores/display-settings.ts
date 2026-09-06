import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  defaultDisplaySettings,
  displaySettingsStorageKey,
  navigationVisibilityStorageKey,
  parseDisplaySettings,
  parseNavigationVisibility,
  type DisplaySettingId,
  type DisplaySettings,
  type NavigationVisibility,
} from '@/data/display-settings'
import { isRetiredOperation, operationModules, type OperationModule } from '@/data/operations-catalog'

export const useDisplaySettings = defineStore('display-settings', () => {
  const settings = ref<DisplaySettings>(readSettings())
  const navigation = ref<NavigationVisibility>(readNavigation())

  function readSettings(): DisplaySettings {
    if (typeof window === 'undefined' || typeof window.localStorage?.getItem !== 'function') return { ...defaultDisplaySettings }
    return parseDisplaySettings(window.localStorage.getItem(displaySettingsStorageKey))
  }

  function readNavigation(): NavigationVisibility {
    if (typeof window === 'undefined' || typeof window.localStorage?.getItem !== 'function') return { hiddenModules: [], hiddenOperations: [] }
    return parseNavigationVisibility(window.localStorage.getItem(navigationVisibilityStorageKey))
  }

  function persistSettings() {
    if (typeof window === 'undefined' || typeof window.localStorage?.setItem !== 'function') return
    window.localStorage.setItem(displaySettingsStorageKey, JSON.stringify(settings.value))
  }

  function persistNavigation() {
    if (typeof window === 'undefined' || typeof window.localStorage?.setItem !== 'function') return
    window.localStorage.setItem(navigationVisibilityStorageKey, JSON.stringify(navigation.value))
  }

  function visible(id: DisplaySettingId) {
    return settings.value[id] !== false
  }

  function setVisible(id: DisplaySettingId, value: boolean) {
    settings.value = { ...settings.value, [id]: value }
    persistSettings()
  }

  function showAll() {
    settings.value = Object.fromEntries(Object.keys(defaultDisplaySettings).map((key) => [key, true])) as DisplaySettings
    persistSettings()
  }

  function hideAll() {
    settings.value = Object.fromEntries(Object.keys(defaultDisplaySettings).map((key) => [key, false])) as DisplaySettings
    persistSettings()
  }

  function moduleVisible(moduleId: string) {
    return !navigation.value.hiddenModules.includes(moduleId)
  }

  function operationVisible(operationId: string, moduleId?: string) {
    if (moduleId && !moduleVisible(moduleId)) return false
    return !navigation.value.hiddenOperations.includes(operationId)
  }

  function setModuleVisible(moduleId: string, value: boolean) {
    const hiddenModules = value
      ? navigation.value.hiddenModules.filter((id) => id !== moduleId)
      : [...new Set([...navigation.value.hiddenModules, moduleId])]
    const module = operationModules.find((item) => item.id === moduleId)
    const operationIds = module?.operations.map((item) => item.id) ?? []
    const hiddenOperations = value
      ? navigation.value.hiddenOperations.filter((id) => !operationIds.includes(id))
      : navigation.value.hiddenOperations
    navigation.value = { hiddenModules, hiddenOperations }
    persistNavigation()
  }

  function setOperationVisible(operationId: string, moduleId: string, value: boolean) {
    const hiddenOperations = value
      ? navigation.value.hiddenOperations.filter((id) => id !== operationId)
      : [...new Set([...navigation.value.hiddenOperations, operationId])]
    const hiddenModules = value
      ? navigation.value.hiddenModules.filter((id) => id !== moduleId)
      : navigation.value.hiddenModules
    navigation.value = { hiddenModules, hiddenOperations }
    persistNavigation()
  }

  function showAllModules() {
    navigation.value = { hiddenModules: [], hiddenOperations: [] }
    persistNavigation()
  }

  function visibleModules(): OperationModule[] {
    return operationModules
      .filter((module) => moduleVisible(module.id))
      .map((module) => ({
        ...module,
        operations: module.operations.filter((operation) => !isRetiredOperation(operation.id) && operationVisible(operation.id)),
      }))
      .filter((module) => module.operations.length > 0)
  }

  const visibleModuleCount = computed(() => visibleModules().length)
  const visibleOperationCount = computed(() => visibleModules().reduce((count, module) => count + module.operations.length, 0))

  return {
    settings,
    navigation,
    visible,
    setVisible,
    showAll,
    hideAll,
    moduleVisible,
    operationVisible,
    setModuleVisible,
    setOperationVisible,
    showAllModules,
    visibleModules,
    visibleModuleCount,
    visibleOperationCount,
  }
})
