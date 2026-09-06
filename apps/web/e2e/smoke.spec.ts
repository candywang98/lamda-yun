import { expect, test } from '@playwright/test'
import { operationPath, operationsCatalog } from '../src/data/operations-catalog'

test('legacy CloudCtl URLs land in the single operations workspace', async ({ page }) => {
  await page.goto('/mobile-automation', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/operations\/system-home\/system-home-02/)
  await expect(page.locator('.yy-shell')).toBeVisible()
  await expect(page.getByText('云控工作台')).toBeVisible()
  await expect(page.locator('body')).not.toContainText('Internal Server Error')
})

test('root and device list URLs stay inside the operations workspace', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/operations$/)
  await expect(page.locator('.yy-shell')).toBeVisible()

  await page.goto('/devices', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/operations\/system-home\/system-home-02/)
  await expect(page.getByText('设备列表').first()).toBeVisible()
})

test('operations sidebar exposes all 15 modules through scrolling', async ({ page }, testInfo) => {
  await page.goto('/operations')
  if (testInfo.project.name === 'mobile') await page.locator('.mobile-menu').click()

  const navigation = page.locator('.yy-nav, .nav-scroll').first()
  const moduleLinks = page.locator('.operation-module-nav')
  await expect(moduleLinks).toHaveCount(15)
  await expect(page.getByText('云控工作台')).toBeVisible()
  await expect(page.getByText('原始页面路由')).toBeVisible()

  const dimensions = await navigation.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }))
  expect(dimensions.overflowY).toBe('auto')
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight)

  await navigation.evaluate((element) => { element.scrollTop = element.scrollHeight })
  await expect(moduleLinks.last()).toContainText('个人中心')
  await expect(moduleLinks.last()).toBeInViewport()
})

test('operation details expose PDF source, page workflow and domain fields', async ({ page }, testInfo) => {
  if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/operations/product-editor/product-editor-03')
  await expect(page.getByText('竞品页面依据')).toHaveCount(0)
  await expect(page.getByLabel('水印模板')).toBeVisible()
  await expect(page.getByLabel('不透明度（%）')).toHaveValue('72')
  await page.getByRole('button', { name: '保存配置' }).click()
  await expect(page.getByRole('status')).toContainText('配置已保存到当前浏览器')
  const assetDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出索引' }).click()
  await expect((await assetDownload).suggestedFilename()).toBe('cloudctl-product-editor-03-assets.json')

  await page.goto('/operations/collection/collection-01')
  await expect(page.getByLabel('公开链接')).toBeVisible()
  await expect(page.getByRole('button', { name: '策略已阻断' }).first()).toBeDisabled()
  const recordsDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出结果' }).click()
  await expect((await recordsDownload).suggestedFilename()).toBe('cloudctl-collection-01-records.csv')
})

test('operations catalog exposes all 134 unique pages and 111 source routes', async ({ page }) => {
  await page.goto('/operations')
  const operationLinks = page.locator('.operation-link-list a')
  await expect(operationLinks).toHaveCount(134)

  const paths = await operationLinks.evaluateAll((links) => links.map((link) => new URL((link as HTMLAnchorElement).href).pathname))
  expect(new Set(paths).size).toBe(134)
  expect(new Set(paths)).toEqual(new Set(operationsCatalog.map(operationPath)))

  const sourceRoutes = await page.locator('.operation-link-copy small').allTextContents()
  expect(sourceRoutes).toHaveLength(134)
  expect(new Set(sourceRoutes).size).toBe(111)
})

const operationBatches = Array.from({ length: 8 }, (_, batchIndex) => (
  operationsCatalog.filter((_, operationIndex) => operationIndex % 8 === batchIndex)
))

for (const [batchIndex, operations] of operationBatches.entries()) {
  test(`operation pages batch ${batchIndex + 1} renders exact PDF metadata`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium', 'The full catalog traversal runs once on desktop Chromium.')
    test.setTimeout(60_000)

    for (const operation of operations) {
      await page.goto(operationPath(operation), { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.page-header h2')).toHaveText(operation.title)
      const sourcePanel = page.locator('.operation-source-panel')
      await expect(sourcePanel).toContainText(`PDF 第 ${operation.sourcePage} 页`)
      await expect(sourcePanel.locator('code')).toHaveText(operation.sourceRoute)
      await expect(page.locator('.operation-page-spec')).toContainText(`页面规格 ${String(operation.index).padStart(3, '0')}`)
    }
  })
}

test('unknown operation URLs redirect to the catalog', async ({ page }) => {
  await page.goto('/operations/not-a-module/not-an-operation')
  await expect(page).toHaveURL(/\/operations$/)
  await expect(page.locator('.page-header h2')).toHaveText('运营功能目录')
})
