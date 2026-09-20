import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ContentIOApiError,
  fetchProductRevisions,
  runContentImport,
} from '@/features/content-io/api'
import {
  parseImportPayload,
  rowErrorText,
  rowStatusLabel,
  rowStatusTone,
} from '@/features/content-io/model'
import { contentIORoutes, registerContentIORoutes } from '@/features/content-io/routes'
import ContentIOView from '@/features/content-io/ContentIOView.vue'
import { createMemoryHistory, createRouter } from 'vue-router'

const config = vi.hoisted(() => ({ configured: true }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return config.configured },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({ 'X-Tenant-Id': 'tenant-f11' }),
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

function respond(body: unknown, status = 200, headers: Record<string, string> = {}) {
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  }))
}

describe('F11 model: import payload parsing and row labels', () => {
  it('normalizes valid rows and strips blank optional fields', () => {
    const items = parseImportPayload(
      '[{"spuCode":" A-1 ","title":" 商品 ","category":"home","price":"19.90","stock":3,"description":"  ","imageUrls":["u1",2]}]',
    )
    expect(items).toHaveLength(1)
    expect(items[0]).toEqual({
      spuCode: 'A-1',
      title: '商品',
      category: 'home',
      price: '19.90',
      stock: 3,
      imageUrls: ['u1'],
    })
  })

  it('rejects malformed payloads and invalid values with row-precise messages', () => {
    expect(() => parseImportPayload('not json')).toThrow('JSON')
    expect(() => parseImportPayload('{"spuCode":"A"}')).toThrow('数组')
    expect(() => parseImportPayload('[]')).toThrow('一行')
    expect(() => parseImportPayload('[{"spuCode":"","title":"t","category":"c","price":"1","stock":1}]')).toThrow('spuCode')
    expect(() => parseImportPayload('[{"spuCode":"A","title":"t","category":"c","price":"1.999","stock":1}]')).toThrow('price')
    expect(() => parseImportPayload('[{"spuCode":"A","title":"t","category":"c","price":"1","stock":-1}]')).toThrow('stock')
  })

  it('maps row statuses to stable labels and tones', () => {
    expect(rowStatusLabel('IMPORT')).toBe('将导入')
    expect(rowStatusLabel('SKIP_EXISTING')).toBe('跳过（已存在）')
    expect(rowStatusLabel('ERROR')).toBe('错误')
    expect(rowStatusTone('IMPORT')).toBe('SUCCEEDED')
    expect(rowStatusTone('SKIP_EXISTING')).toBe('CANDIDATE')
    expect(rowStatusTone('ERROR')).toBe('BLOCKED')
    expect(rowErrorText({
      index: 0, spuCode: 'A', title: 't', status: 'ERROR',
      errors: [{ field: 'spuCode', code: 'DUPLICATE_IN_FILE', message: 'x' }],
    })).toBe('spuCode: DUPLICATE_IN_FILE')
  })
})

describe('F11 api contract', () => {
  it('posts dry-run and apply to the frozen endpoint with the apply flag', async () => {
    respond({ mode: 'DRY_RUN', summary: { total: 0, importCount: 0, skipExistingCount: 0, errorCount: 0 }, rows: [] })
    await runContentImport([{ spuCode: 'A', title: 't', category: 'c', price: '1', stock: 1 }])
    respond({ mode: 'APPLY', summary: { total: 0, importCount: 0, skipExistingCount: 0, errorCount: 0 }, rows: [] })
    await runContentImport([{ spuCode: 'A', title: 't', category: 'c', price: '1', stock: 1 }], { apply: true, importKey: 'k1' })

    expect(fetcher).toHaveBeenCalledTimes(2)
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://control.test/api/v1/content-io/products:import')
    expect(JSON.parse(String(init.body))).toEqual({
      items: [{ spuCode: 'A', title: 't', category: 'c', price: '1', stock: 1 }],
      apply: false,
    })
    const applyBody = JSON.parse(String((fetcher.mock.calls[1] as [string, RequestInit])[1].body))
    expect(applyBody.apply).toBe(true)
    expect(applyBody.importKey).toBe('k1')
  })

  it('fetches revisions with pagination params and fails closed when unconfigured', async () => {
    respond({ productId: 'p1', currentRevision: 2, total: 2, limit: 10, offset: 0, items: [] })
    await fetchProductRevisions('p1', 10, 0)
    expect(fetcher.mock.calls[0][0]).toBe(
      'http://control.test/api/v1/content-io/products/p1/revisions?limit=10&offset=0',
    )
    config.configured = false
    const error = await fetchProductRevisions('p1', 10, 0).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(ContentIOApiError)
    expect((error as Error).message).toContain('未配置 Control API')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})

describe('F11 view', () => {
  it('registers one idempotent route', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    registerContentIORoutes(router)
    registerContentIORoutes(router)
    expect(contentIORoutes).toHaveLength(1)
    expect(router.getRoutes().filter((route) => route.name === 'content-io-workbench')).toHaveLength(1)
  })

  it('dry-run renders row-precise outcomes without enabling apply until confirmed', async () => {
    respond({
      mode: 'DRY_RUN',
      apply: false,
      replayed: false,
      importKey: 'sha:f11',
      groupId: null,
      policy: 'apply=false：仅验证不写库',
      summary: { total: 3, importCount: 1, skipExistingCount: 1, errorCount: 1 },
      rows: [
        { index: 0, spuCode: 'OK-1', title: '合法行', status: 'IMPORT', errors: [] },
        { index: 1, spuCode: 'SEED', title: '已存在', status: 'SKIP_EXISTING', errors: [] },
        { index: 2, spuCode: 'DUP', title: '重复', status: 'ERROR', errors: [{ field: 'spuCode', code: 'DUPLICATE_IN_FILE', message: 'x2' }] },
      ],
    })
    render(ContentIOView)
    await fireEvent.update(screen.getAllByRole('textbox')[0]!, '[{"spuCode":"OK-1","title":"t","category":"c","price":"1","stock":1}]')
    await fireEvent.click(screen.getByRole('button', { name: '验证（不写库）' }))

    await waitFor(() => expect(screen.getByText('验证结果（未写库）')).toBeTruthy())
    expect(screen.getByText('将导入')).toBeTruthy()
    expect(screen.getByText('跳过（已存在）')).toBeTruthy()
    expect(screen.getByText('spuCode: DUPLICATE_IN_FILE')).toBeTruthy()
    expect(screen.getByText('错误 1')).toBeTruthy()
    const apply = screen.getByRole('button', { name: '确认导入' }) as HTMLButtonElement
    expect(apply.disabled).toBe(true)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('revisions panel pages through the immutable history', async () => {
    respond({ productId: 'p1', currentRevision: 2, total: 12, limit: 10, offset: 0, items: [
      { eventId: 'e1', revision: 2, action: 'product.updated', actorType: 'user', actorId: 'u1', requestId: 'r1', result: 'SUCCEEDED', afterHash: 'h2', occurredAt: '2026-09-19T01:00:00+00:00', snapshot: {} },
    ] })
    render(ContentIOView)
    const fields = screen.getAllByRole('textbox')
    await fireEvent.update(fields[fields.length - 1]!, 'p1')
    await fireEvent.click(screen.getByRole('button', { name: '查询修订' }))
    await waitFor(() => expect(screen.getByText('product.updated')).toBeTruthy())
    expect(screen.getByText('第 1–1 条')).toBeTruthy()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
