import { expect, test, type Page, type Route, type TestInfo } from '@playwright/test'
import { rawFleetDeviceFixture, platformTaskFixture } from '../tests/fixtures/fleet-devices'

test.use({ screenshot: 'only-on-failure' })

const deviceId = 'qa-device'
const device = {
  ...rawFleetDeviceFixture({ deviceId, logicalName: 'QA Phone' }),
  id: deviceId, logical_name: 'QA Phone', state: 'REGISTERED',
}

async function mockApi(page: Page, handler: (route: Route, url: URL) => Promise<boolean>, roles = ['device_operator']) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (await handler(route, url)) return
    if (url.pathname === '/api/v1/session') {
      await route.fulfill({ json: { userId: 'qa-user', tenantId: 'qa-tenant', roles, mfa: true, requestId: 'qa' } })
    } else if (url.pathname === '/api/v1/devices') {
      await route.fulfill({ json: [device] })
    } else {
      await route.fulfill({ json: [] })
    }
  })
}

async function capture(page: Page, info: TestInfo, name: string) {
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true })
  const contentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(contentWidth).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
}

for (const role of ['device_operator', 'viewer']) {
  test(`direct orders visit loads ${role} permissions without visiting recipes`, async ({ page }, info) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await mockApi(page, async (route, url) => {
      if (url.pathname !== '/api/v1/orders') return false
      await route.fulfill({ json: { items: [], total: 0 } })
      return true
    }, [role])
    await page.goto('/orders')
    await expect(page.getByText('Control API 会话已验证')).toBeAttached()
    await page.getByRole('combobox', { name: '设备', exact: true }).selectOption(deviceId)
    const collect = page.getByRole('button', { name: '开始采集' })
    if (role === 'device_operator') await expect(collect).toBeEnabled()
    else await expect(collect).toBeDisabled()
    expect(errors).toEqual([])
    await capture(page, info, `orders-${role}`)
  })
}

