import { render, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'
import FleetDeviceCardView from '@/features/fleet/FleetDeviceCardView.vue'
import { mapFleetDevice, permissionGapSummary, schedulingEligibility } from '@/features/fleet/model'
import { heartbeatLabel, readinessOf, searchedDevices, shortDeviceIds, visibleFleetDevices } from '@/features/fleet/presentation'

describe('display-v1 truthful presentation', () => {
  it('keeps omitted execution, session, account and binding data unknown and scheduling closed', () => {
    const device = mapFleetDevice({ id: 'unknown-device', logical_name: 'phone', online: true, version: 99 })
    const { container } = render(FleetDeviceCardView, { props: { device } })
    const card = within(container as HTMLElement)
    expect(card.getByText('执行状态待上报').className).toContain('tag-info')
    expect(card.queryByText(/权限缺口|无持有会话|重置权限/)).toBeNull()
    expect(schedulingEligibility(device)).toBe('ONLINE_NOT_EXECUTABLE')
    expect(device.appVersion).toBeNull()
    expect(device.bindingVersion).toBeNull()
    for (const label of ['持有会话', '绑定账号', '绑定版本（修订号）']) {
      expect(card.getByText(label).parentElement?.textContent).toContain('未上报')
    }
    expect(card.getByText('能力表（0/6 键已回传）')).toBeTruthy()
  })

  it.each([false, null])('uses failed-condition wording for reported gates with executable=%s', (executable) => {
    const device = mapFleetDevice({ id: 'gated', online: true, executable, blockingGates: ['screen-unlocked', 'engine>=min'] })
    const { container } = render(FleetDeviceCardView, { props: { device } })
    expect(within(container as HTMLElement).getByText('执行条件未满足').className).toContain('tag-warn')
    expect(container.textContent).toContain('引擎版本达标 未满足')
    expect(container.textContent).not.toContain('权限缺口')
  })

  it('does not describe explicit false as an unreported executable value', () => {
    const device = mapFleetDevice({ online: true, executable: false })
    expect(permissionGapSummary(device)).toEqual(['服务端未回传未满足条件的明细'])
    expect(readinessOf(device)?.label).toBe('执行条件未满足')
  })

  it('renders one connection badge and no readiness badge for offline records', () => {
    const device = mapFleetDevice({ id: 'offline', online: false, executable: true })
    const { container } = render(FleetDeviceCardView, { props: { device, selectable: true } })
    expect(within(container as HTMLElement).getAllByText('离线')).toHaveLength(1)
    expect(container.querySelector('.fleet-readiness')).toBeNull()
    expect((within(container as HTMLElement).getByRole('checkbox') as HTMLInputElement).disabled).toBe(true)
    expect(schedulingEligibility(device)).toBe('OFFLINE')
  })

  it.each(['companionVersion', 'companion_version'])('reads application version only from capabilities.%s', (key) => {
    const device = mapFleetDevice({ id: 'versioned', capabilities: { [key]: '0.1.0-business-acceptance.9' }, bindingVersion: 7, version: 99 })
    const { container } = render(FleetDeviceCardView, { props: { device } })
    const version = within(container as HTMLElement).getByText('应用版本').parentElement!
    expect(version.textContent).toBe('应用版本0.1.0-business-acceptance.9')
    expect(version.closest('details')).toBeNull()
    const binding = within(container as HTMLElement).getByText('绑定版本（修订号）').parentElement!
    expect(binding.textContent).toBe('绑定版本（修订号）7')
    expect(binding.closest('details')).not.toBeNull()
    expect(device.capabilityKeys).toEqual([key])
    expect(device.capabilities).toEqual([])
  })

  it.each([null, '', '   ', 99, { version: 'invented' }])('does not invent an app version from %s', (value) => {
    expect(mapFleetDevice({ capabilities: { companionVersion: value }, version: 99, bindingVersion: 7 }).appVersion).toBeNull()
  })

  it('formats the heartbeat in Shanghai time and exposes its unmodified raw value', () => {
    const raw = '2026-09-30T16:01:02Z'
    const device = mapFleetDevice({ id: 'time', last_seen_at: raw })
    const { container } = render(FleetDeviceCardView, { props: { device } })
    expect(heartbeatLabel(raw)).toBe('2026/10/01 00:01:02')
    expect(heartbeatLabel('2026-10-01T00:01:02+08:00')).toBe(heartbeatLabel(raw))
    const formatted = within(container as HTMLElement).getByText('2026/10/01 00:01:02')
    expect(formatted.getAttribute('title')).toBe(raw)
    expect(within(container as HTMLElement).getByText('Asia/Shanghai')).toBeTruthy()
    expect(within(container as HTMLElement).getByText(raw).closest('details')).not.toBeNull()
  })

  it.each([null, '', 'bad-timestamp', '2026-09-30T12:00:00', '2026-13-99T00:00:00Z'])('handles missing, invalid or timezone-ambiguous heartbeat %s', (raw) => {
    expect(heartbeatLabel(raw)).toBe(raw ? '时间未知（格式无效）' : '未上报')
  })

  it('retains the full accessible long name and ID with native collapsed diagnostics', () => {
    const device = mapFleetDevice({ id: '12345678-1234-5678-9012-123456789012', logical_name: '长名称phone'.repeat(30), online: true })
    const { container } = render(FleetDeviceCardView, { props: { device, selectable: true } })
    expect(within(container as HTMLElement).getByRole('checkbox', { name: `选择设备 ${device.name}（${device.deviceId}）` })).toBeTruthy()
    expect(within(container as HTMLElement).getByText(device.name).getAttribute('title')).toBe(device.name)
    const shortId = container.querySelector('.fleet-short-id')!
    expect(shortId.textContent).toBe('ID 12345678…')
    expect(shortId.getAttribute('title')).toBe(device.deviceId)
    const details = container.querySelector('details')!
    expect(details.open).toBe(false)
    expect(details.querySelector('summary')?.textContent).toBe('技术详情')
    expect(within(details).getByText(device.deviceId)).toBeTruthy()
  })

  it('keeps colliding names and ID prefixes distinguishable without changing source order', () => {
    const devices = [
      mapFleetDevice({ id: 'aaaaaaaa-1111', name: '同名', online: false }),
      mapFleetDevice({ id: 'aaaaaaaa-2222', name: '同名', online: true }),
      mapFleetDevice({ id: 'other-id', name: 'Other', online: true }),
      mapFleetDevice({ id: 'last-offline', name: 'Other', online: false }),
    ]
    const ids = shortDeviceIds(devices)
    expect(new Set(ids.values()).size).toBe(4)
    expect(ids.get('aaaaaaaa-1111')).not.toBe(ids.get('aaaaaaaa-2222'))
    expect(visibleFleetDevices(devices, 'all').map((device) => device.deviceId)).toEqual(['aaaaaaaa-2222', 'other-id', 'aaaaaaaa-1111', 'last-offline'])
    expect(devices[0]?.deviceId).toBe('aaaaaaaa-1111')
    expect(searchedDevices(devices, ' 同名 ')).toHaveLength(2)
    expect(searchedDevices(devices, 'AAAAaaaa-2222')).toEqual([devices[1]])
    expect(visibleFleetDevices(devices, 'offline')).toEqual([devices[0], devices[3]])
  })
})
