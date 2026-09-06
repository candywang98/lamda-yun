import { defineConfig, devices } from '@playwright/test'

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

export default defineConfig({
  testDir: './e2e',
  testMatch: /product\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:4175', trace: 'retain-on-failure', launchOptions: { executablePath }, ...devices['Desktop Chrome'] },
  webServer: {
    command: 'VITE_CONTROL_API_URL=http://127.0.0.1:9999 VITE_CONTROL_API_DEV_AUTH=true vite --host 127.0.0.1 --port 4175',
    url: 'http://127.0.0.1:4175',
    reuseExistingServer: false,
  },
})
