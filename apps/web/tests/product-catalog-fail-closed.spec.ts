import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CloudCtlApiError } from '@cloudctl/api-contracts'

vi.mock('@/api/control', () => ({
  controlApiConfigured: true,
  createControlApiClient: () => ({
    products: vi.fn().mockRejectedValue(new CloudCtlApiError(404, {
      type: 'about:blank',
      title: 'Not Found',
      status: 404,
      code: 'NOT_FOUND',
      detail: 'missing',
      correlation_id: 'req-1',
      retryable: false,
      fields: {},
    })),
    createProduct: vi.fn().mockRejectedValue(new CloudCtlApiError(404, {
      type: 'about:blank',
      title: 'Not Found',
      status: 404,
      code: 'NOT_FOUND',
      detail: 'missing',
      correlation_id: 'req-1',
      retryable: false,
      fields: {},
    })),
    contents: vi.fn().mockRejectedValue(new CloudCtlApiError(501, {
      type: 'about:blank',
      title: 'Not Implemented',
      status: 501,
      code: 'NOT_IMPLEMENTED',
      detail: 'missing',
      correlation_id: 'req-2',
      retryable: false,
      fields: {},
    })),
  }),
}))

vi.mock('@/api/runtime-mode', () => ({
  localBusinessDataAllowed: () => false,
  requireApiMode: (action: string) => {
    throw new Error(`${action} 失败：未配置 VITE_CONTROL_API_URL，生产环境禁止写入 localStorage`)
  },
}))

import { createProductCatalog } from '@/api/product-catalog'
import { createPostCatalog } from '@/api/post-catalog'

describe('B004 production API fail-closed', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('does not write local products when a configured API returns 404', async () => {
    const catalog = createProductCatalog()
    await expect(catalog.list()).rejects.toBeInstanceOf(CloudCtlApiError)
    await expect(catalog.save({
      payload: {
        spuCode: 'SPU-1',
        title: '测试',
        category: '默认分组',
        price: '1',
        stock: 1,
      },
    })).rejects.toBeInstanceOf(CloudCtlApiError)
    expect(window.localStorage.getItem('cloudctl.local-products')).toBeNull()
  })

  it('does not write local posts when a configured API returns 501', async () => {
    const catalog = createPostCatalog()
    await expect(catalog.list()).rejects.toBeInstanceOf(CloudCtlApiError)
    expect(window.localStorage.getItem('cloudctl.local-posts')).toBeNull()
  })
})
