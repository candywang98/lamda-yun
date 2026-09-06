import { defineConfig, devices } from '@playwright/test'

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
const chromiumLaunchOptions = executablePath ? { executablePath } : {}
const artifactsRoot = process.env.PLAYWRIGHT_ARTIFACTS_DIR

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  workers: Number(process.env.PLAYWRIGHT_WORKERS ?? 2),
  outputDir: artifactsRoot ? `${artifactsRoot}/test-results` : 'test-results',
  reporter: [['list'], ['html', { open: 'never', outputFolder: artifactsRoot ? `${artifactsRoot}/playwright-report` : 'playwright-report' }]],
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure', launchOptions: chromiumLaunchOptions },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173`,
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
  },
})
