import { describe, expect, it } from 'vitest'
import fieldMap from '../../../docs/phase1/field-map.json'
import { findOperation, operationModules, phase1SharedServices } from '@/data/operations-catalog'

const XY_TITLES = [
  '发布商品', '发布帖子', '擦亮商品', '上架商品', '下架商品', '删除商品', '删除帖子', '绑定闲鱼',
  '签到鱼币', '鱼币抵扣', '鱼币推广', '一键小刀', '一键降价', '一键好评', '重启闲鱼', '删除动态',
  '删除消息', '删除留言', '草稿上架', '编辑重发', '托管无忧卖', '快速编辑重发', '快速下架商品',
  '采集宝贝信息', '通用地址池', '设备地址池', '描述池', '标签池', '图片水印', '违禁词检测', '视频操作教程',
] as const

describe('T004 field map and 31 xianyu titles', () => {
  it('keeps original xy-tasks operation ids for all 31 titles', () => {
    const xy = operationModules.find((module) => module.id === 'xy-tasks')
    expect(xy?.titles).toEqual([...XY_TITLES])
    expect(xy?.operations).toHaveLength(31)
    xy?.operations.forEach((operation, index) => {
      expect(operation.id).toBe(`xy-tasks-${String(index + 1).padStart(2, '0')}`)
      expect(operation.title).toBe(XY_TITLES[index])
      expect(findOperation('xy-tasks', operation.id)?.id).toBe(operation.id)
    })
  })

  it('maps every phase-1 xianyu title or records AVAILABILITY_PENDING', () => {
    expect(fieldMap.operations).toHaveLength(31)
    const ids = fieldMap.operations.map((item) => item.id)
    expect(ids).toEqual(XY_TITLES.map((_, index) => `xy-tasks-${String(index + 1).padStart(2, '0')}`))
    expect(fieldMap.operations.every((item) => item.status === 'mapped' || item.status === 'AVAILABILITY_PENDING')).toBe(true)
    expect(fieldMap.operations.filter((item) => item.status === 'AVAILABILITY_PENDING').map((item) => item.id)).toEqual([
      'xy-tasks-02',
      'xy-tasks-07',
    ])
  })

  it('reuses shared pool/watermark/collect services instead of duplicate stores', () => {
    expect(phase1SharedServices).toEqual(fieldMap.sharedServices)
    expect(phase1SharedServices.addressPool).toContain('xy-tasks-25')
    expect(phase1SharedServices.addressPool).toContain('product-editor-04')
    expect(phase1SharedServices.watermark).toContain('xy-tasks-29')
    expect(phase1SharedServices.listingCollect).toEqual(['analytics-01', 'xy-tasks-24'])
  })
})
