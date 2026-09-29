import { defineConfig, devices } from '@playwright/test'

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH

export default defineConfig({
  testDir: './e2e',
  testMatch: 'xianyu-publish-queue.spec.ts',
  workers: 1,
  fullyParallel: false,
  outputDir: '../../artifacts/web-publish-queue-20260929/playwright-results',
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4209',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 } },
  ],
  webServer: {
    command: 'vite --host 127.0.0.1 --port 4209 --strictPort',
    url: 'http://127.0.0.1:4209',
    reuseExistingServer: false,
    env: {
      VITE_CONTROL_API_URL: 'http://127.0.0.1:1',
      VITE_CONTROL_API_DEV_AUTH: 'false',
      VITE_OPERATIONS_MOCK_ENABLED: 'false',
    },
  },
})
