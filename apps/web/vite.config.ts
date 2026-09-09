import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

function loadViteControlApiUrl(): string {
  const envPath = fileURLToPath(new URL('./.env.development', import.meta.url))
  if (!existsSync(envPath)) return 'http://127.0.0.1:18000'
  const match = readFileSync(envPath, 'utf8').match(/^VITE_CONTROL_API_URL=(.*)$/m)
  return (match?.[1]?.trim() || 'http://127.0.0.1:18000').replace(/\/$/, '')
}

const proxyTarget = loadViteControlApiUrl()

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    css: true,
  },
})
