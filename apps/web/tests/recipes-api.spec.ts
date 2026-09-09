import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { parseRecipePackage, recipeApi, rollbackExpectedVersion } from '@/api/recipes'
import { recipeFixture } from './fixtures/recipes'

const config = vi.hoisted(() => ({ configured: true }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return config.configured },
  controlApiBaseUrl: () => '',
  controlApiHeaders: () => ({ 'X-Tenant-Id': 'test-tenant', 'X-User-Id': 'test-operator' }),
}))
const fetcher = vi.fn()
beforeEach(() => { config.configured = true; fetcher.mockReset(); vi.stubGlobal('fetch', fetcher) })
afterEach(() => vi.unstubAllGlobals())
const respond = (body: unknown, status = 200) => fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body), { status }))

describe('Recipe HTTP contract', () => {
  it('reads catalog and encoded detail using existing authentication headers', async () => {
    const version = recipeFixture()
    respond({ items: [version] }); respond(version)
    expect(await recipeApi.catalog()).toEqual([version])
    expect(await recipeApi.detail('version:2')).toEqual(version)
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/api/v1/recipes', '/api/v1/recipes/version%3A2'])
    const init = fetcher.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('GET')
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).get('X-Tenant-Id')).toBe('test-tenant')
    expect(init.body).toBeUndefined()
  })

  it('registers the unchanged signed package and sends exact publish/rollback bodies', async () => {
    const version = recipeFixture()
    const body = { targetDeviceIds: ['device-1'], idempotencyKey: 'intent-1' }
    respond(version); respond(version); respond(version)
    await recipeApi.register(version.package)
    await recipeApi.publish(version.versionId, body)
    await recipeApi.rollback('version-1.0.0', { ...body, idempotencyKey: 'intent-2', expectedCurrentVersionId: version.versionId })
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/api/v1/recipes', '/api/v1/recipes/version-2.0.0:publish', '/api/v1/recipes/version-1.0.0:rollback'])
    expect(fetcher.mock.calls.map(([, init]) => JSON.parse(init.body))).toEqual([version.package, body, { ...body, idempotencyKey: 'intent-2', expectedCurrentVersionId: version.versionId }])
    expect(fetcher.mock.calls.every(([, init]) => init.method === 'POST')).toBe(true)
  })

  it.each([401, 403, 409, 422, 503])('surfaces HTTP %i without automatic retry or success fallback', async (status) => {
    respond({ detail: 'backend rejected' }, status)
    await expect(recipeApi.publish('version', { targetDeviceIds: ['device-1'], idempotencyKey: 'key' })).rejects.toMatchObject({ status, message: expect.stringContaining('backend rejected') })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('fails closed when API is unconfigured even if local data exists', async () => {
    config.configured = false
    await expect(recipeApi.catalog()).rejects.toThrow('未配置 Control API')
    await expect(recipeApi.register(recipeFixture().package)).rejects.toThrow('未配置 Control API')
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('rejects HTML and malformed catalog responses', async () => {
    fetcher.mockResolvedValueOnce(new Response('<html>upstream failed</html>', { status: 502 }))
    await expect(recipeApi.catalog()).rejects.toMatchObject({ status: 502 })
    respond({ wrong: [] })
    await expect(recipeApi.catalog()).rejects.toThrow('目录响应格式错误')
  })

  it('rejects malformed deployment state instead of presenting it as current/history', async () => {
    const invalid = recipeFixture()
    respond({ items: [{ ...invalid, deployments: [{ ...invalid.deployments[0], status: 'UNKNOWN' }] }] })
    await expect(recipeApi.catalog()).rejects.toThrow('版本响应格式错误')
    respond({ ...invalid, package: null })
    await expect(recipeApi.detail(invalid.versionId)).rejects.toThrow('LocalRecipePackage')
  })

  it('checks file structure without replacing signed package content', () => {
    const signed = recipeFixture().package
    expect(parseRecipePackage(JSON.stringify(signed))).toEqual(signed)
    expect(() => parseRecipePackage('{')).toThrow('JSON')
    expect(() => parseRecipePackage(JSON.stringify({ ...signed, signature: undefined }))).toThrow('完整')
    expect(() => parseRecipePackage(JSON.stringify({ ...signed, signature: {} }))).toThrow('签名')
  })
})

describe('rollback candidates', () => {
  it('requires this device history and excludes current and never deployed versions', () => {
    const current = recipeFixture()
    const old = recipeFixture('1.0.0', 'REVOKED')
    expect(rollbackExpectedVersion([current, old], 'device-1', old)).toBe(current.versionId)
    expect(rollbackExpectedVersion([current, old], 'device-2', old)).toBeNull()
    expect(rollbackExpectedVersion([current, old], 'device-1', current)).toBeNull()
    expect(rollbackExpectedVersion([current], 'device-1', old)).toBeNull()
  })
  it('fails closed for missing, duplicate or inconsistent current mappings across commands', () => {
    const current = recipeFixture()
    const old = recipeFixture('1.0.0', 'REVOKED')
    expect(rollbackExpectedVersion([old], 'device-1', old)).toBeNull()
    expect(rollbackExpectedVersion([current, current, old], 'device-1', old)).toBeNull()
    old.package.manifest.commandTypes.push('second-command')
    expect(rollbackExpectedVersion([current, old], 'device-1', old)).toBeNull()
    old.deployments.push({ ...old.deployments[0], id: 'old-second', commandType: 'second-command' })
    const other = recipeFixture('3.0.0')
    other.deployments[0].commandType = 'second-command'
    expect(rollbackExpectedVersion([current, other, old], 'device-1', old)).toBeNull()
  })
})
