import { execFileSync } from 'node:child_process'
import { expect, test } from '@playwright/test'

const base = process.env.CLOUDCTL_DEPLOY_SMOKE_URL?.replace(/\/$/, '')
const productionBase = 'https://43.133.243.154.sslip.io/cloudctl-mobile'
if (base && base !== productionBase) throw new Error('Deployment smoke target must match the configured production site')

function credentials() {
  const script = [
    'import json, pathlib, subprocess',
    'password = pathlib.Path("/home/ubuntu/cloudctl-mobile/shared/web-basic-password.txt").read_text().strip()',
    'text = subprocess.check_output(["sudo", "-n", "cat", "/etc/nginx/.cloudctl_htpasswd"], text=True)',
    'users = [line.split(":", 1)[0] for line in text.splitlines() if ":" in line]',
    'assert len(users) == 1',
    'print(json.dumps({"username": users[0], "password": password}))',
  ].join('; ')
  const result = execFileSync('ssh', [
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'seoul',
    'python3', '-c', `'${script}'`,
  ], { encoding: 'utf8', timeout: 20_000 })
  return JSON.parse(result) as { username: string; password: string }
}

test.use({
  httpCredentials: base ? credentials() : undefined,
  trace: 'off',
  screenshot: 'off',
})

test.describe('authenticated read-only deployment smoke', () => {
  test.skip(!base, 'Set CLOUDCTL_DEPLOY_SMOKE_URL explicitly to verify the deployed site')
  for (const [name, route, apiPath] of [
    ['orders', '/orders', '/api/v1/orders'],
    ['inbox', '/im', '/api/v1/im/threads'],
    ['fleet', '/fleet', '/api/v1/devices'],
    ['products', '/operations/product-management/product-management-01', '/api/v1/products'],
  ]) {
    test(`${name} loads the deployed app and real API`, async ({ page }, info) => {
      const pageErrors: string[] = []
      const blockedWrites: string[] = []
      const apiErrors: string[] = []
      page.on('pageerror', (error) => pageErrors.push(error.message))
      page.on('response', (response) => {
        if (response.url().includes('/api/v1/') && response.status() >= 400) {
          apiErrors.push(`${response.status()} ${new URL(response.url()).pathname}`)
        }
      })
      await page.route('**/api/v1/**', async (request) => {
        if (!['GET', 'HEAD'].includes(request.request().method())) {
          blockedWrites.push(`${request.request().method()} ${new URL(request.request().url()).pathname}`)
          await request.abort()
          return
        }
        await request.continue()
      })
      const response = page.waitForResponse((item) => new URL(item.url()).pathname === apiPath)
      await page.goto(`${base}${route}`)
      expect((await response).status()).toBe(200)
      await expect(page.getByText('Control API 会话已验证', { exact: true })).toBeAttached()
      await expect(page.locator('.yy-content')).toBeVisible()
      if (name === 'fleet') await expect(page.getByRole('button', { name: '刷新设备状态', exact: true })).toBeEnabled()
      if (name === 'orders') await expect(page.locator('.yy-content').getByRole('button', { name: '刷新', exact: true })).toBeEnabled()
      if (name === 'inbox') {
        await expect(page.locator('.im-threads')).toHaveAttribute('aria-busy', 'false')
        await expect(page.getByLabel('监听总开关')).toBeAttached()
      }
      if (name === 'products') await expect(page.getByText('加载中...', { exact: true })).toHaveCount(0)
      await expect(page.locator('.notice-danger[role=alert], .yy-error, .flash.error')).toHaveCount(0)
      await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true })
      expect(await page.evaluate(() => document.documentElement.scrollWidth))
        .toBeLessThanOrEqual(page.viewportSize()!.width + 1)
      expect(pageErrors).toEqual([])
      expect(apiErrors).toEqual([])
      expect(blockedWrites).toEqual([])
    })
  }
})
