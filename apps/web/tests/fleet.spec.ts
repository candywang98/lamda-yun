import { createPinia } from 'pinia'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { JsonObject } from '@cloudctl/api-contracts'
import {
  FROZEN_FIXTURE_ACCOUNT_ID,
  FROZEN_FIXTURE_BINDING_VERSION,
  FROZEN_FIXTURE_DEVICE_ID,
  platformTaskFixture,
  rawFleetDeviceFixture,
} from './fixtures/fleet-devices'
import { useSessionStore } from '@/stores/session'
import {
  activeTaskFor,
  capabilityGaps,
  FLEET_CONTRACT_VERSION,
  mapFleetDevice,
  offlineReasonOf,
  permissionGapSummary,
  schedulingEligibility,
  settledTaskFor,
  type FleetTask,
} from '@/features/fleet/model'
import { cancellableTask, expandDeviceTargets, targetStatusLabel } from '@/features/fleet/batch'
import {
  fleetVersionLine,
  normalizePlatformTasks,
  resolveFleetDataMode,
  type FleetDataMode,
} from '@/features/fleet/api'
import FleetDeviceCardView from '@/features/fleet/FleetDeviceCardView.vue'
import FleetWorkbenchView from '@/features/fleet/FleetWorkbenchView.vue'

const DEVICE_A = 'dev-a-offline'
const DEVICE_B = 'dev-b-online'

function fixtureTasks(): FleetTask[] {
  return normalizePlatformTasks({
    items: [
      platformTaskFixture({ taskId: 'task-b-failed', deviceId: DEVICE_B, state: 'FAILED', errorCode: 'STEP_TIMEOUT', detail: 'B 设备发布第 4 步超时' }),
      platformTaskFixture({ taskId: 'task-b-running', deviceId: DEVICE_B, state: 'RUNNING' }),
    ],
  })
}

function deviceAFixture(): JsonObject {
  return rawFleetDeviceFixture({
    deviceId: DEVICE_A,
    logicalName: 'device-A',
    online: false,
    executable: false,
    executableGates: [],
    blockingGates: null,
    offlineReason: 'Companion 心跳超时 3 个周期',
  })
}

function deviceBFixture(): JsonObject {
  return rawFleetDeviceFixture({ deviceId: DEVICE_B, logicalName: 'device-B', accountId: 'acc-b', bindingVersion: 2 })
}

describe('fleet-identity/v1 device card mapping', () => {
  it('maps the frozen k10 fixture envelope without inventing fields', () => {
    const tasks = fixtureTasks()
    const card = mapFleetDevice(rawFleetDeviceFixture(), tasks)
    expect(card.deviceId).toBe(FROZEN_FIXTURE_DEVICE_ID)
    expect(card.online).toBe(true)
    expect(card.executable).toBe(true)
    expect(card.accountId).toBe(FROZEN_FIXTURE_ACCOUNT_ID)
    expect(card.bindingVersion).toBe(FROZEN_FIXTURE_BINDING_VERSION)
    expect(card.holderSessionId).toBe('sess-20260916-a1')
    expect(card.capabilities.map((entry) => entry.key)).toContain('flutter_anchors')
    expect(card.capabilities.find((entry) => entry.key === 'media_projection')?.supported).toBe(false)
  })

  it('keeps online (heartbeat) separate from executable (gates)', () => {
    const card = mapFleetDevice(
      rawFleetDeviceFixture({ deviceId: 'dev-x', online: false, executable: false, blockingGates: ['accessibility-enabled'] }),
      [],
    )
    expect(card.online).toBe(false)
    expect(schedulingEligibility(card)).toBe('OFFLINE')
    expect(offlineReasonOf(card)).toBe('心跳缺失（transport 门禁未上报）')

    const gated = mapFleetDevice(
      rawFleetDeviceFixture({ deviceId: 'dev-y', online: true, executable: false, blockingGates: ['ime', 'screen-unlocked'] }),
      [],
    )
    expect(gated.online).toBe(true)
    expect(schedulingEligibility(gated)).toBe('ONLINE_NOT_EXECUTABLE')
    expect(permissionGapSummary(gated)).toEqual(['输入法就绪 未满足', '屏幕已解锁 未满足'])
  })

  it('falls back to heartbeat window for online and stays fail-closed when executable is unreported', () => {
    const card = mapFleetDevice(
      { id: 'dev-z', logical_name: 'legacy', last_seen_at: new Date().toISOString() },
      [],
    )
    expect(card.online).toBe(true)
    expect(card.executable).toBeNull()
    expect(schedulingEligibility(card)).toBe('ONLINE_NOT_EXECUTABLE')
    expect(permissionGapSummary(card)).toEqual(['executable 未回传，等待 Companion 上报门禁明细'])
  })
})

