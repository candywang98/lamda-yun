import type { RouteRecordRaw, Router } from 'vue-router'
import FleetWorkbenchView from './FleetWorkbenchView.vue'

/**
 * C10 设备工作台路由。根 router 接线留给控制器：在 router.ts 里
 * `routes: [...coreRoutes, ...operationRoutes, ...fleetRoutes]`，
 * 或运行时调用 registerFleetRoutes(router)。本文件不修改根路由（owned_paths 约束）。
 */
export const fleetRoutes: RouteRecordRaw[] = [
  {
    path: '/fleet',
    name: 'fleet-workbench',
    component: FleetWorkbenchView,
    meta: { title: '设备工作台', section: '舰队' },
  },
]

export function registerFleetRoutes(router: Router): void {
  for (const route of fleetRoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
