import type { RouteRecordRaw, Router } from 'vue-router'
import OperationFormWorkbenchView from './OperationFormWorkbenchView.vue'

export const operationFormRoutes: RouteRecordRaw[] = [
  {
    path: '/business-operations',
    name: 'business-operations',
    component: OperationFormWorkbenchView,
    meta: { title: '业务操作表单', section: '运营目录' },
  },
]

export function registerOperationFormRoutes(router: Router): void {
  for (const route of operationFormRoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
