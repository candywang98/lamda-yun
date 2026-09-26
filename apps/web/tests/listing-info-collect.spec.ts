import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { deviceLabel, LISTING_COLLECT_CONFIG_KEY } from '@/data/listing-info-collect'
import { useSessionStore } from '@/stores/session'
import ListingInfoCollectView from '@/views/ListingInfoCollectView.vue'
import { listingHistoryRows, newListingCollectBatch } from '@/features/fleet/listing-collection'
import type { FleetListingHistoryResult, FleetListingItem } from '@/features/fleet/listings-api'

const api = vi.hoisted(() => ({
  configured: true,
  devices: vi.fn(),
  history: vi.fn(),
  dispatch: vi.fn(),
}))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return api.configured },
  createControlApiClient: () => ({ devices: api.devices }),
}))
vi.mock('@/features/fleet/listings-api', () => ({
  listFleetListings: api.history,
  dispatchListingCollectTask: api.dispatch,
}))

const taskId = '018f1a2b-0000-7000-8000-000000000001'
const deviceRows = ['a', 'b', 'c'].map((id) => ({
  id: `device-${id}`, logicalName: `Phone ${id.toUpperCase()}`,
  lastSeenAt: id === 'c' ? null : new Date().toISOString(),
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function item(overrides: Partial<FleetListingItem> = {}): FleetListingItem {
  return {
    id: 'row-a', deviceId: 'device-a', platform: 'xianyu', itemKey: 'shared-item',
    dedupeMarker: 'fixture', title: 'Fixture listing', priceCents: null, priceText: null,
    statusText: '在售', snapshotCount: 1,
    firstSeenAt: '2026-09-26T00:00:00Z', lastSeenAt: '2026-09-26T00:00:00Z',
    ...overrides,
  }
}

function history(items: FleetListingItem[] = [], nextCursor: string | null = null): FleetListingHistoryResult {
  return { items, total: items.length, nextCursor }
}

function mountView(roles = ['device_operator'], deviceIds: unknown = ['device-a']) {
  localStorage.setItem(LISTING_COLLECT_CONFIG_KEY, JSON.stringify({ deviceIds, schedule: '每周重复' }))
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.applySession({ userId: 'test-user', tenantId: 'test-tenant', roles, mfa: true, requestId: 'fixture' })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: ListingInfoCollectView }] })
  return { ...render(ListingInfoCollectView, { global: { plugins: [pinia, router] } }), session }
}

beforeEach(() => {
  vi.restoreAllMocks()
  api.configured = true
  api.devices.mockReset().mockResolvedValue(deviceRows)
  api.history.mockReset().mockResolvedValue(history())
  api.dispatch.mockReset().mockResolvedValue({ taskId })
  localStorage.clear()
})

describe('listing info collect labels', () => {
  it('renders device name with bound account', () => {
    expect(deviceLabel({ id: '1', name: '11', account: 'xy920065163305', online: false })).toBe('11(xy920065163305)')
    expect(deviceLabel({ id: '2', name: 'LE2100', account: '', online: false })).toBe('LE2100')
  })
})

