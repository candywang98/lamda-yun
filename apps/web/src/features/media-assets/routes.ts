import type { RouteRecordRaw, Router } from 'vue-router'
import MediaAssetsWorkbenchView from './MediaAssetsWorkbenchView.vue'

export const mediaAssetsRoutes: RouteRecordRaw[] = [
  {
    path: '/media-assets',
    name: 'media-assets-workbench',
    component: MediaAssetsWorkbenchView,
    meta: { title: '媒体资产工作台', section: '运营目录' },
  },
]

export function registerMediaAssetsRoutes(router: Router): void {
  for (const route of mediaAssetsRoutes) {
    const name = route.name
    if (typeof name === 'string' && router.hasRoute(name)) continue
    router.addRoute(route)
  }
}
