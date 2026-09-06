import { describe, expect, it, beforeEach } from 'vitest'
import { createProductGroup, DEFAULT_GROUP_NAME, deleteProductGroup, listProductGroups, mergeProductGroups, updateProductGroup } from '@/data/product-groups'
import type { ProductView } from '@cloudctl/api-contracts'

function product(partial: Partial<ProductView> = {}): ProductView {
  return {
    id: 'p1',
    spuCode: 'SPU-1',
    title: '南京黄金回收服务',
    description: '描述',
    category: '黄金回收',
    price: '1',
    stock: 1,
    status: 'ACTIVE',
    revision: 1,
    mediaAssetIds: [],
    media: [],
    attributes: { groupName: '黄金回收' },
    createdAt: '2026-08-20T12:33:23.000Z',
    ...partial,
  }
}

describe('product groups', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('always keeps the system default group and infers groups from products', () => {
    const groups = mergeProductGroups([], [product()])
    expect(groups.map((item) => item.name)).toEqual(['黄金回收', DEFAULT_GROUP_NAME])
    expect(groups.find((item) => item.name === DEFAULT_GROUP_NAME)?.remark).toBe('系统建立的分组')
  })

  it('creates, updates and refuses deleting the default group', () => {
    createProductGroup({ name: '黄金回收', remark: '程序制作商品' })
    const created = listProductGroups()
    expect(created.some((item) => item.name === '黄金回收' && item.remark === '程序制作商品')).toBe(true)
    const gold = created.find((item) => item.name === '黄金回收')!
    updateProductGroup(gold.id, { remark: '回收类目' })
    expect(listProductGroups().find((item) => item.id === gold.id)?.remark).toBe('回收类目')
    const fallback = listProductGroups().find((item) => item.name === DEFAULT_GROUP_NAME)!
    expect(() => deleteProductGroup(fallback.id)).toThrow('系统分组不能删除')
  })
})
