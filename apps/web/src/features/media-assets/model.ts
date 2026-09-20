import type {
  MediaPoolFreezeInput,
  PreflightCheck,
  PublishPreflightInput,
  WatermarkRenderInput,
} from './api'

export function normalizedWatermarkInput(input: WatermarkRenderInput): WatermarkRenderInput {
  const text = input.text.trim()
  if (!text) throw new Error('水印文字不能为空')
  if (!Number.isInteger(input.fontSize) || input.fontSize < 8 || input.fontSize > 256) {
    throw new Error('文字大小必须为 8 到 256 的整数')
  }
  if (!Number.isInteger(input.opacity) || input.opacity < 1 || input.opacity > 100) {
    throw new Error('透明度必须为 1 到 100 的整数')
  }
  if (!Number.isInteger(input.margin) || input.margin < 0 || input.margin > 2048) {
    throw new Error('边距必须为 0 到 2048 的整数')
  }
  return {
    text,
    position: input.position,
    opacity: input.opacity,
    fontSize: input.fontSize,
    margin: input.margin,
    ...(input.ruleVersionId?.trim() ? { ruleVersionId: input.ruleVersionId.trim() } : {}),
  }
}

export function normalizedPoolInput(input: MediaPoolFreezeInput): MediaPoolFreezeInput {
  const taskKey = input.taskKey.trim()
  const groupId = input.groupId.trim()
  if (!taskKey || !groupId) throw new Error('任务键和素材分组不能为空')
  if (!Number.isInteger(input.count) || input.count < 1 || input.count > 49) {
    throw new Error('冻结数量必须为 1 到 49 的整数')
  }
  return {
    taskKey,
    groupId,
    count: input.count,
    ...(input.seed?.trim() ? { seed: input.seed.trim() } : {}),
  }
}

export function normalizedPreflightInput(input: PublishPreflightInput): PublishPreflightInput {
  const productId = input.productId.trim()
  const accountId = input.accountId.trim()
  const deviceId = input.deviceId.trim()
  if (!productId || !accountId || !deviceId) {
    throw new Error('商品、账号和设备 ID 都不能为空')
  }
  return { ...input, productId, accountId, deviceId }
}

export function preflightCounts(checks: PreflightCheck[]) {
  return checks.reduce(
    (counts, check) => ({ ...counts, [check.status]: counts[check.status] + 1 }),
    { PASS: 0, WARNING: 0, BLOCKED: 0 },
  )
}
