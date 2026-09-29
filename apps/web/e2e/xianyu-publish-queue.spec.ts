import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { account, device, product, queueResponse } from '../tests/xianyu-publish-fixtures'
import type { XianyuPublishQueueRequest } from '../src/data/xianyu-publish-goods'

async function isolatedApi(page: Page, longLabels = false) {
  const deviceId = longLabels ? '11111111-1111-4111-8111-111111111111' : 'device-1'
  const accountId = longLabels ? '22222222-2222-4222-8222-222222222222' : 'account-1'
  const productId = longLabels ? '33333333-3333-4333-8333-333333333333' : 'product-1'
  const deviceRow = {
    ...device(deviceId),
    ...(longLabels ? { logical_name: `商品队列视觉验收设备-${'LongDeviceLabel'.repeat(8)}` } : {}),
  }
  const accountRow = {
    ...account(deviceId, accountId),
    ...(longLabels ? { displayLabel: `授权测试账号-${'LongAccountLabel'.repeat(6)}` } : {}),
  }
  const productRow = product({
    id: productId,
    ...(longLabels ? {
      title: `待发布商品长标题-${'LongProductLabel'.repeat(12)}`,
      description: `仅用于隔离界面验收的商品描述-${'中文描述与规格信息'.repeat(12)}`,
      category: `商品分组-${'LongCategoryLabel'.repeat(5)}`,
    } : {}),
  })
  const queueView = (body: XianyuPublishQueueRequest) => {
    const result = queueResponse(body)
    if (longLabels) result.targets[0]!.targetId = '44444444-4444-4444-8444-444444444444'
    return result
  }
  const state = {
    tenantId: 'tenant-1', sessionAvailable: true, lostResponse: !longLabels,
    roles: ['publisher'],
    deviceLabel: deviceRow.logical_name, productTitle: productRow.title,
    requests: [] as XianyuPublishQueueRequest[],
    logicalQueues: new Map<string, XianyuPublishQueueRequest>(),
    forbidden: [] as string[],
  }
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== 'http://127.0.0.1:4209') {
      state.forbidden.push(request.url())
      return route.abort()
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const method = request.method()
    if (method === 'GET' && url.pathname === '/api/v1/session') {
      return route.fulfill({
        status: state.sessionAvailable ? 200 : 401,
        json: state.sessionAvailable
          ? { tenantId: state.tenantId, userId: 'user-1', roles: state.roles, mfa: true, requestId: 'e2e' }
          : { detail: 'No authorized session' },
      })
    }
    if (method === 'GET' && url.pathname === '/api/v1/devices') return route.fulfill({ json: [deviceRow] })
    if (method === 'GET' && url.pathname === '/api/v1/accounts') return route.fulfill({ json: [{ ...accountRow, tenantId: state.tenantId }] })
    if (method === 'GET' && url.pathname === '/api/v1/products') return route.fulfill({ json: [productRow] })
    if (method === 'POST' && url.pathname === '/api/v1/xianyu/publish/queues') {
      const body = request.postDataJSON() as XianyuPublishQueueRequest
      state.requests.push(body)
      const key = `${state.tenantId}:${body.queueId}`
      const existing = state.logicalQueues.get(key)
      if (existing) expect(body).toEqual(existing)
      else state.logicalQueues.set(key, body)
      const persisted = await page.evaluate(() => Object.values(sessionStorage).join('\n'))
      expect(persisted).toContain(body.queueId)
      expect(persisted).toContain(body.items[0]!.deliveryId)
      expect(persisted).not.toContain('Catalog description')
      if (state.lostResponse) {
        state.lostResponse = false
        return route.abort('timedout')
      }
      return route.fulfill({ status: 201, json: { ...queueView(body), replayed: !!existing } })
    }
    if (method === 'GET' && /^\/api\/v1\/xianyu\/publish\/queues\/[^/]+$/.test(url.pathname)) {
      const body = state.logicalQueues.get(`${state.tenantId}:${url.pathname.split('/').at(-1)}`)
      if (body) return route.fulfill({ json: queueView(body) })
    }
    state.forbidden.push(`${method} ${url.pathname}`)
    return route.abort('blockedbyclient')
  })
  await page.addInitScript(({ deviceId, productId }) => {
    localStorage.setItem('cloudctl.xianyu-publish-goods.config', JSON.stringify({
      deviceIds: [deviceId], productIds: [productId],
    }))
  }, { deviceId, productId })
  return state
}