for (const route of ['/orders', '/im']) {
  test(`${route} contains long device names and collected identifiers`, async ({ page }, info) => {
    const logicalName = 'QA warehouse device with an unusually long enrollment label 1234567890'
    await mockApi(page, async (request, url) => {
      if (url.pathname === '/api/v1/devices') {
        await request.fulfill({ json: [{ ...device, logicalName, logical_name: logicalName }] })
      } else if (url.pathname === '/api/v1/orders') {
        await request.fulfill({ json: { items: [{
          id: 'qa-long-order', deviceId, platform: 'xianyu', direction: 'SOLD',
          orderKey: `qa-${'collected-order-key-'.repeat(12)}`,
          itemTitle: 'QA long item title '.repeat(12), buyerName: 'QA buyer',
          amountCents: 10000, statusText: '待发货', occurredAt: '2026-09-28T00:00:00Z',
          createdAt: '2026-09-28T00:00:00Z', updatedAt: '2026-09-28T00:00:00Z',
        }], total: 1 } })
      } else if (url.pathname === '/api/v1/im/threads') {
        await request.fulfill({ json: { items: [], count: 0, bucketCounts: { all: 0, user: 0, notice: 0, review: 0 } } })
      } else if (url.pathname === '/api/v1/im/config') {
        await request.fulfill({ json: { deviceId, enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00', receiveOnly: true } })
      } else return false
      return true
    }, ['viewer'])
    await page.goto(route)
    await expect(page.getByRole('option', { name: route === '/im' ? logicalName : `${logicalName}（${deviceId.slice(0, 8)}）` }).first()).toBeAttached()
    if (route === '/orders') await expect(page.getByRole('cell', { name: 'QA buyer', exact: true })).toBeVisible()
    else {
      await expect(page.getByRole('button', { name: '设备监控设置' })).toHaveAttribute('aria-expanded', 'false')
      await expect(page.getByLabel('监听总开关')).not.toBeVisible()
      await page.getByRole('button', { name: '设备监控设置' }).click()
      await expect(page.getByLabel('监听总开关')).toBeChecked()
    }
    await capture(page, info, `${route.slice(1)}-long-content`)
  })
}

test('monitor config errors remain visible and can recover', async ({ page }, info) => {
  let configFailed = true
  await mockApi(page, async (route, url) => {
    if (url.pathname === '/api/v1/im/threads') {
      await route.fulfill({ json: { items: [], count: 0, bucketCounts: { all: 0, user: 0, notice: 0, review: 0 } } })
    } else if (url.pathname === '/api/v1/im/config') {
      await route.fulfill(configFailed
        ? { status: 503, json: { detail: 'QA config unavailable' } }
        : { json: { deviceId, enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00', receiveOnly: true } })
    } else return false
    return true
  })
  await page.goto('/im')
  await expect(page.getByRole('alert')).toContainText('QA config unavailable')
  await page.getByRole('button', { name: '设备监控设置' }).click()
  configFailed = false
  await page.getByRole('button', { name: '重试加载设置' }).click()
  await expect(page.getByLabel('监听总开关')).toBeChecked()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await capture(page, info, 'im-config')
})

test('older conversations remain accessible beyond the first fifty', async ({ page }, info) => {
  const threads = Array.from({ length: 51 }, (_, index) => ({
    id: `qa-thread-${index}`, deviceId, platform: 'xianyu', peerKey: `qa-peer-${index}`,
    peerName: `QA Buyer ${index}`, unreadCount: 0, lastDirection: 'IN',
    lastMessageText: `QA summary ${index}`, lastMessageAt: '2026-09-28T00:00:00Z',
  }))
  await mockApi(page, async (route, url) => {
    if (url.pathname === '/api/v1/im/threads') {
      const items = url.searchParams.has('after') ? threads.slice(50) : threads.slice(0, 50)
      await route.fulfill({ json: { items, count: items.length, bucketCounts: { all: 51, user: 51, notice: 0, review: 0 } } })
    } else if (url.pathname === '/api/v1/im/config') {
      await route.fulfill({ json: { deviceId, enabled: true, platforms: ['xianyu'], mode: 'NOTIFICATION', dutyStart: '09:00', dutyEnd: '23:00', receiveOnly: true } })
    } else if (url.pathname.endsWith('/messages')) {
      await route.fulfill({ json: { items: [{
        id: 'qa-message', threadId: 'qa-thread-50', direction: 'IN', contentType: 'TEXT',
        text: 'Older conversation body', occurredAt: '2026-09-28T00:00:00Z', replyTaskId: null,
      }] } })
    } else return false
    return true
  }, ['viewer'])
  await page.goto('/im')
  await page.getByRole('button', { name: '加载更多会话' }).click()
  await page.locator('.im-thread').filter({ hasText: 'QA Buyer 50' }).click()
  await expect(page.getByText('Older conversation body', { exact: true })).toBeVisible()
  await expect(page.locator('.im-thread')).toHaveCount(51)
  await expect(page.getByRole('button', { name: '发送回复' })).toHaveCount(0)
  await capture(page, info, 'im-older-conversation')
})

test('fleet detail survives a failed refresh and can be retried', async ({ page }, info) => {
  let devicesFailed = false
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await mockApi(page, async (route, url) => {
    if (url.pathname === '/api/v1/devices') {
      await route.fulfill(devicesFailed ? { status: 503, json: { detail: 'QA offline' } } : { json: [device] })
    } else if (url.pathname === '/api/v1/platform-tasks') {
      await route.fulfill({ json: { items: [platformTaskFixture({ deviceId })] } })
    } else return false
    return true
  })
  await page.goto('/fleet')
  await page.locator('.fleet-card input[type=checkbox]').check()
  await page.getByRole('button', { name: /展开为逐设备目标/ }).click()
  await page.getByRole('button', { name: '查看', exact: true }).click()
  await expect(page.locator('.fleet-detail')).toBeVisible()
  devicesFailed = true
  await page.getByRole('button', { name: '刷新设备状态' }).click()
  await expect(page.getByTestId('fleet-load-error')).toContainText('QA offline')
  await expect(page.locator('.fleet-detail')).toHaveCount(0)
  expect(errors).toEqual([])
  devicesFailed = false
  await page.getByRole('button', { name: '刷新设备状态' }).click()
  await expect(page.locator('.fleet-card')).toHaveCount(1)
  await capture(page, info, 'fleet-recovered')
})

test('product filtering returns to the first page and rejected changes leave values intact', async ({ page }, info) => {
  const products = Array.from({ length: 12 }, (_, index) => ({
    id: `qa-product-${index}`, spuCode: `QA-${index}`, title: `QA Product ${index}`,
    description: 'QA description', category: 'QA group', price: '100', stock: 1,
    status: 'ACTIVE', revision: 1, mediaAssetIds: [], media: [], attributes: {},
    createdAt: '2026-09-28T00:00:00Z',
  }))
  await mockApi(page, async (route, url) => {
    if (url.pathname === '/api/v1/products') await route.fulfill({ json: products })
    else if (url.pathname.startsWith('/api/v1/products/') && route.request().method() === 'PUT') {
      await route.fulfill({ status: 409, json: { detail: 'QA revision conflict' } })
    } else return false
    return true
  }, ['content_editor'])
  await page.goto('/operations/product-management/product-management-01')
  await expect(page.getByText('QA Product 0', { exact: true })).toBeVisible()
  await capture(page, info, 'products-before-pagination')
  await page.locator('.pager').getByRole('button', { name: '2', exact: true }).click()
  await expect(page.getByText('QA Product 11', { exact: true })).toBeVisible()
  await page.getByPlaceholder('搜索ID、标题或内容').fill('QA Product 2')
  await expect(page.getByText('QA Product 2', { exact: true })).toBeVisible()
  await page.locator('thead input[type=checkbox]').check()
  await page.getByRole('button', { name: '改价', exact: true }).click()
  await page.getByPlaceholder('输入新价格').fill('200')
  await page.locator('.mask').getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText(/批量操作失败/)).toBeVisible()
  await page.locator('.mask').getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('tbody tr').getByText('100', { exact: true })).toBeVisible()
  await capture(page, info, 'products-rejected-update')
})
