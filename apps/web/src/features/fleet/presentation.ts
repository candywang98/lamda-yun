import type { FleetDeviceCard } from './model'

export type FleetConnectionFilter = 'all' | 'online' | 'offline'

const heartbeatFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

export function heartbeatLabel(raw: string | null): string {
  if (!raw?.trim()) return '未上报'
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) return '时间未知（格式无效）'
  const timestamp = Date.parse(raw)
  return Number.isFinite(timestamp) ? heartbeatFormatter.format(timestamp) : '时间未知（格式无效）'
}

export function readinessOf(device: FleetDeviceCard): { label: string; tone: string } | null {
  if (!device.online) return null
  if (device.executable === true) return { label: '可执行', tone: 'tag-ok' }
  if (device.executable === false || device.blockingGates?.length) {
    return { label: '执行条件未满足', tone: 'tag-warn' }
  }
  return { label: '执行状态待上报', tone: 'tag-info' }
}

export function searchedDevices(devices: readonly FleetDeviceCard[], query: string): FleetDeviceCard[] {
  const needle = query.trim().toLocaleLowerCase('zh-CN')
  return devices.filter((device) =>
    device.name.toLocaleLowerCase('zh-CN').includes(needle) || device.deviceId.toLocaleLowerCase('zh-CN').includes(needle),
  )
}

export function visibleFleetDevices(devices: readonly FleetDeviceCard[], filter: FleetConnectionFilter): FleetDeviceCard[] {
  return devices.filter((device) => filter === 'all' || device.online === (filter === 'online'))
    .sort((left, right) => Number(right.online) - Number(left.online))
}

export function shortDeviceIds(devices: readonly FleetDeviceCard[]): Map<string, string> {
  const ids = [...new Set(devices.map((device) => device.deviceId))]
  return new Map(ids.map((id) => {
    let length = Math.min(8, id.length)
    while (length < id.length && ids.some((other) => other !== id && other.slice(0, length) === id.slice(0, length))) length++
    return [id, length < id.length ? `${id.slice(0, length)}…` : id]
  }))
}
