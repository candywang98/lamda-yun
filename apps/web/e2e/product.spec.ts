import { expect, test } from '@playwright/test'

const product = {
  id: 'product-e2e-001',
  spuCode: 'SPU-E2E-001',
  title: 'E2E 测试商品',
  description: '真实商品描述',
  category: '黄金回收',
  price: '1.1',
  stock: 2,
  status: 'ACTIVE',
  revision: 3,
  mediaAssetIds: [],
  media: [],
  attributes: {
    groupName: '黄金回收',
    images: [],
    notes: '',
  },
  createdAt: '2026-09-05T00:00:00Z',
}

test('商品列表展示真实列，编辑进入普通宝贝并保存', async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/products' && route.request().method() === 'GET') return route.fulfill({ json: [product] })
    if (url.pathname === `/api/v1/products/${product.id}` && route.request().method() === 'GET') return route.fulfill({ json: product })
    if (url.pathname === '/api/v1/products' && route.request().method() === 'POST') {
      return route.fulfill({ json: { ...product, id: 'product-e2e-new', revision: 1 } })
    }
    if (url.pathname === `/api/v1/products/${product.id}` && route.request().method() === 'PUT') {
      return route.fulfill({ json: { ...product, revision: 4, title: '南京黄金回收服务' } })
    }
    return route.fulfill({ json: {} })
  })

  await page.goto('/operations/product-management/product-management-01')
  await expect(page.getByText('竞品页面依据')).toHaveCount(0)
  await expect(page.getByText('E2E 测试商品')).toBeVisible()
  await expect(page.getByText('黄金回收').first()).toBeVisible()
  await page.getByTitle('编辑').click()
  await expect(page).toHaveURL(/product-editor-01\?id=product-e2e-001/)
  await expect(page.getByLabel('标题')).toHaveValue('E2E 测试商品')
  await page.getByLabel('标题').fill('南京黄金回收服务')
  await page.getByRole('button', { name: '保存编辑' }).first().click()
  await expect(page.getByText('已保存编辑')).toBeVisible()
})
