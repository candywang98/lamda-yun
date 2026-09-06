import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseCsv, parseExcelBytes, parseImportTable, splitImageRefs } from '@/data/product-import'

const csvText = readFileSync(resolve(__dirname, '../public/templates/商品导入模板.csv'), 'utf8')

describe('product import parser', () => {
  it('splits multiline and spaced image cells', () => {
    expect(splitImageRefs('1.jpg\n2.jpg\n3.jpg')).toEqual(['1.jpg', '2.jpg', '3.jpg'])
    expect(splitImageRefs('image1.jpg image2.jpg')).toEqual(['image1.jpg', 'image2.jpg'])
    expect(splitImageRefs('C:\\Users\\Photos\\item.jpg')).toEqual(['C:\\Users\\Photos\\item.jpg'])
  })

  it('parses the official CSV template', () => {
    const parsed = parseImportTable(parseCsv(csvText))
    expect(parsed.errors).toEqual([])
    expect(parsed.rows).toHaveLength(2)
    expect(parsed.rows[0]).toMatchObject({
      title: '商品1标题',
      price: '99',
      address: ['山东省-济南市-长清区'],
    })
    expect(parsed.rows[0]?.images).toEqual(['1.jpg', '2.jpg', '3.jpg'])
    expect(parsed.rows[1]?.images).toEqual(['image1.jpg', 'image2.jpg'])
    expect(parsed.localImageRefs).toContain('1.jpg')
  })

  it('parses the official Excel template', async () => {
    const buffer = readFileSync(resolve(__dirname, '../public/templates/商品导入模板.xlsx'))
    const parsed = await parseExcelBytes(buffer)
    expect(parsed.rows).toHaveLength(2)
    expect(parsed.rows[0]?.title).toBe('商品1标题')
    expect(parsed.rows[0]?.images).toEqual(['1.jpg', '2.jpg', '3.jpg'])
    expect(parsed.rows[1]?.title).toBe('商品2标题')
  })
})
