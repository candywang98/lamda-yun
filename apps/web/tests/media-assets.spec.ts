import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  freezeMediaPool,
  MediaAssetsApiError,
  renderWatermark,
  runPublishPreflight,
} from '@/features/media-assets/api'
import {
  normalizedPoolInput,
  normalizedPreflightInput,
  normalizedWatermarkInput,
  preflightCounts,
} from '@/features/media-assets/model'
import { mediaAssetsRoutes, registerMediaAssetsRoutes } from '@/features/media-assets/routes'
import MediaAssetsWorkbenchView from '@/features/media-assets/MediaAssetsWorkbenchView.vue'
import { createMemoryHistory, createRouter } from 'vue-router'

const config = vi.hoisted(() => ({ configured: true }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return config.configured },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({ 'X-Tenant-Id': 'tenant-f10', 'X-User-Id': 'user-f10' }),
}))
vi.mock('@/api/media-assets', () => ({
  resolveMediaPreviewUrl: vi.fn(async (assetId: string) => `blob:${assetId}`),
}))

const fetcher = vi.fn()

beforeEach(() => {
  config.configured = true
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function respond(body: unknown, status = 200) {
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

describe('F10 media assets input snapshots', () => {
  it('trims stable identifiers and removes blank optional fields', () => {
    expect(normalizedWatermarkInput({
      text: '  云控  ',
      position: 'center',
      opacity: 70,
      fontSize: 32,
      margin: 12,
      ruleVersionId: '  ',
    })).toEqual({ text: '云控', position: 'center', opacity: 70, fontSize: 32, margin: 12 })
    expect(normalizedPoolInput({ taskKey: ' task-1 ', groupId: ' group-1 ', count: 2, seed: ' seed-1 ' }))
      .toEqual({ taskKey: 'task-1', groupId: 'group-1', count: 2, seed: 'seed-1' })
    expect(normalizedPreflightInput({
      productId: ' product-1 ', accountId: ' account-1 ', deviceId: ' device-1 ', platform: 'xianyu',
    })).toEqual({ productId: 'product-1', accountId: 'account-1', deviceId: 'device-1', platform: 'xianyu' })
  })

  it('rejects invalid ranges before calling the API and counts all check states', () => {
    expect(() => normalizedWatermarkInput({
      text: 'x', position: 'center', opacity: 0, fontSize: 32, margin: 12,
    })).toThrow('透明度')
    expect(() => normalizedPoolInput({ taskKey: 'task', groupId: 'group', count: 50 })).toThrow('1 到 49')
    expect(preflightCounts([
      { id: 'a', category: 'fields', status: 'PASS', detail: 'ok' },
      { id: 'b', category: 'content', status: 'WARNING', detail: 'warn' },
      { id: 'c', category: 'media', status: 'BLOCKED', detail: 'blocked' },
    ])).toEqual({ PASS: 1, WARNING: 1, BLOCKED: 1 })
  })
})

describe('F10 media assets API contract', () => {
  it('posts the three commands to their frozen endpoints without minting a platform task', async () => {
    respond({ derivativeId: 'derivative-1' })
    await renderWatermark('asset/source', {
      text: 'CloudCtl', position: 'bottom_right', opacity: 70, fontSize: 32, margin: 24,
    })
    respond({ taskKey: 'task-1', replayed: false })
    await freezeMediaPool({ taskKey: 'task-1', groupId: 'group-1', count: 1 })
    respond({ ready: true, checks: [], snapshot: {}, snapshotSha256: 'sha' })
    await runPublishPreflight({
      productId: 'product-1', accountId: 'account-1', deviceId: 'device-1', platform: 'xianyu',
    })

    expect(fetcher).toHaveBeenCalledTimes(3)
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      'http://control.test/api/v1/media-assets/asset%2Fsource/watermark:render',
      'http://control.test/api/v1/media-assets/pools:freeze',
      'http://control.test/api/v1/media-assets/publish:preflight',
    ])
    for (const [, init] of fetcher.mock.calls as [string, RequestInit][]) {
      expect(init.method).toBe('POST')
      expect(init.credentials).toBe('same-origin')
    }
    expect(fetcher.mock.calls.some(([url]) => String(url).includes('platform-tasks'))).toBe(false)
  })

  it('fails closed before any network request when Control API is unavailable', async () => {
    config.configured = false
    const error = await runPublishPreflight({
      productId: 'product-1', accountId: 'account-1', deviceId: 'device-1', platform: 'xianyu',
    }).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(MediaAssetsApiError)
    expect((error as Error).message).toContain('未配置 Control API')
    expect(fetcher).not.toHaveBeenCalled()
  })
})

describe('F10 media assets workbench', () => {
  it('registers one idempotent independent route', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    registerMediaAssetsRoutes(router)
    registerMediaAssetsRoutes(router)
    expect(mediaAssetsRoutes).toHaveLength(1)
    expect(router.getRoutes().filter((route) => route.name === 'media-assets-workbench')).toHaveLength(1)
  })

  it('disables all real commands when Control API is unavailable', () => {
    config.configured = false
    render(MediaAssetsWorkbenchView)
    expect(screen.getByText('Control API 未配置')).toBeTruthy()
    for (const button of screen.getAllByRole('button')) {
      expect((button as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('renders explainable warning and blocking checks from the read-only preflight response', async () => {
    respond({
      ready: false,
      checks: [
        { id: 'content.word.国家级', category: 'content', status: 'WARNING', detail: '国家级: 虚假主张' },
        { id: 'device.online', category: 'device', status: 'BLOCKED', detail: 'device is offline' },
      ],
      snapshot: {
        productId: 'product-1', productRevision: 3, mediaAssetIds: ['asset-1'],
        accountId: 'account-1', bindingVersion: 2, deviceId: 'device-1', platform: 'xianyu',
      },
      snapshotSha256: 'snapshot-sha',
    })
    render(MediaAssetsWorkbenchView)
    const fields = screen.getAllByRole('textbox')
    await fireEvent.update(fields[6]!, 'product-1')
    await fireEvent.update(fields[7]!, 'account-1')
    await fireEvent.update(fields[8]!, 'device-1')
    await fireEvent.click(screen.getByRole('button', { name: '执行只读预检' }))

    await waitFor(() => expect(screen.getByText('阻止任务创建')).toBeTruthy())
    expect(screen.getByText('content.word.国家级')).toBeTruthy()
    expect(screen.getByText('device.online')).toBeTruthy()
    expect(screen.getByText('告警 1')).toBeTruthy()
    expect(screen.getByText('阻断 1')).toBeTruthy()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