async function submit(page: Page) {
  const button = page.getByRole('button', { name: '创建或查询队列', exact: true }).first()
  await expect(button).toBeEnabled()
  await button.click()
}

test('viewer with valid API selections cannot create a queue', async ({ page }) => {
  const state = await isolatedApi(page)
  state.roles = ['viewer']
  await page.goto('/operations/xy-tasks/xy-tasks-01')
  await expect(page.locator('.selection .chip-name')).toContainText(state.deviceLabel)
  await expect(page.locator('.selection .picker')).toHaveText(state.productTitle)
  await expect(page.getByTestId('creation-block')).toContainText('task.create')
  const actions = page.getByRole('button', { name: '创建或查询队列', exact: true })
  await expect(actions).toHaveCount(2)
  await expect(actions.nth(0)).toBeDisabled()
  await expect(actions.nth(1)).toBeDisabled()
  await actions.first().dispatchEvent('click')
  await expect(page.getByRole('alert')).toContainText('task.create')
  expect(state.requests).toHaveLength(0)
  expect(state.logicalQueues.size).toBe(0)
  expect(state.forbidden).toEqual([])
})

test('same-tab reload after a lost response reuses queue and delivery IDs, with one logical queue', async ({ page }) => {
  const state = await isolatedApi(page)
  await page.goto('/operations/xy-tasks/xy-tasks-01')
  await submit(page)
  await expect(page.getByRole('alert').filter({ hasText: '未确认本次结果' })).toBeVisible()
  const first = state.requests[0]!
  expect(first.items[0]!.mediaAssetIds).toEqual(['asset-1', 'asset-2'])
  await page.reload()
  await submit(page)
  await expect(page.getByTestId('xianyu-publish-queue-result')).toContainText(first.queueId)
  expect(state.requests).toHaveLength(2)
  expect(state.requests[1]).toEqual(first)
  expect(state.logicalQueues.size).toBe(1)
  await submit(page)
  await expect(page.getByRole('status')).toContainText('已确认')
  expect(state.requests).toHaveLength(2)
  expect(state.forbidden).toEqual([])
})

test('session tenant change cannot reuse another tenant queue identity', async ({ page }) => {
  const state = await isolatedApi(page)
  await page.goto('/operations/xy-tasks/xy-tasks-01')
  await submit(page)
  await expect(page.getByRole('alert').filter({ hasText: '未确认本次结果' })).toBeVisible()
  state.tenantId = 'tenant-2'
  await page.reload()
  await submit(page)
  await expect(page.getByTestId('xianyu-publish-queue-result')).toBeVisible()
  expect(state.requests[1]!.queueId).not.toBe(state.requests[0]!.queueId)
  expect(state.requests[1]!.items[0]!.deliveryId).not.toBe(state.requests[0]!.items[0]!.deliveryId)
  expect(state.forbidden).toEqual([])
})

