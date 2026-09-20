import type { RouteRecordRaw, Router } from 'vue-router'
import ContentIOView from './ContentIOView.vue'

export const contentIORoutes: RouteRecordRaw[] = [
  {
    path: '/content-io',
    name: 'content-io-workbench',
    component: ContentIOView,
    meta: { title: '内容导入导出', section: '运营目录' },
  },
]

export function registerContentIORoutes(router: Router): void {
  for (const route of contentIORoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
