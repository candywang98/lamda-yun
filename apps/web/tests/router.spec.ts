import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { coreRoutes, operationRoutes } from '@/router'

describe('core route contract', () => {
  it('keeps legacy CloudCtl paths only as redirects into the operations workspace', () => {
    expect(coreRoutes).toHaveLength(20)
    expect(new Set(coreRoutes.map((route) => route.path)).size).toBe(20)
    expect(coreRoutes.find((route) => route.name === 'mobile-automation')?.redirect).toBe('/operations/system-home/system-home-02')
    expect(coreRoutes.find((route) => route.name === 'devices')?.redirect).toBe('/operations/system-home/system-home-02')
    expect(coreRoutes.find((route) => route.name === 'device-detail')?.component).toBeTruthy()
  })

  it('gives each page a visible title and navigation section', () => {
    for (const route of coreRoutes) {
      expect(route.meta?.title).toBeTruthy()
      expect(route.meta?.section).toBeTruthy()
    }
  })

  it('adds catalog and reusable dynamic operation routes without changing the core routes', () => {
    expect(operationRoutes).toHaveLength(3)
    expect(operationRoutes.map((route) => route.path)).toEqual(['/operations', '/operations/settings/display', '/operations/:moduleId/:operationId'])
  })

  it('redirects unknown operation identifiers to the catalog', async () => {
    const testRouter = createRouter({ history: createMemoryHistory(), routes: operationRoutes })
    await testRouter.push('/operations/not-a-module/not-an-operation')
    await testRouter.isReady()
    expect(testRouter.currentRoute.value.name).toBe('operations-catalog')
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
