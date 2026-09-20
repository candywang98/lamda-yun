import type { ContentImportItemInput, ContentImportResultRow } from './api'

const PRICE_PATTERN = /^[0-9]+(\.[0-9]{1,2})?$/

export function parseImportPayload(raw: string): ContentImportItemInput[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error('导入内容不是合法 JSON')
  }
  if (!Array.isArray(parsed)) throw new Error('导入内容必须是 JSON 数组，每行一个商品')
  if (parsed.length < 1) throw new Error('至少需要一行商品数据')
  if (parsed.length > 100) throw new Error('单次最多 100 行')
  return parsed.map((row, index) => normalizeItem(row, index))
}

function normalizeItem(row: unknown, index: number): ContentImportItemInput {
  if (!row || typeof row !== 'object') throw new Error(`第 ${index + 1} 行不是对象`)
  const record = row as Record<string, unknown>
  const spuCode = text(record.spuCode)
  const title = text(record.title)
  const category = text(record.category)
  const price = text(record.price)
  const stock = record.stock
  if (!spuCode) throw new Error(`第 ${index + 1} 行缺少 spuCode`)
  if (!title) throw new Error(`第 ${index + 1} 行缺少 title`)
  if (!category) throw new Error(`第 ${index + 1} 行缺少 category`)
  if (!PRICE_PATTERN.test(price)) {
    throw new Error(`第 ${index + 1} 行 price 必须是非负两位小数格式`)
  }
  if (!Number.isInteger(stock) || (stock as number) < 0) {
    throw new Error(`第 ${index + 1} 行 stock 必须是不小于 0 的整数`)
  }
  const imageUrls = Array.isArray(record.imageUrls)
    ? record.imageUrls.filter((url): url is string => typeof url === 'string')
    : undefined
  return {
    spuCode,
    title,
    category,
    price,
    stock: stock as number,
    ...(text(record.description) ? { description: text(record.description) } : {}),
    ...(imageUrls ? { imageUrls } : {}),
    ...(text(record.groupId) ? { groupId: text(record.groupId) } : {}),
  }
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function rowStatusLabel(status: ContentImportResultRow['status']): string {
  if (status === 'IMPORT') return '将导入'
  if (status === 'SKIP_EXISTING') return '跳过（已存在）'
  return '错误'
}

export function rowStatusTone(status: ContentImportResultRow['status']): string {
  if (status === 'IMPORT') return 'SUCCEEDED'
  if (status === 'SKIP_EXISTING') return 'CANDIDATE'
  return 'BLOCKED'
}

export function rowErrorText(row: ContentImportResultRow): string {
  return row.errors.map((error) => `${error.field}: ${error.code}`).join('；')
}
