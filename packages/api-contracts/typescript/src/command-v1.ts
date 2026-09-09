export const COMMAND_V1_PROTOCOL = 'cloudctl.command/v1' as const

export const COMMAND_V1_TYPES = [
  'xianyu.publish_listing.v1',
  'xianyu.collect_orders.v1',
  'xiaohongshu.publish_note.v1',
  'device.probe_capabilities.v1',
] as const

export type CommandV1Type = (typeof COMMAND_V1_TYPES)[number]

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const SHA = /^[a-f0-9]{64}$/
const PACKAGE = /^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$/
const PRICE = /^[0-9]+(\.[0-9]{1,2})?$/
const FORBIDDEN = ['shell', 'dex', 'js', 'javascript', 'frida', 'argv', 'payload', 'script', 'bytecode']
const PACKAGES: Record<CommandV1Type, string | null> = {
  'xianyu.publish_listing.v1': 'com.taobao.idlefish',
  'xianyu.collect_orders.v1': 'com.taobao.idlefish',
  'xiaohongshu.publish_note.v1': 'com.xingin.xhs',
  'device.probe_capabilities.v1': null,
}

export interface CommandV1 {
  protocolVersion: typeof COMMAND_V1_PROTOCOL
  taskId: string
  attemptId: string
  commandType: CommandV1Type
  deviceId: string
  accountId: string
  bindingVersion: number
  snapshot: { id: string; sha256: string }
  recipe: { versionId: string; sha256: string; engineMinVersion: number }
  targetPackage: string
  requiredCapabilities: Array<'accessibility' | 'mediaProjection' | 'network' | 'foregroundService'>
  lease: { controlEpoch: number; expiresAt: string }
  mediaDeliveryId?: string
  legacyStepsEnabled?: boolean
  parameters: Record<string, unknown>
}

function fail(message: string): never {
  throw new Error(message)
}

function requireId(value: unknown, field: string): string {
  if (typeof value !== 'string' || !ID.test(value)) fail(`${field} is invalid`)
  return value
}

function rejectForbidden(value: unknown): void {
  if (Array.isArray(value)) {
    value.forEach(rejectForbidden)
    return
  }
  if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const lowered = key.toLowerCase()
      if (FORBIDDEN.some((fragment) => lowered.includes(fragment))) {
        fail('command contains unauthorized execution fields')
      }
      rejectForbidden(item)
    }
  }
}

const ALLOWED_KEYS = new Set([
  'protocolVersion',
  'taskId',
  'attemptId',
  'commandType',
  'deviceId',
  'accountId',
  'bindingVersion',
  'snapshot',
  'recipe',
  'targetPackage',
  'requiredCapabilities',
  'lease',
  'mediaDeliveryId',
  'legacyStepsEnabled',
  'parameters',
])

export function parseCommandV1(payload: unknown): CommandV1 {
  if (!payload || typeof payload !== 'object') fail('command must be an object')
  rejectForbidden(payload)
  const raw = payload as Record<string, unknown>
  for (const key of Object.keys(raw)) {
    if (!ALLOWED_KEYS.has(key)) fail('Unknown command field')
  }
  if (raw.protocolVersion !== COMMAND_V1_PROTOCOL) fail('UNSUPPORTED_PROTOCOL')
  if (!COMMAND_V1_TYPES.includes(raw.commandType as CommandV1Type)) fail('UNSUPPORTED_PROTOCOL')
  const commandType = raw.commandType as CommandV1Type
  const targetPackage = typeof raw.targetPackage === 'string' ? raw.targetPackage : fail('targetPackage is invalid')
  if (!PACKAGE.test(targetPackage)) fail('targetPackage is invalid')
  const expected = PACKAGES[commandType]
  if (expected && targetPackage !== expected) fail('targetPackage does not match commandType')
  const snapshot = raw.snapshot as Record<string, unknown> | undefined
  const recipe = raw.recipe as Record<string, unknown> | undefined
  const lease = raw.lease as Record<string, unknown> | undefined
  if (!snapshot || !recipe || !lease) fail('command refs are required')
  const command: CommandV1 = {
    protocolVersion: COMMAND_V1_PROTOCOL,
    taskId: requireId(raw.taskId, 'taskId'),
    attemptId: requireId(raw.attemptId, 'attemptId'),
    commandType,
    deviceId: requireId(raw.deviceId, 'deviceId'),
    accountId: requireId(raw.accountId, 'accountId'),
    bindingVersion: typeof raw.bindingVersion === 'number' && raw.bindingVersion >= 1 ? raw.bindingVersion : fail('bindingVersion is invalid'),
    snapshot: {
      id: requireId(snapshot.id, 'snapshot.id'),
      sha256: typeof snapshot.sha256 === 'string' && SHA.test(snapshot.sha256) ? snapshot.sha256 : fail('snapshot.sha256 is invalid'),
    },
    recipe: {
      versionId: requireId(recipe.versionId, 'recipe.versionId'),
      sha256: typeof recipe.sha256 === 'string' && SHA.test(recipe.sha256) ? recipe.sha256 : fail('recipe.sha256 is invalid'),
      engineMinVersion:
        typeof recipe.engineMinVersion === 'number' && recipe.engineMinVersion >= 1
          ? recipe.engineMinVersion
          : fail('recipe.engineMinVersion is invalid'),
    },
    targetPackage,
    requiredCapabilities: Array.isArray(raw.requiredCapabilities)
      ? (raw.requiredCapabilities as CommandV1['requiredCapabilities'])
      : fail('requiredCapabilities is invalid'),
    lease: {
      controlEpoch: typeof lease.controlEpoch === 'number' && lease.controlEpoch >= 1 ? lease.controlEpoch : fail('lease.controlEpoch is invalid'),
      expiresAt: typeof lease.expiresAt === 'string' ? lease.expiresAt : fail('lease.expiresAt is invalid'),
    },
    ...(raw.mediaDeliveryId === undefined
      ? {}
      : { mediaDeliveryId: requireId(raw.mediaDeliveryId, 'mediaDeliveryId') }),
    ...(raw.legacyStepsEnabled === undefined ? {} : { legacyStepsEnabled: raw.legacyStepsEnabled === true }),
    parameters: raw.parameters && typeof raw.parameters === 'object' ? (raw.parameters as Record<string, unknown>) : fail('parameters are required'),
  }
  if (commandType === 'xianyu.publish_listing.v1') {
    const listingBody = command.parameters.listingBody
    const price = command.parameters.price
    if (typeof listingBody !== 'string' || !listingBody.trim()) fail('listingBody is required')
    if (typeof price !== 'string' || !PRICE.test(price)) fail('price is invalid')
  }
  return command
}
