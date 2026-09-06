import { describe, expect, it } from 'vitest'
import {
  WATERMARK_HISTORY_LIMIT,
  emptyWatermarkConfig,
  pushWatermarkHistory,
  sanitizeWatermarkConfig,
} from '@/data/post-watermark'

describe('post watermark config', () => {
  it('clamps numeric fields and keeps image/text modes', () => {
    const config = sanitizeWatermarkConfig({
      mode: 'image',
      opacity: 180,
      sizePercent: 0,
      rotation: 400,
      fontSize: 2,
      color: 'blue',
      position: '天空',
    })
    expect(config.mode).toBe('image')
    expect(config.opacity).toBe(100)
    expect(config.sizePercent).toBe(1)
    expect(config.rotation).toBe(360)
    expect(config.fontSize).toBe(10)
    expect(config.color).toBe('#267cde')
    expect(config.position).toBe('右上')
  })

  it('keeps the newest 12 history items', () => {
    window.localStorage.clear()
    for (let index = 0; index < 14; index += 1) {
      pushWatermarkHistory(emptyWatermarkConfig({ text: `水印${index}` }), '')
    }
    const history = JSON.parse(window.localStorage.getItem('cloudctl.post-watermark.history') ?? '[]') as { config: { text: string } }[]
    expect(history).toHaveLength(WATERMARK_HISTORY_LIMIT)
    expect(history[0]?.config.text).toBe('水印13')
  })
})