test('missing session or corrupt retry storage blocks POST', async ({ page }) => {
  const state = await isolatedApi(page)
  await page.goto('/operations/xy-tasks/xy-tasks-01')
  await submit(page)
  await expect(page.getByRole('alert').filter({ hasText: '未确认本次结果' })).toBeVisible()
  await page.evaluate(() => {
    const key = Object.keys(sessionStorage).find((item) => item.startsWith('cloudctl.xianyu-publish-queue.v1.'))!
    sessionStorage.setItem(key, '{corrupt')
  })
  await page.reload()
  await submit(page)
  await expect(page.getByRole('alert').filter({ hasText: '存储失败或损坏' })).toBeVisible()
  expect(state.requests).toHaveLength(1)
  state.sessionAvailable = false
  await page.reload()
  await expect(page.getByTestId('creation-block')).toContainText('缺少已验证')
  await expect(page.getByRole('button', { name: '创建或查询队列' }).first()).toBeDisabled()
  expect(state.requests).toHaveLength(1)
  expect(state.forbidden).toEqual([])
})

test('long labels and UUID identities stay within the viewport and queue result', async ({ page }, testInfo) => {
  const state = await isolatedApi(page, true)
  await page.goto('/operations/xy-tasks/xy-tasks-01')
  await submit(page)
  const result = page.getByTestId('xianyu-publish-queue-result')
  await expect(result).toContainText('44444444-4444-4444-8444-444444444444')
  await expect(result).toContainText('尚未派发、尚未发布')
  await expect(page.locator('.selection .chip-name')).toContainText(state.deviceLabel)
  await expect(page.locator('.selection .picker')).toHaveText(state.productTitle)
  await page.evaluate(() => document.fonts.ready)
  await page.evaluate(() => window.scrollTo(0, 0))
  const screenshot = fileURLToPath(new URL(
    `../../../artifacts/web-publish-queue-20260929/queue-${testInfo.project.name}.png`, import.meta.url,
  ))
  await page.screenshot({ path: screenshot, fullPage: true, animations: 'disabled' })
  await testInfo.attach(`queue-${testInfo.project.name}`, { path: screenshot, contentType: 'image/png' })
  const geometry = await result.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const documentWidth = document.documentElement.clientWidth
    return {
      documentWidth, documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      queueWidth: element.clientWidth, queueScrollWidth: element.scrollWidth,
      queueLeft: rect.left, queueRight: rect.right,
      overflowingText: [...element.children].filter((child) => {
        const bounds = child.getBoundingClientRect()
        return child.scrollWidth > child.clientWidth + 1 || bounds.left < rect.left - 1 || bounds.right > rect.right + 1
      }).map((child) => child.textContent),
    }
  })
  await testInfo.attach('overflow-measurements', { body: JSON.stringify(geometry, null, 2), contentType: 'application/json' })
  expect(geometry.documentScrollWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.documentWidth + 1)
  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.documentWidth + 1)
  expect(geometry.queueScrollWidth).toBeLessThanOrEqual(geometry.queueWidth + 1)
  expect(geometry.queueLeft).toBeGreaterThanOrEqual(0)
  expect(geometry.queueRight).toBeLessThanOrEqual(geometry.documentWidth + 1)
  expect(geometry.overflowingText).toEqual([])
  const catalog = page.getByRole('region', { name: '商品目录', exact: true })
  const tableGeometry = await catalog.evaluate((element) => {
    element.scrollLeft = element.scrollWidth
    const rect = element.getBoundingClientRect()
    const action = element.querySelector('.ops button')!.getBoundingClientRect()
    return {
      scrollWidth: element.scrollWidth, width: element.clientWidth, scrollLeft: element.scrollLeft,
      left: rect.left, right: rect.right, actionLeft: action.left, actionRight: action.right,
    }
  })
  expect(tableGeometry.actionLeft).toBeGreaterThanOrEqual(tableGeometry.left)
  expect(tableGeometry.actionRight).toBeLessThanOrEqual(tableGeometry.right)
  if (testInfo.project.name === 'mobile') {
    expect(tableGeometry.scrollWidth).toBeGreaterThan(tableGeometry.width)
    expect(tableGeometry.scrollLeft).toBeGreaterThan(0)
  }
  expect(state.requests).toHaveLength(1)
  expect(state.forbidden).toEqual([])
})
