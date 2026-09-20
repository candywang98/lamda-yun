import { expect, test } from '@playwright/test'

/**
 * F13 业务表单薄层 E2E。
 *
 * 按任务卡「定向E2E仅连接staging」：当前没有可用 staging（BLK-001 未解除、
 * Control API 无公网部署），本规格只连接本地 Vite 实例验证 fail-closed 呈现，
 * 不做任何铸造调用；staging 实测状态记录为 NOT_TESTED_AGAINST_STAGING。
 */

test('business operations form renders from the catalog and stays fail-closed without a backend', async ({ page }, testInfo) => {
  if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/business-operations', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: '业务操作表单' })).toBeVisible()
  const featureSelect = page.getByRole('combobox')
  await expect(featureSelect).toBeVisible()
  const optionCount = await featureSelect.locator('option').count()
  expect(optionCount).toBeGreaterThan(50)

  const submit = page.getByRole('button', { name: /不可提交/ })
  await expect(submit).toBeVisible()
  await expect(submit).toBeDisabled()

  const snapshot = page.getByTestId('business-operation-snapshot')
  await expect(snapshot).toBeVisible()
  await expect(snapshot.locator('.preview-list')).toHaveCount(0)

  const body = page.locator('body')
  await expect(body).not.toContainText('Internal Server Error')
  await expect(body).not.toContainText('示例操作')
})

test('selecting a feature surfaces an explicit availability reason instead of minting', async ({ page }) => {
  await page.goto('/business-operations', { waitUntil: 'domcontentloaded' })
  const featureSelect = page.getByRole('combobox')
  const firstValue = await featureSelect.locator('option').nth(1).getAttribute('value')
  expect(firstValue).toBeTruthy()
  await featureSelect.selectOption(firstValue!)

  await expect(page.getByTestId('business-operation-snapshot')).toBeVisible()
  await expect(page.getByText(/PENDING|POLICY_BLOCKED|OUT_OF_SCOPE/).first()).toBeVisible()
  const submit = page.getByRole('button', { name: /不可提交/ })
  await expect(submit).toBeDisabled()
  await expect(page.getByText('提交结果')).toHaveCount(0)
})
