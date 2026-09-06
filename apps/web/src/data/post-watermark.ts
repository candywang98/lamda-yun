export const WATERMARK_CONFIG_KEY = 'cloudctl.post-watermark.config'
export const WATERMARK_HISTORY_KEY = 'cloudctl.post-watermark.history'
export const WATERMARK_HISTORY_LIMIT = 12
export const WATERMARK_PREVIEW_WIDTH = 960
export const WATERMARK_PREVIEW_HEIGHT = 540

export const watermarkModes = [
  { id: 'custom-text', label: '自定义文字' },
  { id: 'member-name', label: '某鱼会员名' },
  { id: 'nickname', label: '某鱼昵称' },
  { id: 'image', label: '图片水印' },
] as const

export type WatermarkMode = (typeof watermarkModes)[number]['id']
export type WatermarkPosition = '右上' | '右下' | '左上' | '左下' | '居中'
export type WatermarkApplyTo = '全部' | '首张' | '尾张'

export interface WatermarkConfig {
  mode: WatermarkMode
  text: string
  imageDataUrl: string
  sizePercent: number
  opacity: number
  position: WatermarkPosition
  marginX: number
  marginY: number
  tile: boolean
  rotation: number
  applyTo: WatermarkApplyTo
  fontFamily: string
  fontSize: number
  color: string
  shadow: number
}

export interface WatermarkHistoryItem {
  id: string
  savedAt: string
  thumbnail: string
  config: WatermarkConfig
}

export const watermarkFonts = [
  { id: 'simhei', label: 'simhei黑体.ttf', css: 'SimHei, "Heiti SC", "PingFang SC", "Microsoft YaHei", sans-serif' },
  { id: 'simsun', label: 'simsun宋体.ttf', css: 'SimSun, Songti SC, serif' },
  { id: 'msyh', label: 'msyh微软雅黑.ttf', css: '"Microsoft YaHei", "PingFang SC", sans-serif' },
  { id: 'arial', label: 'arial.ttf', css: 'Arial, Helvetica, sans-serif' },
]

export const watermarkPositions: WatermarkPosition[] = ['右上', '右下', '左上', '左下', '居中']
export const watermarkApplyOptions: WatermarkApplyTo[] = ['全部', '首张', '尾张']

export function emptyWatermarkConfig(partial: Partial<WatermarkConfig> = {}): WatermarkConfig {
  return {
    mode: 'custom-text',
    text: '水印文字',
    imageDataUrl: '',
    sizePercent: 30,
    opacity: 90,
    position: '右上',
    marginX: 20,
    marginY: 20,
    tile: false,
    rotation: 45,
    applyTo: '全部',
    fontFamily: 'simhei',
    fontSize: 50,
    color: '#267cde',
    shadow: 0,
    ...partial,
  }
}

export function clamp(value: number, min: number, max: number, fallback: number): number {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.min(max, Math.max(min, number))
}

export function sanitizeWatermarkConfig(raw: unknown): WatermarkConfig {
  const value = (raw ?? {}) as Partial<WatermarkConfig>
  const mode = watermarkModes.some((item) => item.id === value.mode) ? value.mode! : 'custom-text'
  return emptyWatermarkConfig({
    mode,
    text: typeof value.text === 'string' && value.text.trim() ? value.text : '水印文字',
    imageDataUrl: typeof value.imageDataUrl === 'string' ? value.imageDataUrl : '',
    sizePercent: clamp(Number(value.sizePercent), 1, 100, 30),
    opacity: clamp(Number(value.opacity), 1, 100, 90),
    position: watermarkPositions.includes(value.position as WatermarkPosition) ? value.position as WatermarkPosition : '右上',
    marginX: clamp(Number(value.marginX), 0, 400, 20),
    marginY: clamp(Number(value.marginY), 0, 400, 20),
    tile: Boolean(value.tile),
    rotation: clamp(Number(value.rotation), 0, 360, 45),
    applyTo: watermarkApplyOptions.includes(value.applyTo as WatermarkApplyTo) ? value.applyTo as WatermarkApplyTo : '全部',
    fontFamily: watermarkFonts.some((item) => item.id === value.fontFamily) ? value.fontFamily! : 'simhei',
    fontSize: clamp(Number(value.fontSize), 10, 100, 50),
    color: typeof value.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(value.color) ? value.color : '#267cde',
    shadow: clamp(Number(value.shadow), 0, 100, 0),
  })
}

export function loadWatermarkConfig(): WatermarkConfig {
  try {
    return sanitizeWatermarkConfig(JSON.parse(localStorage.getItem(WATERMARK_CONFIG_KEY) ?? 'null'))
  } catch {
    return emptyWatermarkConfig()
  }
}

export function saveWatermarkConfig(config: WatermarkConfig): WatermarkConfig {
  const next = sanitizeWatermarkConfig(config)
  localStorage.setItem(WATERMARK_CONFIG_KEY, JSON.stringify(next))
  return next
}

export function loadWatermarkHistory(): WatermarkHistoryItem[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(WATERMARK_HISTORY_KEY) ?? '[]') as WatermarkHistoryItem[]
    if (!Array.isArray(parsed)) return []
    return parsed.slice(0, WATERMARK_HISTORY_LIMIT).map((item) => ({
      id: String(item.id ?? crypto.randomUUID()),
      savedAt: String(item.savedAt ?? new Date().toISOString()),
      thumbnail: String(item.thumbnail ?? ''),
      config: sanitizeWatermarkConfig(item.config),
    }))
  } catch {
    return []
  }
}

