import type { RouteRecordRaw, Router } from 'vue-router'
import ReconciliationWorkbenchView from './ReconciliationWorkbenchView.vue'

/**
 * C11 对账与人工介入工作台路由。接线方式与 features/fleet 相同：
 * 在 router.ts 里 `routes: [...coreRoutes, ...operationRoutes, ...fleetRoutes, ...reconciliationRoutes]`，
 * 或运行时调用 registerReconciliationRoutes(router)。本文件不修改根路由。
 */
export const reconciliationRoutes: RouteRecordRaw[] = [
  {
    path: '/reconciliation',
    name: 'reconciliation-workbench',
    component: ReconciliationWorkbenchView,
    meta: { title: '对账工作台', section: '舰队' },
  },
]

export function registerReconciliationRoutes(router: Router): void {
  for (const route of reconciliationRoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
