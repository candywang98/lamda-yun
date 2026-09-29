import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchXianyuTaskDevices } from '@/data/xianyu-task-devices'
import { account, device } from './xianyu-publish-fixtures'

const state = vi.hoisted(() => ({ configured: true, devices: vi.fn(), accounts: vi.fn() }))
vi.mock('@/api/control', () => ({
  get controlApiConfigured() { return state.configured },
  createControlApiClient: () => state,
}))

beforeEach(() => {
  state.configured = true
  state.devices.mockReset().mockResolvedValue([device()])
  state.accounts.mockReset().mockResolvedValue([account()])
})

describe('Control API xianyu account identity', () => {
  it('maps a unique real-shape BOUND xianyu account without using device ID as account ID', async () => {
    expect(await fetchXianyuTaskDevices()).toEqual([expect.objectContaining({
      id: 'device-1', accountId: 'account-1', account: 'Seller', online: true,
    })])
  })

  it('keeps devices visible when the account API fails and reports an actionable error', async () => {
    state.accounts.mockRejectedValue(new Error('403'))
    const onError = vi.fn()
    expect(await fetchXianyuTaskDevices(onError)).toEqual([expect.objectContaining({
      id: 'device-1', accountId: null, accountError: expect.stringContaining('读取失败'),
    })])
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('设备仍可查看'))
  })

  it('does not select one of multiple bound accounts', async () => {
    state.accounts.mockResolvedValue([account(), account('device-1', 'account-2')])
    expect(await fetchXianyuTaskDevices()).toEqual([expect.objectContaining({
      accountId: null, accountError: expect.stringContaining('多个'),
    })])
  })

  it.each([
    { status: 'SUSPENDED' }, { status: 'REVOKED' }, { status: undefined },
    { revokedAt: '2026-09-29T01:00:00Z' }, { revokedAt: undefined },
  ])('does not enable an unauthorized or revoked account %j', async (overrides) => {
    state.accounts.mockResolvedValue([{ ...account(), ...overrides }])
    expect((await fetchXianyuTaskDevices())[0]!.accountId).toBeNull()
  })

  it.each([
    { status: 'UNBOUND' }, { historical: true }, { accountId: 'other' },
    { platform: 'douyin' }, { unboundAt: '2026-09-29T01:00:00Z' },
  ])('rejects invalid or historical binding %j', async (overrides) => {
    const row = account()
    state.accounts.mockResolvedValue([{ ...row, bindings: [{ ...row.bindings[0], ...overrides }] }])
    expect((await fetchXianyuTaskDevices())[0]!.accountId).toBeNull()
  })

  it('does not guess IDs from accounts with no matching xianyu binding', async () => {
    state.accounts.mockResolvedValue([{ ...account(), platform: 'douyin' }, account('device-other')])
    expect((await fetchXianyuTaskDevices())[0]!.accountId).toBeNull()
  })

  it('keeps devices but fails closed on malformed account response', async () => {
    state.accounts.mockResolvedValue({ accounts: [account()] })
    expect((await fetchXianyuTaskDevices())[0]!.accountId).toBeNull()
  })

  it('reports a device API failure', async () => {
    state.devices.mockRejectedValue(new Error('offline'))
    const onError = vi.fn()
    expect(await fetchXianyuTaskDevices(onError)).toEqual([])
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('设备列表读取失败'))
  })

  it('does not fetch any data without API configuration', async () => {
    state.configured = false
    expect(await fetchXianyuTaskDevices()).toEqual([])
    expect(state.devices).not.toHaveBeenCalled()
    expect(state.accounts).not.toHaveBeenCalled()
  })
})
