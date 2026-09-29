import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { XianyuPublishQueueRequest } from '@/data/xianyu-publish-goods'
import { XY_PUBLISH_GOODS_CONFIG_KEY, XY_PUBLISH_GOODS_TASKS_KEY } from '@/data/xianyu-publish-goods'
import { account, device, product, queueResponse } from './xianyu-publish-fixtures'
import XianyuPublishGoodsView from '@/views/XianyuPublishGoodsView.vue'
import { useSessionStore } from '@/stores/session'

const state = vi.hoisted(() => ({ configured: true, fetch: vi.fn() }))
vi.mock('@/api/control', async () => {
  const { CloudCtlApiClient } = await import('@cloudctl/api-contracts')
  return {
    get controlApiConfigured() { return state.configured },
    createControlApiClient: () => new CloudCtlApiClient({ baseUrl: 'https://control.invalid', fetch: state.fetch }),
  }
})

let views: VueWrapper[] = []
let products = [product()]
let accounts: unknown = [account()]
let postError = false
let getError = false
let catalogError = false
let malformed = false
let inFlight = false
let pausePost: Promise<void> | null = null
let requests = new Map<string, XianyuPublishQueueRequest>()
let noSession = false
let currentSession: ReturnType<typeof useSessionStore>
let tenantId = 'tenant-1'
let sessionRoles = ['publisher']

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

async function renderView(config: { deviceIds?: string[]; productIds?: string[] } = {}) {
  localStorage.setItem(XY_PUBLISH_GOODS_CONFIG_KEY, JSON.stringify({
    deviceIds: ['device-1'], productIds: ['product-1'], ...config,
    smartVideo: 'on', formMode: 'direct', schedule: 'malicious persisted schedule',
  }))
  const router = createRouter({
    history: createMemoryHistory(), routes: [{ path: '/', component: XianyuPublishGoodsView }],
  })
  await router.push('/')
  const pinia = createPinia()
  currentSession = useSessionStore(pinia)
  currentSession.loaded = true
  if (!noSession) currentSession.applySession({
    tenantId, userId: 'user-1', roles: sessionRoles, mfa: true, requestId: 'request-1',
  })
  const view = mount(XianyuPublishGoodsView, { global: { plugins: [pinia, router], stubs: { MediaThumb: true } } })
  views.push(view)
  await flushPromises()
  return view
}

function createButtons(view: VueWrapper) {
  return view.findAll('button').filter((button) => /创建或查询队列|请求中/.test(button.text()))
}
async function submit(view: VueWrapper) {
  await createButtons(view)[0]!.trigger('click')
  await vi.waitFor(() => expect(createButtons(view)[0]!.text()).toBe('创建或查询队列'))
}
function writes() {
  return state.fetch.mock.calls.filter(([, init]) => init.method === 'POST')
}
function payload(call = 0): XianyuPublishQueueRequest {
  return JSON.parse(writes()[call]![1].body)
}

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  vi.stubEnv('VITE_CONTROL_API_URL', 'https://control.invalid')
  sessionStorage.clear()
  localStorage.clear()
  noSession = false
  tenantId = 'tenant-1'
  sessionRoles = ['publisher']
  state.configured = true
  products = [product()]
  accounts = [account()]
  postError = false
  getError = false
  catalogError = false
  malformed = false
  inFlight = false
  pausePost = null
  requests = new Map()
  state.fetch.mockReset().mockImplementation(async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname
    if (path === '/api/v1/devices' && init.method === 'GET') return response([device(), device('device-2')])
    if (path === '/api/v1/accounts' && init.method === 'GET') return response(accounts, accounts === null ? 503 : 200)
    if (path === '/api/v1/products' && init.method === 'GET') return response(products, catalogError ? 503 : 200)
    if (path === '/api/v1/xianyu/publish/queues' && init.method === 'POST') {
      const input = JSON.parse(String(init.body)) as XianyuPublishQueueRequest
      requests.set(input.queueId, input)
      expect([...Array(sessionStorage.length)].some((_, index) =>
        sessionStorage.getItem(sessionStorage.key(index)!)?.includes(input.queueId))).toBe(true)
      if (pausePost) await pausePost
      if (postError) throw new Error('request timeout')
      const raw = queueResponse(input)
      return response(malformed ? { ...raw, accountId: 'wrong-account' } : raw, 201)
    }
    if (path.startsWith('/api/v1/xianyu/publish/queues/') && init.method === 'GET') {
      if (getError) throw new Error('query unavailable')
      const input = requests.get(path.split('/').at(-1)!)!
      const raw = queueResponse(input)
      if (inFlight) {
        raw.serialAdvanceBlocked = true
        raw.targets[0]!.state = 'IN_FLIGHT'
        raw.targets[0]!.taskIds = ['task-1']
      }
      return response(raw)
    }
    throw new Error(`Forbidden endpoint ${init.method} ${path}`)
  })
})

