import { describe, expect, it } from 'vitest'
import { keepAliveHint, mapControlDevice, presenceFromLastSeen, presenceLabel, previewCaption } from '@/api/devices'

describe('Control API device mapping', () => {
  it('maps a direct Companion device without inventing Edge or health values', () => {
    const device = mapControlDevice({
      id: 'device-1',
      logical_name: 'oneplus-9r',
      edge_id: null,
      android_version: '14',
      lamda_version: null,
      target_app_versions: {},
      capabilities: { mobileDirect: true, companionVersion: '0.1.0' },
      state: 'REGISTERED',
      maintenance: false,
      version: 2,
    })

    expect(device.edge).toBe('手机直连')
    expect(device.status).toBe('UNKNOWN')
    expect(device.presence).toBe('BOUND_UNSEEN')
    expect(device.battery).toBeNull()
    expect(device.temperature).toBeNull()
    expect(device.capability).toContain('mobileDirect')
  })

  it('treats a fresh last_seen_at as online even when stored state is REGISTERED', () => {
    const device = mapControlDevice({
      id: 'device-2',
      logicalName: 'cloud-phone',
      edgeId: null,
      androidVersion: '15',
      capabilities: { mobileDirect: true, health: { batteryPercent: 88, temperatureCelsius: 33 } },
      labels: ['mobile-direct'],
      state: 'REGISTERED',
      lastSeenAt: new Date().toISOString(),
    })

    expect(device.name).toBe('cloud-phone')
    expect(device.android).toBe('15')
    expect(device.status).toBe('ONLINE')
    expect(device.presence).toBe('ONLINE')
    expect(device.battery).toBe(88)
    expect(device.temperature).toBe(33)
  })

  it('surfaces keep-alive gaps from companion heartbeat capabilities', () => {
    const device = mapControlDevice({
      id: 'device-3',
      logicalName: 'keep-alive-phone',
      lastSeenAt: new Date().toISOString(),
      capabilities: {
        mobileDirect: true,
        accessibilityEnabled: false,
        batteryOptimizationIgnored: false,
        runnerState: 'IDLE',
      },
    })
    expect(device.accessibilityEnabled).toBe(false)
    expect(device.batteryOptimizationIgnored).toBe(false)
    expect(keepAliveHint(device)).toBe('无障碍未开启，无法执行本机任务')
    expect(keepAliveHint({
      presence: 'ONLINE',
      accessibilityEnabled: true,
      batteryOptimizationIgnored: false,
    })).toBe('未忽略电池优化，国产 ROM 可能冻停心跳')
  })

  it('describes companion preview state without inventing a frame', () => {
    expect(previewCaption({
      active: false,
      waitingForFrame: false,
      hasFrame: false,
      capturedAt: null,
      accessibilityEnabled: true,
    })).toBe('尚未开始投屏')
    expect(previewCaption({
      active: true,
      waitingForFrame: true,
      hasFrame: false,
      capturedAt: null,
      accessibilityEnabled: true,
    })).toBe('已通知手机，等待 Companion 回传画面')
    expect(previewCaption({
      active: true,
      waitingForFrame: true,
      hasFrame: false,
      capturedAt: null,
      accessibilityEnabled: false,
    })).toBe('无障碍未开启，手机无法截屏回传')
  })

  it('labels presence from heartbeat age', () => {
    expect(presenceFromLastSeen(null)).toBe('BOUND_UNSEEN')
    expect(presenceFromLastSeen(new Date(Date.now() - 10_000).toISOString())).toBe('ONLINE')
    expect(presenceFromLastSeen(new Date(Date.now() - 120_000).toISOString())).toBe('OFFLINE')
    expect(presenceLabel('BOUND_UNSEEN')).toBe('已绑定未报活')
  })
})