export function pushWatermarkHistory(config: WatermarkConfig, thumbnail: string): WatermarkHistoryItem[] {
  const item: WatermarkHistoryItem = {
    id: crypto.randomUUID(),
    savedAt: new Date().toISOString(),
    thumbnail,
    config: sanitizeWatermarkConfig(config),
  }
  const next = [item, ...loadWatermarkHistory()].slice(0, WATERMARK_HISTORY_LIMIT)
  localStorage.setItem(WATERMARK_HISTORY_KEY, JSON.stringify(next))
  return next
}

export function resolvedWatermarkText(config: WatermarkConfig, bound?: { memberName?: string; nickname?: string }): string {
  if (config.mode === 'member-name') return bound?.memberName?.trim() || config.text || '水印文字'
  if (config.mode === 'nickname') return bound?.nickname?.trim() || config.text || '水印文字'
  return config.text || '水印文字'
}

export function fontCss(fontFamily: string): string {
  return watermarkFonts.find((item) => item.id === fontFamily)?.css ?? watermarkFonts[0].css
}

function stampPosition(width: number, height: number, stampWidth: number, stampHeight: number, config: WatermarkConfig): { x: number; y: number } {
  const maxX = Math.max(0, width - stampWidth)
  const maxY = Math.max(0, height - stampHeight)
  if (config.position === '左上') return { x: Math.min(config.marginX, maxX), y: Math.min(config.marginY, maxY) }
  if (config.position === '左下') return { x: Math.min(config.marginX, maxX), y: Math.max(0, height - stampHeight - config.marginY) }
  if (config.position === '右下') return { x: Math.max(0, width - stampWidth - config.marginX), y: Math.max(0, height - stampHeight - config.marginY) }
  if (config.position === '居中') return { x: Math.max(0, (width - stampWidth) / 2), y: Math.max(0, (height - stampHeight) / 2) }
  return { x: Math.max(0, width - stampWidth - config.marginX), y: Math.min(config.marginY, maxY) }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('水印图片无法读取'))
    image.src = src
  })
}

async function createStamp(config: WatermarkConfig): Promise<HTMLCanvasElement> {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('当前浏览器无法预览水印')
  if (config.mode === 'image') {
    if (!config.imageDataUrl) throw new Error('请先上传水印 logo')
    const image = await loadImage(config.imageDataUrl)
    const height = Math.max(8, Math.round(WATERMARK_PREVIEW_HEIGHT * (config.sizePercent / 100)))
    const width = Math.max(8, Math.round(image.width * (height / Math.max(1, image.height))))
    canvas.width = width
    canvas.height = height
    ctx.drawImage(image, 0, 0, width, height)
    return canvas
  }
  const text = resolvedWatermarkText(config)
  const fontSize = Math.round(config.fontSize * (96 / 72))
  ctx.font = `${fontSize}px ${fontCss(config.fontFamily)}`
  const metrics = ctx.measureText(text)
  const padding = Math.ceil(fontSize * 0.35)
  canvas.width = Math.ceil(metrics.width) + padding * 2
  canvas.height = Math.ceil(fontSize * 1.4) + padding
  ctx.font = `${fontSize}px ${fontCss(config.fontFamily)}`
  ctx.fillStyle = config.color
  ctx.textBaseline = 'middle'
  if (config.shadow > 0) {
    ctx.shadowColor = 'rgba(15, 23, 42, 0.55)'
    ctx.shadowBlur = Math.round(config.shadow / 4)
    ctx.shadowOffsetX = Math.round(config.shadow / 20)
    ctx.shadowOffsetY = Math.round(config.shadow / 20)
  }
  ctx.fillText(text, padding, canvas.height / 2)
  return canvas
}

export async function renderWatermarkPreview(config: WatermarkConfig): Promise<string> {
  const canvas = document.createElement('canvas')
  canvas.width = WATERMARK_PREVIEW_WIDTH
  canvas.height = WATERMARK_PREVIEW_HEIGHT
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('当前浏览器无法预览水印')
  const background = ctx.createLinearGradient(0, 0, WATERMARK_PREVIEW_WIDTH, WATERMARK_PREVIEW_HEIGHT)
  background.addColorStop(0, '#d7e3ee')
  background.addColorStop(1, '#f4f7fb')
  ctx.fillStyle = background
  ctx.fillRect(0, 0, WATERMARK_PREVIEW_WIDTH, WATERMARK_PREVIEW_HEIGHT)
  ctx.fillStyle = '#64748b'
  ctx.font = '20px sans-serif'
  ctx.fillText('预览图片 960×540', 28, 36)

  const stamp = await createStamp(config)
  ctx.globalAlpha = config.opacity / 100
  const origin = stampPosition(WATERMARK_PREVIEW_WIDTH, WATERMARK_PREVIEW_HEIGHT, stamp.width, stamp.height, config)
  const gapX = stamp.width + 48
  const gapY = stamp.height + 48
  const startX = config.tile ? -stamp.width : origin.x
  const startY = config.tile ? -stamp.height : origin.y
  const endX = config.tile ? WATERMARK_PREVIEW_WIDTH + stamp.width : origin.x
  const endY = config.tile ? WATERMARK_PREVIEW_HEIGHT + stamp.height : origin.y
  for (let y = startY; y <= endY; y += gapY) {
    for (let x = startX; x <= endX; x += gapX) {
      ctx.save()
      ctx.translate(x + stamp.width / 2, y + stamp.height / 2)
      ctx.rotate((config.rotation * Math.PI) / 180)
      ctx.drawImage(stamp, -stamp.width / 2, -stamp.height / 2)
      ctx.restore()
      if (!config.tile) break
    }
    if (!config.tile) break
  }
  return canvas.toDataURL('image/png')
}

export async function renderWatermarkThumbnail(config: WatermarkConfig): Promise<string> {
  try {
    return await renderWatermarkPreview(config)
  } catch {
    return ''
  }
}