describe('C10 acceptance A: per-device task isolation', () => {
  it('never attaches device B tasks to offline device A (mapper level)', () => {
    const tasks = fixtureTasks()
    const cardA = mapFleetDevice(deviceAFixture(), tasks)
    expect(cardA.online).toBe(false)
    expect(cardA.currentTask).toBeNull()
    expect(cardA.settledTask).toBeNull()
    expect(offlineReasonOf(cardA)).toBe('Companion 心跳超时 3 个周期')

    const cardB = mapFleetDevice(deviceBFixture(), tasks)
    expect(cardB.currentTask?.taskId).toBe('task-b-running')
    expect(cardB.settledTask?.taskId).toBe('task-b-failed')
    expect(activeTaskFor(DEVICE_A, tasks)).toBeNull()
    expect(settledTaskFor(DEVICE_A, tasks)).toBeNull()
  })

  it('renders device A offline without device B failure, and the failure only on B (component level)', async () => {
    const tasks = fixtureTasks()
    const cardA = mapFleetDevice(deviceAFixture(), tasks)
    const cardB = mapFleetDevice(deviceBFixture(), tasks)
    render(FleetDeviceCardView, { props: { device: cardA } })
    render(FleetDeviceCardView, { props: { device: cardB } })

    const cardANode = document.querySelector('[data-device-id="dev-a-offline"]')
    const cardBNode = document.querySelector('[data-device-id="dev-b-online"]')
    expect(cardANode).not.toBeNull()
    expect(cardBNode).not.toBeNull()

    // A：离线原因可见，B 的任务失败绝不出现。
    expect(within(cardANode as HTMLElement).getByText(/Companion 心跳超时 3 个周期/)).toBeTruthy()
    expect(within(cardANode as HTMLElement).queryByText(/B 设备发布第 4 步超时/)).toBeNull()
    expect(within(cardANode as HTMLElement).queryByText('最近失败（本设备）')).toBeNull()
    expect(within(cardANode as HTMLElement).getByText('无进行中任务')).toBeTruthy()

    // B：失败只挂在 B 自己的卡上。
    expect(within(cardBNode as HTMLElement).getByText(/最近失败（本设备）/)).toBeTruthy()
    expect(within(cardBNode as HTMLElement).getByText(/B 设备发布第 4 步超时/)).toBeTruthy()
  })
})

describe('batch expansion into explicit per-device targets', () => {
  it('expands selection into per-device statuses where capability gaps mean not-dispatched, not failure', () => {
    const tasks = fixtureTasks()
    const cards = [
      mapFleetDevice(deviceBFixture(), tasks),
      mapFleetDevice(deviceAFixture(), tasks),
      mapFleetDevice(
        rawFleetDeviceFixture({ deviceId: 'dev-gap', logicalName: 'device-gap', unsupported: ['media_projection', 'ime'] }),
        tasks,
      ),
    ]
    const targets = expandDeviceTargets(cards, {
      commandType: 'xianyu.publish_listing.steps.v1',
      requiredCapabilities: ['accessibility', 'ime'],
    })
    expect(targets.map((target) => target.status)).toEqual(['ELIGIBLE', 'OFFLINE', 'INELIGIBLE_CAPABILITY'])
    expect(targets[1]?.reason).toContain('设备离线不派发')
    expect(targets[2]?.reason).toContain('INELIGIBLE_CAPABILITY')
    expect(targetStatusLabel('INELIGIBLE_CAPABILITY')).toBe('能力缺口不派发')
    expect(capabilityGaps(['accessibility', 'ime'], cards[2]!.capabilities)).toEqual(['ime'])
    expect(capabilityGaps(['accessibility'], cards[0]!.capabilities)).toEqual([])
  })

  it('follows the server cancel guards: terminal and RECONCILING are not cancellable', () => {
    expect(cancellableTask(fixtureTasks()[1])).toEqual({ cancellable: true, reason: null })
    expect(cancellableTask(null).cancellable).toBe(false)
    expect(
      cancellableTask({ taskId: 't', deviceId: 'd', commandType: 'c', state: 'RECONCILING', runnerStatus: null, errorCode: null, detail: null, createdAt: null }).reason,
    ).toContain('RECONCILE_REQUIRED')
    expect(
      cancellableTask({ taskId: 't', deviceId: 'd', commandType: 'c', state: 'FAILED', runnerStatus: null, errorCode: null, detail: null, createdAt: null }).cancellable,
    ).toBe(false)
  })
})

