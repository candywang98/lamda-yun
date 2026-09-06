import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { firstOperationPath, operationModules, operationPath, type OperationDefinition } from '@/data/operations-catalog'

export const useOperationsWorkspace = defineStore('operations-workspace', () => {
  const expandedModuleId = ref(operationModules[0]?.id ?? 'system-home')
  const tabs = ref<Array<{ id: string; title: string; to: string; moduleId: string }>>([])

  const modules = computed(() => operationModules)

  function toggleModule(moduleId: string) {
    expandedModuleId.value = expandedModuleId.value === moduleId ? '' : moduleId
  }

  function ensureExpanded(moduleId: string) {
    expandedModuleId.value = moduleId
  }

  function openTab(operation: OperationDefinition) {
    const to = operationPath(operation)
    const existing = tabs.value.find((tab) => tab.id === operation.id)
    if (existing) {
      ensureExpanded(operation.moduleId)
      return
    }
    const next = [...tabs.value, { id: operation.id, title: operation.title, to, moduleId: operation.moduleId }]
    tabs.value = next.length > 5 ? next.slice(next.length - 5) : next
    ensureExpanded(operation.moduleId)
  }

  function closeTab(id: string) {
    tabs.value = tabs.value.filter((tab) => tab.id !== id)
  }

  function firstPath(moduleId: string) {
    const module = operationModules.find((item) => item.id === moduleId)
    return module ? firstOperationPath(module) : '/operations'
  }

  return { expandedModuleId, tabs, modules, toggleModule, ensureExpanded, openTab, closeTab, firstPath }
})
