import type { RouteRecordRaw, Router } from 'vue-router'
import OrdersHistoryView from './OrdersHistoryView.vue'

/**
 * O10 订单历史切片路由。接线方式与 features/fleet、features/reconciliation
 * 相同：router.ts 里展开 ordersHistoryRoutes，或运行时调用
 * registerOrdersHistoryRoutes(router)。本文件不修改根路由。
 */
export const ordersHistoryRoutes: RouteRecordRaw[] = [
  {
    path: '/orders/history',
    name: 'orders-history',
    component: OrdersHistoryView,
    meta: { title: '订单历史切片', section: '运营目录' },
  },
]

export function registerOrdersHistoryRoutes(router: Router): void {
  for (const route of ordersHistoryRoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