describe('runtime data mode (fail-closed, mock flag, version line)', () => {
  it('resolves api > mock > unavailable and never auto-falls back to mock in production', () => {
    expect(resolveFleetDataMode(true, false)).toBe<FleetDataMode>('api')
    expect(resolveFleetDataMode(true, true)).toBe<FleetDataMode>('api')
    expect(resolveFleetDataMode(false, true)).toBe<FleetDataMode>('mock')
    expect(resolveFleetDataMode(false, false)).toBe<FleetDataMode>('unavailable')
  })

  it('normalizes the platform task list envelope ({items, nextCursor}) and plain arrays', () => {
    expect(normalizePlatformTasks({ items: [platformTaskFixture()], nextCursor: null, limit: 1 })).toHaveLength(1)
    expect(normalizePlatformTasks([platformTaskFixture({ taskId: 'x' })])).toHaveLength(1)
    expect(normalizePlatformTasks(null)).toEqual([])
  })

  it('exposes the frozen contract version on the version line', () => {
    expect(fleetVersionLine('api')).toContain(FLEET_CONTRACT_VERSION)
    expect(fleetVersionLine('mock')).toContain('Mock 数据')
    expect(fleetVersionLine('unavailable')).toContain('未配置')
  })
})

const { api, flags } = vi.hoisted(() => ({
  api: {
    devices: vi.fn(),
    listPlatformTasks: vi.fn(),
  },
  flags: {
    configured: true,
    mock: false,
  },
}))

vi.mock('@/api/control', () => ({
  get controlApiConfigured() {
    return flags.configured
  },
  get operationsMockEnabled() {
    return flags.mock
  },
  controlApiBaseUrl: () => 'http://control.test',
  controlApiHeaders: () => ({}),
  createControlApiClient: () => api,
}))

function setMode(configured: boolean, mock: boolean) {
  flags.configured = configured
  flags.mock = mock
  api.devices.mockReset()
  api.listPlatformTasks.mockReset()
}

function primeApiSuccess() {
  api.devices.mockResolvedValue([deviceAFixture(), deviceBFixture()])
  api.listPlatformTasks.mockResolvedValue({
    items: [
      platformTaskFixture({ taskId: 'task-b-failed', deviceId: DEVICE_B, state: 'FAILED', errorCode: 'STEP_TIMEOUT', detail: 'B 设备发布第 4 步超时' }),
      platformTaskFixture({ taskId: 'task-b-running', deviceId: DEVICE_B, state: 'RUNNING' }),
    ],
    nextCursor: null,
    limit: 100,
  })
}

function primeViewerSession() {
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.applySession({ userId: 'user-viewer', tenantId: 'tenant-0001', roles: ['viewer'], mfa: true, requestId: 'req-test' })
  return { pinia, session }
}

function primeOperatorSession() {
  const pinia = createPinia()
  const session = useSessionStore(pinia)
  session.applySession({ userId: 'user-op', tenantId: 'tenant-0001', roles: ['device_operator'], mfa: true, requestId: 'req-test' })
  return { pinia, session }
}

