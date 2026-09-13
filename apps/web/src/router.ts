import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DeviceDetailView from '@/views/DeviceDetailView.vue'
import OperationsCatalogView from '@/views/OperationsCatalogView.vue'
import OperationsView from '@/views/OperationsView.vue'
import DisplaySettingsView from '@/views/DisplaySettingsView.vue'
import SourceConnectionsView from '@/views/SourceConnectionsView.vue'
import ImInboxView from './views/ImInboxView.vue'
import RecipeVersionsView from '@/views/RecipeVersionsView.vue'
import { findOperation } from '@/data/operations-catalog'

const deviceList = '/operations/system-home/system-home-02'
const taskQueue = '/operations/task-queue/task-queue-01'
const catalog = '/operations'

export const coreRoutes: RouteRecordRaw[] = [
  { path: '/im', name: 'im-inbox', component: ImInboxView, meta: { title: '消息聚合', section: '运营目录' } },
  { path: '/recipes', name: 'recipe-versions', component: RecipeVersionsView, meta: { title: 'Recipe 版本管理', section: '版本管理' } },
  { path: '/', name: 'dashboard', redirect: catalog, meta: { title: '运营功能目录', section: '运营目录' } },
  { path: '/devices', name: 'devices', redirect: deviceList, meta: { title: '设备列表', section: '运营目录' } },
  { path: '/devices/:id', name: 'device-detail', component: DeviceDetailView, meta: { title: '设备详情 / 远控', section: '运营目录' } },
  { path: '/accounts', name: 'accounts', redirect: '/operations/system-home/system-home-03', meta: { title: '系统授权', section: '运营目录' } },
  { path: '/works', name: 'works', redirect: '/operations/product-management/product-management-01', meta: { title: '商品列表', section: '运营目录' } },
  { path: '/works/:id/edit', name: 'work-editor', redirect: (to) => `/operations/product-editor/product-editor-01?id=${String(to.params.id)}`, meta: { title: '普通宝贝', section: '运营目录' } },
  { path: '/groups', name: 'groups', redirect: '/operations/product-management/product-management-03', meta: { title: '商品分组', section: '运营目录' } },
  { path: '/media', name: 'media', redirect: '/operations/assets/assets-02', meta: { title: '图片素材', section: '运营目录' } },
  { path: '/watermarks', name: 'watermarks', redirect: '/operations/assets/assets-01', meta: { title: '图片水印', section: '运营目录' } },
  { path: '/publishes/new', name: 'publish-create', redirect: '/operations/xy-tasks/xy-tasks-01', meta: { title: '发布商品', section: '运营目录' } },
  { path: '/publishes/:id', name: 'publish-detail', redirect: '/operations/xy-tasks/xy-tasks-01', meta: { title: '发布商品', section: '运营目录' } },
  { path: '/tasks', name: 'tasks', redirect: taskQueue, meta: { title: '任务队列', section: '运营目录' } },
  { path: '/tasks/:id', name: 'task-detail', redirect: taskQueue, meta: { title: '任务队列', section: '运营目录' } },
  { path: '/automation', name: 'automation', redirect: taskQueue, meta: { title: '任务队列', section: '运营目录' } },
  { path: '/studio', name: 'studio', redirect: catalog, meta: { title: '运营功能目录', section: '运营目录' } },
  { path: '/mobile-automation', name: 'mobile-automation', redirect: deviceList, meta: { title: '设备列表', section: '运营目录' } },
  { path: '/apks', name: 'apks', redirect: catalog, meta: { title: '运营功能目录', section: '运营目录' } },
  { path: '/apks/rollouts', name: 'apk-rollouts', redirect: catalog, meta: { title: '运营功能目录', section: '运营目录' } },
  { path: '/system', name: 'system', redirect: '/operations/settings/display', meta: { title: '显示设置', section: '运营目录' } },
  { path: '/sources', name: 'sources', component: SourceConnectionsView, meta: { title: '数据源连接', section: '数据源' } },
]

export const operationRoutes: RouteRecordRaw[] = [
  { path: '/operations', name: 'operations-catalog', component: OperationsCatalogView, meta: { title: '运营功能目录', section: '运营目录' } },
  { path: '/operations/settings/display', name: 'operations-display-settings', component: DisplaySettingsView, meta: { title: '显示设置', section: '运营目录' } },
  {
    path: '/operations/:moduleId/:operationId',
    name: 'operation-detail',
    component: OperationsView,
    meta: { title: '运营功能', section: '运营目录' },
    beforeEnter: (to) => {
      const moduleId = typeof to.params.moduleId === 'string' ? to.params.moduleId : ''
      const operationId = typeof to.params.operationId === 'string' ? to.params.operationId : ''
      return findOperation(moduleId, operationId) ? true : { name: 'operations-catalog', replace: true }
    },
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [...coreRoutes, ...operationRoutes],
  scrollBehavior: () => ({ top: 0 }),
})
