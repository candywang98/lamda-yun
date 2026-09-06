import type { ProductCreate } from '@cloudctl/api-contracts'
import { attributesPayload, emptyAttributes, normalizePrice } from '@/data/product-fields'

export const IMPORT_HEADERS = ['图片', '标题', '价格', '描述', '备注', '入手价', '库存', '运费', '采集链接', '地址'] as const

export interface ParsedImportRow {
  line: number
  images: string[]
  title: string
  price: string
  description: string
  notes: string
  costPrice: string
  stock: number
  shippingFee: string
  collectionLink: string
  address: string[]
}

export interface ImportParseResult {
  rows: ParsedImportRow[]
  errors: string[]
  localImageRefs: string[]
}

const HEADER_ALIASES: Record<string, (typeof IMPORT_HEADERS)[number]> = {
  图片: '图片',
  图片路径: '图片',
  标题: '标题',
  价格: '价格',
  描述: '描述',
  备注: '备注',
  入手价: '入手价',
  库存: '库存',
  运费: '运费',
  采集链接: '采集链接',
  地址: '地址',
}

export function cleanCell(value: unknown): string {
  return String(value ?? '')
    .replace(/^\uFEFF/, '')
    .replace(/^["'“”]+|["'“”]+$/g, '')
    .trim()
}

export function splitImageRefs(raw: string): string[] {
  const text = cleanCell(raw)
  if (!text) return []
  const parts = /[\n\r]/.test(text)
    ? text.split(/\r?\n/)
    : text.includes(';')
      ? text.split(';')
      : text.includes(',') && !/^[A-Za-z]:\\/.test(text)
        ? text.split(',')
        : /\s/.test(text) && !/^[A-Za-z]:\\/.test(text) && !text.startsWith('/')
          ? text.split(/\s+/)
          : [text]
  return parts.map((item) => cleanCell(item)).filter(Boolean)
}

export function isRemoteImage(ref: string): boolean {
  return /^https?:\/\//i.test(ref.trim())
}

export function imageBasename(ref: string): string {
  const cleaned = cleanCell(ref).replace(/\\/g, '/')
  const name = cleaned.split('/').at(-1) ?? cleaned
  return name.trim()
}

export function parseCsv(text: string): string[][] {
  const source = text.replace(/^\uFEFF/, '')
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]!
    const next = source[index + 1]
    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"'
        index += 1
      } else if (char === '"') {
        quoted = false
      } else {
        cell += char
      }
      continue
    }
    if (char === '"') {
      quoted = true
      continue
    }
    if (char === ',') {
      row.push(cell)
      cell = ''
      continue
    }
    if (char === '\n') {
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
      continue
    }
    if (char !== '\r') cell += char
  }
  if (quoted) throw new Error('CSV 引号未闭合')
  if (cell.length > 0 || row.length > 0) {
    row.push(cell)
    rows.push(row)
  }
  return rows.filter((item) => item.some((value) => cleanCell(value).length > 0))
}

function headerIndex(headers: string[]): Record<(typeof IMPORT_HEADERS)[number], number> {
  const map = Object.fromEntries(IMPORT_HEADERS.map((key) => [key, -1])) as Record<(typeof IMPORT_HEADERS)[number], number>
  headers.forEach((header, index) => {
    const key = HEADER_ALIASES[cleanCell(header)]
    if (key) map[key] = index
  })
  return map
}

export function parseImportTable(table: string[][]): ImportParseResult {
  const errors: string[] = []
  if (table.length < 2) {
    return { rows: [], errors: ['文件中没有商品数据'], localImageRefs: [] }
  }
  const columns = headerIndex(table[0] ?? [])
  if (columns['标题'] < 0 || columns['价格'] < 0 || columns['图片'] < 0) {
    return { rows: [], errors: ['缺少必填列：图片、标题、价格。请使用标准模板'], localImageRefs: [] }
  }
  const rows: ParsedImportRow[] = []
  const localImageRefs: string[] = []
  table.slice(1, 101).forEach((cells, index) => {
    const line = index + 2
    const read = (key: (typeof IMPORT_HEADERS)[number]) => (columns[key] >= 0 ? cleanCell(cells[columns[key]]) : '')
    const title = read('标题')
    const price = read('价格')
    const images = splitImageRefs(read('图片'))
    if (!title && !price && images.length === 0) return
    if (!title || !price || images.length === 0) {
      errors.push(`第 ${line} 行缺少必填字段（图片、标题、价格）`)
      return
    }
    images.filter((item) => !isRemoteImage(item)).forEach((item) => localImageRefs.push(item))
    const addressRaw = read('地址')
    rows.push({
      line,
      images,
      title,
      price: normalizePrice(price),
      description: read('描述'),
      notes: read('备注'),
      costPrice: read('入手价') ? normalizePrice(read('入手价')) : '',
      stock: Number(read('库存') || '0') || 0,
      shippingFee: read('运费') ? normalizePrice(read('运费')) : '',
      collectionLink: read('采集链接'),
      address: addressRaw ? [addressRaw] : [],
    })
  })
  if (table.length - 1 > 100) errors.push('单次最多导入 100 个商品，已截取前 100 行')
  return { rows, errors, localImageRefs: [...new Set(localImageRefs)] }
}

export async function decodeImportText(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const utf8 = new TextDecoder('utf-8', { fatal: false }).decode(buffer)
  if (!utf8.includes('\uFFFD')) return utf8
  try {
    return new TextDecoder('gbk' as unknown as string).decode(buffer)
  } catch {
    return utf8
  }
}

export async function parseExcelBytes(data: ArrayBuffer | Uint8Array): Promise<ImportParseResult> {
  const xlsx = await import('xlsx')
  const workbook = xlsx.read(data, { type: 'array' })
  const sheetName = workbook.SheetNames[0]
  if (!sheetName) return { rows: [], errors: ['Excel 文件没有工作表'], localImageRefs: [] }
  const table = xlsx.utils.sheet_to_json<(string | number | null)[]>(workbook.Sheets[sheetName]!, { header: 1, raw: false, blankrows: false })
  return parseImportTable(table.map((row) => (row ?? []).map((cell) => String(cell ?? ''))))
}

async function readFileBytes(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === 'function') return file.arrayBuffer()
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error ?? new Error('读取文件失败'))
    reader.readAsArrayBuffer(file)
  })
}

export async function parseImportFile(file: File): Promise<ImportParseResult> {
  const name = file.name.toLowerCase()
  if (name.endsWith('.csv')) {
    return parseImportTable(parseCsv(await decodeImportText(file)))
  }
  if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) {
    return { rows: [], errors: ['请选择 .xlsx、.xls 或 .csv 文件'], localImageRefs: [] }
  }
  return parseExcelBytes(new Uint8Array(await readFileBytes(file)))
}

export function toProductCreate(row: ParsedImportRow, groupName: string, resolvedImages: string[]): ProductCreate {
  const attributes = emptyAttributes()
  attributes.images = resolvedImages
  attributes.notes = row.notes
  attributes.costPrice = row.costPrice
  attributes.shippingFee = row.shippingFee
  attributes.collectionLink = row.collectionLink
  attributes.address = row.address
  attributes.groupName = groupName
  return {
    spuCode: `SPU-${Date.now()}-${row.line}-${Math.random().toString(36).slice(2, 8)}`,
    title: row.title,
    description: row.description,
    category: groupName || '默认分组',
    price: row.price,
    stock: row.stock,
    mediaAssetIds: [],
    attributes: attributesPayload(attributes),
  }
}