async function selectDeviceBAndExpand() {
  const cardB = await waitFor(() => {
    const node = document.querySelector('[data-device-id="dev-b-online"]')
    expect(node).not.toBeNull()
    return node as HTMLElement
  })
  await fireEvent.click(within(cardB).getByRole('checkbox'))
  await fireEvent.click(screen.getByRole('button', { name: /展开为逐设备目标/ }))
  return within(screen.getByTestId('fleet-targets').querySelector('[data-target-device="dev-b-online"]') as HTMLElement)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('C10 acceptance B: fleet workbench mock indicator and fail-closed behavior', () => {
  it('stays fail-closed when production has no API configured (no mock fallback, disabled actions)', async () => {
    setMode(false, false)
    render(FleetWorkbenchView, { global: { plugins: [createPinia()] } })
    const alerts = await screen.findAllByRole('alert')
    const unavailable = alerts.map((node) => node.textContent ?? '').join('\n')
    expect(unavailable).toContain('Control API 未配置')
    expect(unavailable).toContain('不会自动回退 Mock')
    expect(screen.queryByTestId('fleet-mock-banner')).toBeNull()
    expect(screen.queryByText('device-B')).toBeNull()
    expect((screen.getByRole('button', { name: 'Control API 不可用' }) as HTMLButtonElement).disabled).toBe(true)
    expect(api.devices).not.toHaveBeenCalled()
  })

  it('renders an error state (not mock success) when the configured API fails', async () => {
    setMode(true, false)
    api.devices.mockRejectedValue(new Error('control plane offline'))
    api.listPlatformTasks.mockRejectedValue(new Error('control plane offline'))
    render(FleetWorkbenchView, { global: { plugins: [createPinia()] } })

    await waitFor(() => expect(screen.getByTestId('fleet-load-error').textContent).toContain('Control API 请求失败'))
    expect(screen.getByTestId('fleet-load-error').textContent).toContain('control plane offline')
    expect(screen.queryByTestId('fleet-mock-banner')).toBeNull()
    expect(screen.queryByText('device-B')).toBeNull()
    expect(screen.queryByText('oneplus-9r-main')).toBeNull()
  })

  it('shows a prominent mock banner with fixture-shaped cards in explicit dev mock mode', async () => {
    setMode(false, true)
    render(FleetWorkbenchView, { global: { plugins: [createPinia()] } })

    const banner = await screen.findByTestId('fleet-mock-banner')
    expect(banner.textContent).toContain('Mock 数据（开发模式）')
    expect(banner.textContent).toContain('不会触发真实设备')
    expect(await screen.findByText('oneplus-9r-main')).toBeTruthy()
    expect(await screen.findByText('redmi-k60-broken')).toBeTruthy()
    expect(screen.getByText(/fleet-identity\/v1@20260916\.1/)).toBeTruthy()
    expect(api.devices).not.toHaveBeenCalled()
  })

  it('loads real API data in api mode with the API/contract version line', async () => {
    setMode(true, false)
    primeApiSuccess()
    render(FleetWorkbenchView, { global: { plugins: [createPinia()] } })

    await screen.findByText('device-B')
    expect(screen.getByText(/API http:\/\/control\.test/)).toBeTruthy()
    expect(screen.getByText(new RegExp(FLEET_CONTRACT_VERSION.replace('/', '\\/')))).toBeTruthy()
    // 验收 A 的视图级复核：离线 A 卡不显示 B 的失败任务。
    const cardA = document.querySelector('[data-device-id="dev-a-offline"]') as HTMLElement
    const cardB = document.querySelector('[data-device-id="dev-b-online"]') as HTMLElement
    expect(within(cardA).queryByText(/B 设备发布第 4 步超时/)).toBeNull()
    expect(within(cardB).getByText(/B 设备发布第 4 步超时/)).toBeTruthy()
  })
})

describe('C10 acceptance C: permission gating and server-side rejection of cancel', () => {
  it('disables per-device cancel without task.create permission even when a task is running', async () => {
    setMode(true, false)
    primeApiSuccess()
    const { pinia } = primeViewerSession()
    render(FleetWorkbenchView, { global: { plugins: [pinia] } })

    const targetRow = await selectDeviceBAndExpand()
    const cancelButton = targetRow.getByRole('button', { name: '取消任务' }) as HTMLButtonElement
    expect(cancelButton.disabled).toBe(true)
    expect(cancelButton.title).toContain('task.create')
  })

  it('renders the error state per device when the server rejects the cancel (409 RECONCILE_REQUIRED)', async () => {
    setMode(true, false)
    primeApiSuccess()
    const { pinia } = primeOperatorSession()
    render(FleetWorkbenchView, { global: { plugins: [pinia] } })

    const targetRow = await selectDeviceBAndExpand()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: 'about:blank',
            title: 'Conflict',
            status: 409,
            code: 'RECONCILE_REQUIRED',
            detail: '存在未收敛 UNKNOWN 台账行，需先对账',
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    await fireEvent.click(targetRow.getByRole('button', { name: '取消任务' }))

    const errorNode = await screen.findByTestId('fleet-cancel-error')
    expect(errorNode.textContent).toContain('取消失败')
    expect(errorNode.textContent).toContain('需先对账')
    expect(screen.queryByText(/已请求取消/)).toBeNull()
  })

  it('marks the target cancelled after a successful server confirmation', async () => {
    setMode(true, false)
    primeApiSuccess()
    api.devices.mockResolvedValue([deviceAFixture(), deviceBFixture()])
    const { pinia } = primeOperatorSession()
    render(FleetWorkbenchView, { global: { plugins: [pinia] } })

    const targetRow = await selectDeviceBAndExpand()
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify(platformTaskFixture({ taskId: 'task-b-running', deviceId: DEVICE_B, state: 'CANCELLED' })), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
        .mockResolvedValue(
          new Response(
            JSON.stringify({ items: [platformTaskFixture({ taskId: 'task-b-failed', deviceId: DEVICE_B, state: 'FAILED' })] }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
    )
    await fireEvent.click(targetRow.getByRole('button', { name: '取消任务' }))

    await waitFor(() => expect(screen.getByText(/已请求取消：CANCELLED/)).toBeTruthy())
  })
})
