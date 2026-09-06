import { expect, test } from '@playwright/test'

test('Studio creates an explicit fallback session and exposes Monaco', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Automation Studio')).toBeVisible()
  await expect(page.getByText('publish.py')).toBeVisible()
  await expect(page.getByText('Python 3.12 · cloudctl_automation_sdk')).toBeVisible()
  await expect(page.getByText('显式模拟设备流 · 非真机证据')).toBeVisible()
  await expect(page.locator('.monaco-editor')).toBeVisible()
  await page.getByRole('button', { name: /创建 15 分钟会话/ }).click()
  await expect(page.getByText('模拟会话已连接')).toBeVisible()
  await page.getByTitle('单步').click()
  await expect(page.getByText('PREFLIGHT', { exact: true })).toBeVisible()
})

test('Commit intent requires confirmation and disables replay afterwards', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /创建 15 分钟会话/ }).click()
  const step = page.getByTitle('单步')
  await step.click()
  await step.click()
  await step.click()
  await step.click()
  await expect(page.getByRole('heading', { name: '即将写入 Commit Intent' })).toBeVisible()
  await page.getByRole('button', { name: '确认写入模拟 Intent' }).click()
  await expect(page.getByText('COMMIT_INTENT_WRITTEN', { exact: true })).toBeVisible()
  await expect(page.getByTitle('回退重放')).toBeDisabled()
})
