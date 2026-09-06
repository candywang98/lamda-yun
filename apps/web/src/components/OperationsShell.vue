<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BookHeart,
  ChevronDown,
  Clock3,
  FilePenLine,
  FileText,
  Home,
  Image,
  Layers,
  Lightbulb,
  Menu,
  MessageCircle,
  MonitorSmartphone,
  Package,
  Play,
  RefreshCw,
  Repeat2,
  Settings2,
  ShoppingBag,
  Sparkles,
  UserRound,
  X,
} from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'
import { useOperationsWorkspace } from '@/stores/operations-workspace'
import { useDisplaySettings } from '@/stores/display-settings'
import { findOperation, firstOperationPath, operationModules, operationPath } from '@/data/operations-catalog'
import { controlApiConfigured } from '@/api/control'
import type { Component } from 'vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const workspace = useOperationsWorkspace()
const display = useDisplaySettings()

const moduleIcons: Record<string, Component> = {
  'system-home': Home,
  'task-queue': Play,
  'product-editor': FilePenLine,
  collection: Layers,
  'product-management': Package,
  'post-management': FileText,
  orders: ShoppingBag,
  analytics: Clock3,
  'xy-tasks': Sparkles,
  'zz-tasks': Repeat2,
  'red-tasks': BookHeart,
  creative: Lightbulb,
  chat: MessageCircle,
  assets: Image,
  profile: UserRound,
}

const visibleModules = computed(() => display.visibleModules())
const currentOperation = computed(() => findOperation(String(route.params.moduleId ?? ''), String(route.params.operationId ?? '')))
const catalogOpen = computed(() => route.name === 'operations-catalog')
const settingsOpen = computed(() => route.name === 'operations-display-settings')
const remoteOpen = computed(() => route.name === 'device-detail')
const pageTitle = computed(() => {
  if (currentOperation.value) return currentOperation.value.title
  if (settingsOpen.value) return '显示设置'
  if (remoteOpen.value) return '设备详情 / 远控'
  return '运营功能目录'
})

function isExpanded(moduleId: string) {
  return workspace.expandedModuleId === moduleId || route.params.moduleId === moduleId
}

function openModule(moduleId: string) {
  workspace.toggleModule(moduleId)
  if (route.params.moduleId !== moduleId) {
    const module = visibleModules.value.find((item) => item.id === moduleId) ?? operationModules.find((item) => item.id === moduleId)
    if (module?.operations[0]) void router.push(firstOperationPath(module))
  }
}

function closeTab(id: string) {
  const remaining = workspace.tabs.filter((tab) => tab.id !== id)
  workspace.closeTab(id)
  if (currentOperation.value?.id === id) {
    const fallback = remaining.at(-1)
    void router.push(fallback?.to ?? '/operations')
  }
}

watch(currentOperation, (operation) => {
  if (operation) workspace.openTab(operation)
}, { immediate: true })
</script>

<template>
  <div class="yy-shell">
    <aside class="yy-sidebar" :class="{ open: session.sidebarOpen }" aria-label="运营导航">
      <div class="yy-brand">
        <span class="yy-brand-mark"><MonitorSmartphone :size="18" /></span>
        <strong>云控工作台</strong>
      </div>
      <nav class="nav-scroll yy-nav">
        <RouterLink to="/operations" class="yy-catalog-link" :class="{ active: catalogOpen }" @click="session.sidebarOpen = false">全部功能</RouterLink>
        <RouterLink to="/operations/settings/display" class="yy-catalog-link" :class="{ active: settingsOpen }" @click="session.sidebarOpen = false"><Settings2 :size="14" />显示设置</RouterLink>
        <section v-for="module in visibleModules" :key="module.id" class="yy-module-block">
          <button
            class="nav-link operation-module-nav yy-module"
            :class="{ 'module-active': route.params.moduleId === module.id, open: isExpanded(module.id) }"
            @click="openModule(module.id)"
          >
            <component :is="moduleIcons[module.id] ?? Home" :size="15" />
            <span>{{ module.label }}</span>
            <small>{{ module.operations.length }}</small>
            <ChevronDown :size="13" />
          </button>
          <div v-show="isExpanded(module.id)" class="yy-subnav">
            <RouterLink
              v-for="operation in module.operations"
              :key="operation.id"
              :to="operationPath(operation)"
              class="yy-sub-link"
              :class="{ active: operation.id === currentOperation?.id }"
              @click="session.sidebarOpen = false"
            >
              {{ operation.title }}
            </RouterLink>
          </div>
        </section>
      </nav>
      <div class="yy-sidebar-foot">
        <span class="dot" :class="controlApiConfigured ? 'dot-good' : 'dot-warn'" />
        {{ controlApiConfigured ? 'Control API 已连接' : '本地模式 · 未接真机' }}
      </div>
    </aside>

    <div v-if="session.sidebarOpen" class="sidebar-backdrop" @click="session.sidebarOpen = false" />

    <main class="yy-main">
      <header class="yy-topbar">
        <button class="icon-button mobile-menu" title="打开导航" @click="session.sidebarOpen = true"><Menu :size="18" /></button>
        <button class="yy-tool" type="button" title="刷新" @click="router.go(0)"><RefreshCw :size="15" />刷新</button>
        <RouterLink class="yy-tool" to="/operations/task-queue/task-queue-01"><Play :size="15" /></RouterLink>
        <div v-if="display.visible('topNotice')" class="yy-notice">功能配置如有疑问，请到对应教程查看。执行走授权设备与 Control API，不连接竞品服务。</div>
        <span class="filter-spacer" />
      </header>

      <div class="yy-tabs" aria-label="已打开页面">
        <RouterLink to="/operations" class="yy-tab" :class="{ active: catalogOpen }">全部功能</RouterLink>
        <RouterLink to="/operations/settings/display" class="yy-tab" :class="{ active: settingsOpen }">显示设置</RouterLink>
        <RouterLink v-if="remoteOpen" :to="route.fullPath" class="yy-tab active">设备详情 / 远控</RouterLink>
        <div v-for="tab in workspace.tabs" :key="tab.id" class="yy-tab" :class="{ active: tab.id === currentOperation?.id }">
          <RouterLink :to="tab.to">{{ tab.title }}</RouterLink>
          <button type="button" :aria-label="`关闭 ${tab.title}`" @click="closeTab(tab.id)"><X :size="11" /></button>
        </div>
      </div>

      <div class="yy-content">
        <p class="sr-only">{{ pageTitle }}</p>
        <RouterView />
      </div>
    </main>
  </div>
</template>
