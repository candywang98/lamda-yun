import type { JsonObject, JsonPrimitive, OperationCatalogEntry } from '@cloudctl/api-contracts'
import type { OperationPageField, OperationPageProfile } from './operation-page-profiles'

export type OperationPageParameterValues = Record<string, string | number | boolean>

function validatedFieldValue(field: OperationPageField, value: unknown): JsonPrimitive {
  if (field.control === 'toggle') {
    if (typeof value !== 'boolean') throw new Error(`${field.label} 必须是布尔值`)
    return value
  }
  if (field.control === 'number') {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${field.label} 必须是有限数值`)
    return value
  }
  if (typeof value !== 'string') throw new Error(`${field.label} 必须是字符串`)
  if (value.length > 8_192) throw new Error(`${field.label} 超过 8192 字符限制`)
  if (field.control === 'select' && !field.options?.includes(value)) throw new Error(`${field.label} 包含未允许的选项`)
  return value
}

export function validatedPageParameters(
  profile: OperationPageProfile,
  values: OperationPageParameterValues,
): JsonObject {
  const parameters: JsonObject = {}
  for (const field of profile.fields) parameters[field.id] = validatedFieldValue(field, values[field.id])
  return parameters
}

export function buildOperationParameters(
  profile: OperationPageProfile,
  values: OperationPageParameterValues,
  catalog: Pick<OperationCatalogEntry, 'allowedParameters'>,
): JsonObject {
  if (!catalog.allowedParameters.includes('pageParameters')) {
    throw new Error('Control API 未声明 pageParameters 参数合同，已阻止提交')
  }
  return { pageParameters: validatedPageParameters(profile, values) }
}
