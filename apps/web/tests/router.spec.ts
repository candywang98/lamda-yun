import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { coreRoutes, operationRoutes } from '@/router'

describe('core route contract', () => {
  it('keeps legacy CloudCtl paths only as redirects into the operations workspace', () => {
    expect(coreRoutes).toHaveLength(23)
    expect(new Set(coreRoutes.map((route) => route.path)).size).toBe(23)
    expect(coreRoutes.find((route) => route.name === 'im-inbox')?.component).toBeTruthy()
    expect(coreRoutes.find((route) => route.name === 'orders')?.redirect).toBe('/operations/orders/orders-01')
    expect(coreRoutes.find((route) => route.name === 'mobile-automation')?.redirect).toBe('/operations/system-home/system-home-02')
    expect(coreRoutes.find((route) => route.name === 'devices')?.redirect).toBe('/operations/system-home/system-home-02')
    expect(coreRoutes.find((route) => route.name === 'device-detail')?.component).toBeTruthy()
  })

  it('exposes Recipe version management as a working page', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: coreRoutes })
    await testRouter.push('/recipes')
    expect(testRouter.currentRoute.value.name).toBe('recipe-versions')
    expect(coreRoutes.find((route) => route.name === 'recipe-versions')?.component).toBeTruthy()
  })

  it('redirects the legacy orders URL to the canonical sync task', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: [...coreRoutes, ...operationRoutes] })
    await testRouter.push('/orders')
    await testRouter.isReady()
    expect(testRouter.currentRoute.value.fullPath).toBe('/operations/orders/orders-01')
    expect(coreRoutes.find((route) => route.name === 'orders')?.redirect).toBe('/operations/orders/orders-01')
  })

  it('gives each page a visible title and navigation section', () => {
    for (const route of coreRoutes) {
      expect(route.meta?.title).toBeTruthy()
      expect(route.meta?.section).toBeTruthy()
    }
  })

  it('adds catalog and reusable dynamic operation routes without changing the core routes', () => {
    expect(operationRoutes).toHaveLength(6)
    expect(operationRoutes.map((route) => route.path)).toEqual(['/operations/system-home/system-home-01', '/operations/system-home/system-home-06', '/operations/orders/orders-04', '/operations', '/operations/settings/display', '/operations/:moduleId/:operationId'])
  })

  it('redirects all-orders from both initial load and an existing dynamic operation route', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: operationRoutes })
    await testRouter.push('/operations/orders/orders-04')
    expect(testRouter.currentRoute.value.fullPath).toBe('/operations/product-management/product-management-01?tab=orders')
    await testRouter.push('/operations/orders/orders-01')
    await testRouter.push('/operations/orders/orders-04')
    expect(testRouter.currentRoute.value.params.moduleId).toBe('product-management')
    expect(testRouter.currentRoute.value.query.tab).toBe('orders')
  })

  it('redirects unknown operation identifiers to the catalog', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: operationRoutes })
    await testRouter.push('/operations/not-a-module/not-an-operation')
    await testRouter.isReady()
    expect(testRouter.currentRoute.value.name).toBe('operations-catalog')
    expect(testRouter.currentRoute.value.fullPath).toBe('/operations')
  })

  it.each(['system-home-01', 'system-home-06'])('redirects removed %s on initial and dynamic navigation', async (id) => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: operationRoutes })
    await testRouter.push('/operations/system-home/' + id)
    expect(testRouter.currentRoute.value.fullPath).toBe('/operations')
    await testRouter.push('/operations/system-home/system-home-02')
    await testRouter.push('/operations/system-home/' + id)
    expect(testRouter.currentRoute.value.fullPath).toBe('/operations')
  })

  it('keeps valid operation identifiers on the detail route', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: operationRoutes })
    await testRouter.push('/operations/product-editor/product-editor-03')
    await testRouter.isReady()
    expect(testRouter.currentRoute.value.name).toBe('operation-detail')
  })

  it('sends the old mobile-automation URL to the operations device list', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: [...coreRoutes, ...operationRoutes] })
    await testRouter.push('/mobile-automation')
    await testRouter.isReady()
    expect(testRouter.currentRoute.value.fullPath).toBe('/operations/system-home/system-home-02')
  })
})
