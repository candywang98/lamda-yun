import type { RouteRecordRaw, Router } from 'vue-router'
import LiveFleetPanelView from './LiveFleetPanelView.vue'

/**
 * L12 分级投屏面板路由。接线方式与 features/fleet、features/reconciliation 相同：
 * 在 router.ts 里 `routes: [...fleetRoutes, ...reconciliationRoutes, ...liveFleetRoutes]`，
 * 或运行时调用 registerLiveFleetRoutes(router)。本文件不修改根路由。
 */
export const liveFleetRoutes: RouteRecordRaw[] = [
  {
    path: '/live',
    name: 'live-fleet-panel',
    component: LiveFleetPanelView,
    meta: { title: '投屏预览 / 远控', section: '舰队' },
  },
]

export function registerLiveFleetRoutes(router: Router): void {
  for (const route of liveFleetRoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
