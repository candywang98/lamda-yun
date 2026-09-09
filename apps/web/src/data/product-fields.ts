import type { JsonObject, JsonValue, ProductView } from '@cloudctl/api-contracts'

export interface ProductAttributes {
  titlePool: string
  rewriteText: string
  specType: string
  specValues: string[]
  images: string[]
  imageAssetIds: string[]
  imageLabels: string[]
  videoName: string
  videoUrl: string
  videoAssetId: string
  costPrice: string
  fanPrice: string
  shippingFee: string
  address: string[]
  selfPickup: boolean
  freeShipping: boolean
  theme: string[]
  brands: string[]
  collectionLink: string
  virtualProduct: string
  notes: string
  shareCode: string
  groupName: string
  orderLink: string
}

export function emptyAttributes(): ProductAttributes {
  return {
    titlePool: '',
    rewriteText: '',
    specType: '',
    specValues: [],
    images: [],
    imageAssetIds: [],
    imageLabels: [],
    videoName: '',
    videoUrl: '',
    videoAssetId: '',
    costPrice: '',
    fanPrice: '',
    shippingFee: '',
    address: [],
    selfPickup: false,
    freeShipping: false,
    theme: [],
    brands: [],
    collectionLink: '',
    virtualProduct: '',
    notes: '',
    shareCode: '',
    groupName: '',
    orderLink: '',
  }
}

function asString(value: JsonValue | undefined, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asBoolean(value: JsonValue | undefined): boolean {
  return value === true
}

function asStringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

export function parseAttributes(raw: JsonObject | undefined | null): ProductAttributes {
  const source = raw ?? {}
  const parsed = emptyAttributes()
  parsed.titlePool = asString(source.titlePool)
  parsed.rewriteText = asString(source.rewriteText)
  parsed.specType = asString(source.specType)
  parsed.specValues = asStringList(source.specValues)
  parsed.images = asStringList(source.images).concat(asStringList(source.imageUrls))
  parsed.imageAssetIds = asStringList(source.imageAssetIds)
  parsed.imageLabels = asStringList(source.imageLabels)
  parsed.videoName = asString(source.videoName)
  parsed.videoUrl = asString(source.videoUrl)
  parsed.videoAssetId = asString(source.videoAssetId)
  parsed.costPrice = asString(source.costPrice)
  parsed.fanPrice = asString(source.fanPrice)
  parsed.shippingFee = asString(source.shippingFee)
  parsed.address = asStringList(source.address)
  parsed.selfPickup = asBoolean(source.selfPickup)
  parsed.freeShipping = asBoolean(source.freeShipping)
  parsed.theme = asStringList(source.theme)
  parsed.brands = asStringList(source.brands)
  parsed.collectionLink = asString(source.collectionLink)
  parsed.virtualProduct = asString(source.virtualProduct)
  parsed.notes = asString(source.notes)
  parsed.shareCode = asString(source.shareCode)
  parsed.groupName = asString(source.groupName)
  parsed.orderLink = asString(source.orderLink)
  return parsed
}

export function attributesPayload(attributes: ProductAttributes): JsonObject {
  const { images, videoUrl, ...rest } = attributes
  return {
    ...rest,
    images: attributes.imageAssetIds,
    videoUrl: attributes.videoAssetId,
  }
}

export function productGroupName(product: ProductView): string {
  const attributes = parseAttributes(product.attributes)
  return attributes.groupName || product.category || '未分组'
}

export function productSpecLabel(product: ProductView): string {
  const attributes = parseAttributes(product.attributes)
  if (attributes.specValues.length === 0) return '无规格'
  return attributes.specValues.slice(0, 3).join(' / ')
}

export function productImages(product: ProductView): string[] {
  return parseAttributes(product.attributes).images
}

export function formatDateTime(value: string | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 19)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function normalizePrice(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return '0'
  const numeric = Number(trimmed)
  if (!Number.isFinite(numeric) || numeric < 0) return '0'
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')
}

export async function compressImageFile(file: File, maxEdge = 480): Promise<string> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(bitmap.width * scale))
  canvas.height = Math.max(1, Math.round(bitmap.height * scale))
  const context = canvas.getContext('2d')
  if (!context) {
    return await readFileAsDataUrl(file)
  }
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.72)
}

export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error ?? new Error('read file failed'))
    reader.readAsDataURL(file)
  })
}

export function downloadDataUrl(dataUrl: string, fileName: string) {
  const link = document.createElement('a')
  link.href = dataUrl
  link.download = fileName
  link.click()
}

export function clipText(value: string, max = 18): string {
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}