afterEach(() => {
  views.forEach((view) => view.unmount())
  views = []
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('publish view with local Control API transport mocks', () => {
  it('blocks a viewer with valid API devices, bound account and products even on a synthetic click', async () => {
    sessionRoles = ['viewer']
    const view = await renderView()
    expect(view.findAll('.chip')).toHaveLength(2)
    expect(view.get('.selection .picker').text()).toContain(products[0]!.title)
    expect(state.fetch.mock.calls.map(([url, init]) => [new URL(url).pathname, init.method])).toEqual([
      ['/api/v1/devices', 'GET'], ['/api/v1/accounts', 'GET'], ['/api/v1/products', 'GET'],
    ])
    expect(createButtons(view).every((button) => button.element.matches(':disabled'))).toBe(true)
    expect(view.get('[data-testid="creation-block"]').text()).toContain('task.create')
    createButtons(view)[0]!.element.dispatchEvent(new MouseEvent('click'))
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain('task.create')
    expect(writes()).toHaveLength(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('rechecks task.create after async identity persistence when permission is revoked', async () => {
    const view = await renderView()
    let release!: () => void
    const paused = new Promise<void>((resolve) => { release = resolve })
    const digest = webcrypto.subtle.digest.bind(webcrypto.subtle)
    const hashing = vi.spyOn(webcrypto.subtle, 'digest').mockImplementationOnce(async (algorithm, data) => {
      await paused
      return digest(algorithm, data)
    })
    expect(currentSession.can('task.create')).toBe(true)
    await createButtons(view)[0]!.trigger('click')
    expect(hashing).toHaveBeenCalledTimes(1)
    expect(writes()).toHaveLength(0)
    currentSession.applySession({ ...currentSession.session!, roles: ['viewer'] })
    release()
    await vi.waitFor(() => expect(createButtons(view)[0]!.text()).toBe('创建或查询队列'))
    expect(sessionStorage.length).toBe(1)
    expect(view.get('[role="alert"]').text()).toContain('缺少 task.create 权限')
    expect(createButtons(view).every((button) => button.element.matches(':disabled'))).toBe(true)
    expect(writes()).toHaveLength(0)
    expect(view.find('[data-testid="xianyu-publish-queue-result"]').exists()).toBe(false)
  })

  it('creates one server queue from API products and a bound account, and shows exact target state', async () => {
    const view = await renderView()
    await submit(view)
    expect(writes()).toHaveLength(1)
    expect(payload()).toMatchObject({
      deviceId: 'device-1', accountId: 'account-1', queueId: expect.any(String),
      items: [{ description: 'Catalog description', price: '12.50', mediaAssetIds: ['asset-1', 'asset-2'],
        deliveryId: expect.any(String), completionBoundary: 'HUMAN_PRICE_HUMAN_COMMIT' }],
    })
    const result = view.get('[data-testid="xianyu-publish-queue-result"]').text()
    expect(result).toContain(payload().queueId)
    expect(result).toContain('target-0')
    expect(result).toContain('PENDING')
    expect(result).toContain('尚未派发、尚未发布')
    expect(view.text()).not.toContain('open-only')
    expect(localStorage.getItem(XY_PUBLISH_GOODS_TASKS_KEY)).toBeNull()
    expect(state.fetch.mock.calls.map(([url, init]) => [new URL(url).pathname, init.method])).toEqual([
      ['/api/v1/devices', 'GET'], ['/api/v1/accounts', 'GET'], ['/api/v1/products', 'GET'],
      ['/api/v1/xianyu/publish/queues', 'POST'],
    ])
  })

  it('early-returns on a concurrent click before the DOM disables the other button', async () => {
    let release!: () => void
    pausePost = new Promise<void>((resolve) => { release = resolve })
    const view = await renderView()
    const buttons = createButtons(view)
    buttons[0]!.element.dispatchEvent(new MouseEvent('click'))
    buttons[1]!.element.dispatchEvent(new MouseEvent('click'))
    await vi.waitFor(() => expect(writes()).toHaveLength(1))
    expect(createButtons(view).every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    release()
    await flushPromises()
  })

  it('queries instead of creating again after a successful identical submission', async () => {
    const view = await renderView()
    await submit(view)
    await submit(view)
    expect(writes()).toHaveLength(1)
    const [url, init] = state.fetch.mock.calls.at(-1)!
    expect(url).toBe(`https://control.invalid/api/v1/xianyu/publish/queues/${payload().queueId}`)
    expect(init.method).toBe('GET')
  })

  it('does not claim an already-dispatched replay is still pending', async () => {
    const view = await renderView()
    await submit(view)
    inFlight = true
    await submit(view)
    const result = view.get('[data-testid="xianyu-publish-queue-result"]').text()
    expect(result).toContain('IN_FLIGHT')
    expect(result).toContain('状态已变化')
    expect(result).not.toContain('尚未派发、尚未发布')
    expect(writes()).toHaveLength(1)
  })

  it('preserves queueId and every deliveryId on timeout retry', async () => {
    products.push(product({ id: 'product-2', price: '20' }))
    postError = true
    const view = await renderView({ productIds: ['product-2', 'product-1'] })
    await submit(view)
    expect(view.find('[data-testid="xianyu-publish-queue-result"]').exists()).toBe(false)
    expect(view.get('[data-testid="attempt-queue-id"]').text()).toContain(payload().queueId)
    const first = writes()[0]![1].body
    postError = false
    await submit(view)
    expect(writes()[1]![1].body).toBe(first)
    expect(new Set(payload().items.map((item) => item.deliveryId)).size).toBe(2)
    expect(view.text()).toContain('尚未派发、尚未发布')
  })

  it('reuses persisted IDs after page remount with a lost response, creating one logical queue', async () => {
    postError = true
    const view = await renderView()
    await submit(view)
    const first = payload()
    view.unmount()
    postError = false
    const reloaded = await renderView()
    await submit(reloaded)
    expect(payload(1)).toEqual(first)
    expect(requests.size).toBe(1)
    expect(reloaded.get('[data-testid="xianyu-publish-queue-result"]').text()).toContain(first.queueId)
  })

  it('refuses POST on corrupt storage or quota failure and retains known results', async () => {
    const view = await renderView()
    await submit(view)
    const known = view.get('[data-testid="xianyu-publish-queue-result"]').text()
    sessionStorage.setItem(sessionStorage.key(0)!, '{broken')
    await submit(view)
    expect(writes()).toHaveLength(1)
    expect(view.text()).toContain('存储失败或损坏')
    expect(view.get('[data-testid="xianyu-publish-queue-result"]').text()).toBe(known)
    view.unmount()
    sessionStorage.clear()
    vi.spyOn(Object.getPrototypeOf(window.sessionStorage), 'setItem').mockImplementation(() => { throw new Error('QuotaExceededError') })
    const next = await renderView()
    await submit(next)
    expect(writes()).toHaveLength(1)
  })

  it('blocks missing session and never infers identity from saved selections', async () => {
    noSession = true
    const view = await renderView()
    expect(createButtons(view)[0]!.attributes('disabled')).toBeDefined()
    expect(view.text()).toContain('缺少已验证的租户和用户会话')
    expect(state.fetch).not.toHaveBeenCalled()
  })

  it('does not reuse another tenant retry identity after remount', async () => {
    postError = true
    const view = await renderView()
    await submit(view)
    view.unmount()
    tenantId = 'tenant-2'
    postError = false
    const next = await renderView()
    await submit(next)
    expect(payload(1).queueId).not.toBe(payload().queueId)
    expect(payload(1).items[0]!.deliveryId).not.toBe(payload().items[0]!.deliveryId)
  })

  it('blocks in-page session change until current API catalog and identity are reloaded', async () => {
    const view = await renderView()
    await submit(view)
    currentSession.applySession({ ...currentSession.session!, tenantId: 'tenant-2' })
    await flushPromises()
    expect(view.text()).toContain('会话或 API 环境已变化')
    expect(view.find('[data-testid="xianyu-publish-queue-result"]').exists()).toBe(false)
    await submit(view)
    expect(writes()).toHaveLength(1)
  })

  it('rejects mismatched responses without success and retries with the original identity', async () => {
    malformed = true
    const view = await renderView()
    await submit(view)
    expect(view.find('[data-testid="xianyu-publish-queue-result"]').exists()).toBe(false)
    expect(view.text()).toContain('响应不完整')
    malformed = false
    await submit(view)
    expect(payload(1).queueId).toBe(payload().queueId)
  })

  it('retains verified result on failed refresh or failed creation of another selection', async () => {
    products.push(product({ id: 'product-2', title: 'Second product' }))
    const view = await renderView()
    await submit(view)
    const known = view.get('[data-testid="xianyu-publish-queue-result"]').text()
    getError = true
    await submit(view)
    expect(view.get('[data-testid="xianyu-publish-queue-result"]').text()).toBe(known)
    await view.findAll('button[title="添加发布"]')[1]!.trigger('click')
    postError = true
    await submit(view)
    expect(view.get('[data-testid="xianyu-publish-queue-result"]').text()).toBe(known)
    expect(view.text()).toContain('未确认本次结果')
    await view.findAll('button[title="添加发布"]')[1]!.trigger('click')
    getError = false
    await submit(view)
    expect(writes()).toHaveLength(2)
    expect(state.fetch.mock.calls.at(-1)![1].method).toBe('GET')
  })

  it.each([
    [{ deviceIds: [] }, '只选择 1 台'],
    [{ deviceIds: ['device-1', 'device-2'] }, '只选择 1 台'],
    [{ deviceIds: ['not-api-device'] }, '不在当前 Control API'],
    [{ deviceIds: ['device-2'] }, 'accountId'],
    [{ productIds: [] }, '待发布宝贝'],
  ])('disables invalid selection %j', async (config, message) => {
    const view = await renderView(config)
    expect(createButtons(view)[0]!.attributes('disabled')).toBeDefined()
    expect(view.get('[data-testid="creation-block"]').text()).toContain(message)
    await submit(view)
    expect(writes()).toHaveLength(0)
  })

  it('does not silently drop stale products from a requested queue', async () => {
    const view = await renderView({ productIds: ['product-1', 'not-api-product'] })
    await submit(view)
    expect(writes()).toHaveLength(0)
    expect(view.text()).toContain('不在当前 API 可用商品目录中')
  })

  it('keeps devices visible and creation disabled on account API failure', async () => {
    accounts = null
    const view = await renderView()
    expect(view.findAll('.chip')).toHaveLength(2)
    expect(view.text()).toContain('账号列表读取失败')
    expect(createButtons(view)[0]!.attributes('disabled')).toBeDefined()
    expect(writes()).toHaveLength(0)
  })

  it('does not use local products or create anything without Control API configuration', async () => {
    state.configured = false
    localStorage.setItem('cloudctl.local-products', JSON.stringify(products))
    const view = await renderView()
    expect(view.text()).toContain('未配置 Control API')
    expect(createButtons(view)[0]!.attributes('disabled')).toBeDefined()
    expect(state.fetch).not.toHaveBeenCalled()
    expect(view.findAll('tbody tr')).toHaveLength(1)
  })

  it('reports catalog failure without falling back to local products', async () => {
    catalogError = true
    localStorage.setItem('cloudctl.local-products', JSON.stringify(products))
    const view = await renderView()
    await submit(view)
    expect(view.text()).toContain('API 商品目录读取失败')
    expect(writes()).toHaveLength(0)
  })

  it('disables all legacy execution and schedule settings', async () => {
    const view = await renderView()
    const controls = view.findAll('.legacy-settings input, .legacy-settings select, .legacy-settings button')
    expect(controls.length).toBeGreaterThan(20)
    expect(controls.every((control) => control.element.matches(':disabled'))).toBe(true)
    await submit(view)
    expect(Object.keys(payload())).toEqual(['queueId', 'deviceId', 'accountId', 'items'])
  })
})
