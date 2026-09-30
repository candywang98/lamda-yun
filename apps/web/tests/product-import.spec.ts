import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseCsv, parseExcelBytes, parseImportTable, splitImageRefs, toProductCreate } from '@/data/product-import'

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
  it.each(['abc', '-1', 'Infinity', '0x10'])('rejects invalid money %s instead of converting to zero', (price) => {
    const parsed = parseImportTable([['图片', '标题', '价格'], ['a.jpg', '商品', price]])
    expect(parsed.rows).toHaveLength(0)
    expect(parsed.errors[0]).toContain('第 2 行价格必须是非负有限数值')
  })

  it.each(['-1', '1.5', '9007199254740992'])('rejects invalid stock %s', (stock) => {
    const parsed = parseImportTable([['图片', '标题', '价格', '库存'], ['a.jpg', '商品', '0', stock]])
    expect(parsed.rows).toHaveLength(0)
    expect(parsed.localImageRefs).toEqual([])
  })

  it('reports the exact overflow count without claiming all rows were imported', () => {
    const parsed = parseImportTable([['图片', '标题', '价格'], ...Array.from({ length: 103 }, () => ['a.jpg', '商品', '1'])])
    expect(parsed.rows).toHaveLength(100)
    expect(parsed.errors).toEqual(['单次最多检查前 100 行商品；第 102 行起另有 3 行未处理，请拆分文件后另行导入'])
  })

  it('preserves source image references as metadata, not uploaded media assets', () => {
    const parsed = parseImportTable([['图片', '标题', '价格'], ['a.jpg;https://example.com/a.jpg', '商品', '1']])
    const payload = toProductCreate(parsed.rows[0]!, '默认分组', parsed.rows[0]!.images)
    expect(payload.attributes?.importedImageRefs).toEqual(['a.jpg', 'https://example.com/a.jpg'])
    expect(payload.attributes?.images).toEqual([])
    expect(payload.mediaAssetIds).toEqual([])
  })

  it('rejects oversized image reference metadata', () => {
    const parsed = parseImportTable([['图片', '标题', '价格'], ['x'.repeat(2049), '商品', '1']])
    expect(parsed.rows).toHaveLength(0)
    expect(parsed.errors[0]).toContain('图片引用超限')
  })

  it('keeps blank records so validation points to the original data row', () => {
    const parsed = parseImportTable(parseCsv('图片,标题,价格\n\na.jpg,商品,abc\n'))
    expect(parsed.errors[0]).toContain('第 3 行价格')
  })

})