describe('listing-sync collection gates', () => {
  it('creates independent same-day batches and displays accepted task IDs, not execution success', async () => {
    const view = mountView()
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    expect(view.getByText(taskId)).toBeTruthy()
    expect(view.getByText('本批次 1 台设备：已受理 1 台，未确认 0 台')).toBeTruthy()
    expect(view.queryByText('执行成功')).toBeNull()
    await fireEvent.click(view.getByRole('button', { name: '新建采集任务' }))
    await flushPromises()
    expect(api.dispatch).toHaveBeenCalledTimes(2)
    const [first, second] = api.dispatch.mock.calls.map(([input]) => input)
    expect(first.deviceId).toBe('device-a')
    expect(second.deviceId).toBe(first.deviceId)
    expect(second.idempotencyKey).not.toBe(first.idempotencyKey)
  })

  it('blocks double clicks, selection and saving while a batch is pending', async () => {
    const pending = deferred<{ taskId: string }>()
    api.dispatch.mockReturnValueOnce(pending.promise)
    const view = mountView()
    await flushPromises()
    const create = view.getByRole('button', { name: '创建任务' })
    await Promise.all([fireEvent.click(create), fireEvent.click(create)])
    expect(api.dispatch).toHaveBeenCalledTimes(1)
    expect((create as HTMLButtonElement).disabled).toBe(true)
    expect((view.getByRole('button', { name: '保存配置' }) as HTMLButtonElement).disabled).toBe(true)
    for (const checkbox of view.getAllByRole('checkbox')) expect((checkbox as HTMLInputElement).disabled).toBe(true)
    pending.resolve({ taskId })
    await flushPromises()
    expect((view.getByRole('button', { name: '新建采集任务' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('continues after partial failure, retries only unresolved original devices with SAME keys despite selection changes', async () => {
    api.dispatch.mockResolvedValueOnce({ taskId }).mockRejectedValueOnce(new Error('ambiguous network result'))
      .mockResolvedValueOnce({ taskId: '018f1a2b-0000-7000-8000-000000000003' })
    const view = mountView(['device_operator'], ['device-a', 'device-b', 'device-c'])
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    expect(api.dispatch.mock.calls.map(([input]) => input.deviceId)).toEqual(['device-a', 'device-b', 'device-c'])
    expect(view.getByText('本批次 3 台设备：已受理 2 台，未确认 1 台')).toBeTruthy()
    expect(view.getByText('ambiguous network result')).toBeTruthy()
    expect((view.getByRole('button', { name: '新建采集任务' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(view.getByRole('button', { name: '全部取消选择' }))
    await fireEvent.click(view.getByRole('checkbox', { name: /Phone A/ }))
    await fireEvent.click(view.getByRole('button', { name: '重试未确认设备' }))
    await flushPromises()
    expect(api.dispatch).toHaveBeenCalledTimes(4)
    expect(api.dispatch.mock.calls[3]![0]).toEqual(api.dispatch.mock.calls[1]![0])
    expect(view.getByText('本批次 3 台设备：已受理 3 台，未确认 0 台')).toBeTruthy()
    expect(view.queryByRole('button', { name: '重试未确认设备' })).toBeNull()
  })

  it('keeps malformed-response failures unresolved through repeated same-key retries', async () => {
    api.dispatch.mockRejectedValueOnce(new Error('派发响应缺少有效 taskId，结果未确认'))
      .mockRejectedValueOnce(new Error('still ambiguous'))
    const view = mountView()
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    expect(view.getByText('本批次 1 台设备：已受理 0 台，未确认 1 台')).toBeTruthy()
    for (let retry = 0; retry < 2; retry++) {
      await fireEvent.click(view.getByRole('button', { name: '重试未确认设备' }))
      await flushPromises()
    }
    expect(api.dispatch).toHaveBeenCalledTimes(3)
    expect(api.dispatch.mock.calls[0]![0]).toEqual(api.dispatch.mock.calls[1]![0])
    expect(api.dispatch.mock.calls[1]![0]).toEqual(api.dispatch.mock.calls[2]![0])
    expect(view.getByText(taskId)).toBeTruthy()
  })

  it.each([
    { selection: [] }, { selection: ['deleted-device'] }, { selection: 'not-an-array' },
  ])('does not dispatch without a real selected device: $selection', async ({ selection }) => {
    const view = mountView(['device_operator'], selection)
    await flushPromises()
    const create = view.getByRole('button', { name: '创建任务' })
    expect((create as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(create)
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it('uses only actual selected devices, excluding stale saved IDs', async () => {
    const view = mountView(['device_operator'], ['device-b', 'deleted-device'])
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    expect(api.dispatch).toHaveBeenCalledTimes(1)
    expect(api.dispatch.mock.calls[0]![0].deviceId).toBe('device-b')
  })

  it('enforces read-only permission in handlers as well as disabled controls', async () => {
    const view = mountView(['viewer'])
    await flushPromises()
    const create = view.getByRole('button', { name: '创建任务' }) as HTMLButtonElement
    expect(create.disabled).toBe(true)
    create.disabled = false
    await fireEvent.click(create)
    const checkbox = view.getByRole('checkbox', { name: /Phone B/ }) as HTMLInputElement
    checkbox.disabled = false
    await fireEvent.click(checkbox)
    const saved = localStorage.getItem(LISTING_COLLECT_CONFIG_KEY)
    const save = view.getByRole('button', { name: '保存配置' }) as HTMLButtonElement
    save.disabled = false
    await fireEvent.click(save)
    expect(localStorage.getItem(LISTING_COLLECT_CONFIG_KEY)).toBe(saved)
    expect(api.dispatch).not.toHaveBeenCalled()
    expect(api.history).toHaveBeenCalledTimes(1)
    expect(view.getByText('当前角色只读，不能创建采集任务。')).toBeTruthy()
  })

  it('stops later devices on permission revocation and protects accepted devices when permission is restored', async () => {
    const pending = deferred<{ taskId: string }>()
    api.dispatch.mockReturnValueOnce(pending.promise)
    const view = mountView(['device_operator'], ['device-a', 'device-b'])
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    view.session.applySession({ userId: 'test-user', tenantId: 'test-tenant', roles: ['viewer'], mfa: true, requestId: 'fixture' })
    pending.resolve({ taskId })
    await flushPromises()
    expect(api.dispatch).toHaveBeenCalledTimes(1)
    expect(view.getByText('当前身份缺少 device.control 权限，未派发')).toBeTruthy()
    const retry = view.getByRole('button', { name: '重试未确认设备' }) as HTMLButtonElement
    expect(retry.disabled).toBe(true)
    retry.disabled = false
    await fireEvent.click(retry)
    expect(api.dispatch).toHaveBeenCalledTimes(1)
    view.session.applySession({ userId: 'test-user', tenantId: 'test-tenant', roles: ['device_operator'], mfa: true, requestId: 'fixture' })
    await flushPromises()
    await fireEvent.click(retry)
    await flushPromises()
    expect(api.dispatch.mock.calls.map(([input]) => input.deviceId)).toEqual(['device-a', 'device-b'])
  })

  it('does not dispatch remaining devices after unmount', async () => {
    const pending = deferred<{ taskId: string }>()
    api.dispatch.mockReturnValueOnce(pending.promise)
    const view = mountView(['device_operator'], ['device-a', 'device-b'])
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    view.unmount()
    pending.resolve({ taskId })
    await flushPromises()
    expect(api.dispatch).toHaveBeenCalledTimes(1)
  })

  it('shows device loading/errors, recovers on refresh, and never submits during discovery', async () => {
    const pending = deferred<typeof deviceRows>()
    api.devices.mockReturnValueOnce(pending.promise)
    const view = mountView()
    await flushPromises()
    expect(view.getByText('加载设备中…')).toBeTruthy()
    expect((view.getByRole('button', { name: '创建任务' }) as HTMLButtonElement).disabled).toBe(true)
    pending.reject(new Error('device discovery failed'))
    await flushPromises()
    expect(view.getByText('device discovery failed')).toBeTruthy()
    await fireEvent.click(view.getByRole('button', { name: '刷新设备' }))
    await flushPromises()
    expect(view.getAllByRole('checkbox')).toHaveLength(3)
    expect(view.queryByText('device discovery failed')).toBeNull()
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it('does not use mock devices or permit collection when API is unconfigured', async () => {
    api.configured = false
    const view = mountView()
    await flushPromises()
    expect(view.getByText('未配置 Control API，无法读取执行设备')).toBeTruthy()
    expect(view.queryAllByRole('checkbox')).toHaveLength(0)
    const create = view.getByRole('button', { name: '创建任务' }) as HTMLButtonElement
    create.disabled = false
    await fireEvent.click(create)
    expect(api.dispatch).not.toHaveBeenCalled()
    expect(api.devices).not.toHaveBeenCalled()
  })

  it('checks the busy discovery gate in the submit handler while stale selected devices are still visible', async () => {
    const view = mountView()
    await flushPromises()
    const pending = deferred<typeof deviceRows>()
    api.devices.mockReturnValueOnce(pending.promise)
    await fireEvent.click(view.getByRole('button', { name: '刷新设备' }))
    const create = view.getByRole('button', { name: '创建任务' }) as HTMLButtonElement
    expect(create.disabled).toBe(true)
    create.disabled = false
    await fireEvent.click(create)
    expect(api.dispatch).not.toHaveBeenCalled()
    pending.resolve([])
    await flushPromises()
    expect(view.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('fails closed if a unique batch identity cannot be generated', async () => {
    const view = mountView()
    await flushPromises()
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => { throw new Error('unavailable') })
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    expect(view.getByText('无法生成采集批次标识，未派发任务')).toBeTruthy()
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it('never retries unresolved dispatches when only history is refreshed', async () => {
    api.dispatch.mockRejectedValueOnce(new Error('unknown result'))
    const view = mountView()
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '刷新采集历史' }))
    await flushPromises()
    expect(api.history).toHaveBeenCalledTimes(2)
    expect(api.dispatch).toHaveBeenCalledTimes(1)
    expect(view.getByRole('button', { name: '重试未确认设备' })).toBeTruthy()
  })

  it('removes unsupported scheduling controls and saves immediate-only configuration', async () => {
    const view = mountView()
    await flushPromises()
    expect(view.getByText('立即执行')).toBeTruthy()
    expect(view.queryByText('每周重复')).toBeNull()
    expect(view.queryByText('定时执行')).toBeNull()
    expect(view.container.querySelector('input[type="datetime-local"]')).toBeNull()
    expect(view.getAllByRole('combobox')).toHaveLength(1)
    await fireEvent.click(view.getByRole('button', { name: '保存配置' }))
    expect(JSON.parse(localStorage.getItem(LISTING_COLLECT_CONFIG_KEY)!)).toEqual({
      deviceIds: ['device-a'], app: 'main', schedule: '立即执行',
    })
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it('reports local save failure without blocking explicit collection', async () => {
    const view = mountView()
    await flushPromises()
    vi.spyOn(localStorage instanceof Storage ? Storage.prototype : localStorage, 'setItem')
      .mockImplementation(() => { throw new Error('quota') })
    await fireEvent.click(view.getByRole('button', { name: '保存配置' }))
    expect(view.getByText('当前浏览器无法保存配置')).toBeTruthy()
    expect(view.queryByText('配置已保存到当前浏览器')).toBeNull()
    await fireEvent.click(view.getByRole('button', { name: '创建任务' }))
    await flushPromises()
    expect(api.dispatch).toHaveBeenCalledTimes(1)
  })
})

describe('listing-sync source history', () => {
  it('preserves separate device rows and legacy duplicates without inferring sources from selection', async () => {
    api.history.mockResolvedValue(history([
      item(), item({ id: 'row-b', deviceId: 'device-b' }),
      item({ id: undefined, deviceId: undefined, platform: undefined }),
      item({ id: undefined, deviceId: undefined, platform: undefined }),
    ]))
    const view = mountView()
    await flushPromises()
    expect(view.getAllByRole('row')).toHaveLength(5)
    expect(view.getByText('Phone A（device-a）')).toBeTruthy()
    expect(view.getByText('Phone B（device-b）')).toBeTruthy()
    expect(view.getAllByText('未知来源')).toHaveLength(2)
    expect(view.getAllByText('未知平台')).toHaveLength(2)
    expect(view.getAllByText('闲鱼')).toHaveLength(2)
    expect(view.getAllByText('Fixture listing')).toHaveLength(4)
  })

  it('shows unknown device IDs verbatim and preserves non-xianyu platform metadata', async () => {
    api.history.mockResolvedValue(history([item({ deviceId: 'removed-device', platform: 'other-platform' })]))
    const view = mountView()
    await flushPromises()
    expect(view.getByText('removed-device')).toBeTruthy()
    expect(view.getByText('other-platform')).toBeTruthy()
  })

  it('distinguishes loading, failure and genuinely empty history and refresh never dispatches', async () => {
    const pending = deferred<FleetListingHistoryResult>()
    api.history.mockReturnValueOnce(pending.promise)
    const view = mountView()
    await flushPromises()
    expect(view.getByText('加载采集历史中…')).toBeTruthy()
    expect(view.queryByText('暂无采集结果。')).toBeNull()
    pending.reject(new Error('history unavailable'))
    await flushPromises()
    expect(view.getByText('history unavailable')).toBeTruthy()
    expect(view.queryByText('暂无采集结果。')).toBeNull()
    await fireEvent.click(view.getByRole('button', { name: '刷新采集历史' }))
    await flushPromises()
    expect(view.getByText('暂无采集结果。')).toBeTruthy()
    expect(view.queryByText('history unavailable')).toBeNull()
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it('uses opaque cursors, rolls back failed navigation, supports previous, and refreshes page one', async () => {
    api.history.mockResolvedValueOnce(history([item({ title: 'Page one' })], 'opaque+/=='))
    const view = mountView()
    await flushPromises()
    expect(api.history).toHaveBeenLastCalledWith({ deviceId: undefined, limit: 50 })
    expect((view.getByRole('button', { name: '上一页' }) as HTMLButtonElement).disabled).toBe(true)
    api.history.mockRejectedValueOnce(new Error('page failed'))
    await fireEvent.click(view.getByRole('button', { name: '下一页' }))
    await flushPromises()
    expect(api.history).toHaveBeenLastCalledWith({ deviceId: undefined, limit: 50, cursor: 'opaque+/==' })
    expect(view.getByText('Page one')).toBeTruthy()
    expect(view.getByText('第 1 页')).toBeTruthy()
    api.history.mockResolvedValueOnce(history([item({ title: 'Page two' })]))
    await fireEvent.click(view.getByRole('button', { name: '下一页' }))
    await flushPromises()
    expect(view.getByText('第 2 页')).toBeTruthy()
    expect(view.queryByText('Page one')).toBeNull()
    expect((view.getByRole('button', { name: '下一页' }) as HTMLButtonElement).disabled).toBe(true)
    api.history.mockResolvedValueOnce(history([item({ title: 'Page one' })], 'opaque+/=='))
    await fireEvent.click(view.getByRole('button', { name: '上一页' }))
    await flushPromises()
    expect(api.history).toHaveBeenLastCalledWith({ deviceId: undefined, limit: 50 })
    api.history.mockResolvedValueOnce(history([item({ title: 'Page two' })]))
    await fireEvent.click(view.getByRole('button', { name: '下一页' }))
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '刷新采集历史' }))
    await flushPromises()
    expect(api.history).toHaveBeenLastCalledWith({ deviceId: undefined, limit: 50 })
    expect(view.getByText('第 1 页')).toBeTruthy()
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it.each(['success', 'failure'])('ignores stale %s from earlier device filters', async (outcome) => {
    const stale = deferred<FleetListingHistoryResult>()
    const current = deferred<FleetListingHistoryResult>()
    api.history.mockResolvedValueOnce(history([item({ title: 'Old data' })], 'old-cursor'))
    const view = mountView()
    await flushPromises()
    api.history.mockReturnValueOnce(stale.promise).mockReturnValueOnce(current.promise)
    await fireEvent.update(view.getByRole('combobox', { name: '来源设备' }), 'device-a')
    expect(view.queryByText('Old data')).toBeNull()
    await fireEvent.update(view.getByRole('combobox', { name: '来源设备' }), 'device-b')
    expect(api.history).toHaveBeenLastCalledWith({ deviceId: 'device-b', limit: 50 })
    current.resolve(history([item({ deviceId: 'device-b', title: 'Current result' })]))
    await flushPromises()
    if (outcome === 'success') stale.resolve(history([item({ title: 'Stale result' })], 'wrong-cursor'))
    else stale.reject(new Error('stale failure'))
    await flushPromises()
    expect(view.getByText('Current result')).toBeTruthy()
    expect(view.queryByText('Stale result')).toBeNull()
    expect(view.queryByText('stale failure')).toBeNull()
    expect((view.getByRole('button', { name: '下一页' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('does not let stale completion hide a newer pending request, including overlapping refreshes', async () => {
    const first = deferred<FleetListingHistoryResult>()
    const second = deferred<FleetListingHistoryResult>()
    api.history.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const view = mountView()
    await fireEvent.click(view.getByRole('button', { name: '刷新采集历史' }))
    first.resolve(history([item({ title: 'Stale result' })]))
    await flushPromises()
    expect(view.getByText('加载采集历史中…')).toBeTruthy()
    expect(view.queryByText('Stale result')).toBeNull()
    second.resolve(history([item({ title: 'Latest result' })]))
    await flushPromises()
    expect(view.getByText('Latest result')).toBeTruthy()
    expect(view.queryByText('加载采集历史中…')).toBeNull()
    expect(api.dispatch).not.toHaveBeenCalled()
  })

  it('resets pagination on filtering and retains readable rows when a refresh fails', async () => {
    api.history.mockResolvedValueOnce(history([item()], 'page-2'))
    const view = mountView()
    await flushPromises()
    api.history.mockResolvedValueOnce(history([item({ title: 'Second page' })]))
    await fireEvent.click(view.getByRole('button', { name: '下一页' }))
    await flushPromises()
    api.history.mockResolvedValueOnce(history([item({ title: 'Filtered result' })]))
    await fireEvent.update(view.getByRole('combobox', { name: '来源设备' }), 'device-a')
    await flushPromises()
    expect(api.history).toHaveBeenLastCalledWith({ deviceId: 'device-a', limit: 50 })
    expect(view.getByText('第 1 页')).toBeTruthy()
    expect(view.queryByText('Second page')).toBeNull()
    api.history.mockRejectedValueOnce(new Error('refresh failed'))
    await fireEvent.click(view.getByRole('button', { name: '刷新采集历史' }))
    await flushPromises()
    expect(view.getByText('Filtered result')).toBeTruthy()
    expect(view.getByText('refresh failed')).toBeTruthy()
  })

  it('does not loop pagination when the server repeats the current cursor', async () => {
    api.history.mockResolvedValueOnce(history([item()], 'cursor'))
    const view = mountView()
    await flushPromises()
    api.history.mockResolvedValueOnce(history([item()], 'cursor'))
    await fireEvent.click(view.getByRole('button', { name: '下一页' }))
    await flushPromises()
    expect((view.getByRole('button', { name: '下一页' }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('listing-specific identities', () => {
  it('deduplicates selected device IDs and copies labels into independent batch snapshots', () => {
    const device = { id: 'device-a', name: 'Original', account: '', online: true }
    const first = newListingCollectBatch([device, device])
    const second = newListingCollectBatch([device])
    device.name = 'Changed'
    expect(first).toHaveLength(1)
    expect(first[0]!.deviceName).toBe('Original')
    expect(first[0]!.idempotencyKey).not.toBe(second[0]!.idempotencyKey)
  })

  it('uses stable row IDs and collision-safe legacy occurrence keys without collapsing itemKey', () => {
    const items = [
      item({ id: 'row-a' }), item({ id: 'row-b' }),
      item({ id: null }), item({ id: undefined }), item({ id: ' ' }),
    ]
    const first = listingHistoryRows(items, 1)
    const second = listingHistoryRows(items, 2)
    expect(new Set(first.map((row) => row.key)).size).toBe(5)
    expect(first.slice(0, 2).map((row) => row.key)).toEqual(['id:row-a', 'id:row-b'])
    expect(first[0]!.key).toBe(second[0]!.key)
    expect(first[2]!.key).not.toBe(second[2]!.key)
  })
})
