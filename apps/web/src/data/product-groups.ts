import type { ProductView } from '@cloudctl/api-contracts'
import { parseAttributes, productGroupName } from '@/data/product-fields'

export const PRODUCT_GROUPS_STORAGE_KEY = 'cloudctl.local-product-groups'
export const DEFAULT_GROUP_NAME = '默认分组'

export interface ProductGroup {
  id: string
  name: string
  remark: string
  createdAt: string
  system?: boolean
}

export const DEFAULT_PRODUCT_GROUP: ProductGroup = {
  id: '380160',
  name: DEFAULT_GROUP_NAME,
  remark: '系统建立的分组',
  createdAt: '2026-01-12T20:24:37.000Z',
  system: true,
}

function loadStored(): ProductGroup[] {
  try {
    const raw = localStorage.getItem(PRODUCT_GROUPS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ProductGroup[]
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item) => item && typeof item.id === 'string' && typeof item.name === 'string')
  } catch {
    return []
  }
}

function saveStored(groups: ProductGroup[]) {
  localStorage.setItem(PRODUCT_GROUPS_STORAGE_KEY, JSON.stringify(groups))
}

function numericId(existing: Set<string>): string {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const id = String(100000 + Math.floor(Math.random() * 900000))
    if (!existing.has(id)) return id
  }
  return String(Date.now()).slice(-6)
}

export function sortProductGroups(groups: ProductGroup[]): ProductGroup[] {
  return [...groups].sort((left, right) => right.createdAt.localeCompare(left.createdAt) || right.id.localeCompare(left.id))
}

export function mergeProductGroups(stored: ProductGroup[], products: ProductView[]): ProductGroup[] {
  const byName = new Map<string, ProductGroup>()
  byName.set(DEFAULT_GROUP_NAME, { ...DEFAULT_PRODUCT_GROUP })
  for (const group of stored) {
    const name = group.name.trim() || DEFAULT_GROUP_NAME
    const current = byName.get(name)
    if (!current || (!current.system && group.system)) {
      byName.set(name, { ...group, name })
    }
  }
  const usedIds = new Set([...byName.values()].map((item) => item.id))
  for (const product of products) {
    const name = productGroupName(product)
    if (byName.has(name)) continue
    const createdAt = product.createdAt || product.updatedAt || new Date().toISOString()
    const id = numericId(usedIds)
    usedIds.add(id)
    byName.set(name, {
      id,
      name,
      remark: name === DEFAULT_GROUP_NAME ? DEFAULT_PRODUCT_GROUP.remark : '',
      createdAt,
    })
  }
  return sortProductGroups([...byName.values()])
}

export function resolveProductGroups(products: ProductView[] = []): ProductGroup[] {
  return mergeProductGroups(loadStored(), products)
}

export function listProductGroups(products: ProductView[] = []): ProductGroup[] {
  const groups = resolveProductGroups(products)
  saveStored(groups)
  return groups
}

export function createProductGroup(input: { name: string; remark?: string }, products: ProductView[] = []): ProductGroup {
  const name = input.name.trim()
  if (!name) throw new Error('请填写分组名')
  const groups = listProductGroups(products)
  if (groups.some((item) => item.name === name)) throw new Error('分组名已存在')
  const created: ProductGroup = {
    id: numericId(new Set(groups.map((item) => item.id))),
    name,
    remark: input.remark?.trim() ?? '',
    createdAt: new Date().toISOString(),
  }
  saveStored(sortProductGroups([created, ...groups]))
  return created
}

export function updateProductGroup(id: string, patch: { name?: string; remark?: string }, products: ProductView[] = []): ProductGroup {
  const groups = listProductGroups(products)
  const index = groups.findIndex((item) => item.id === id)
  if (index < 0) throw new Error('分组不存在')
  const current = groups[index]!
  const name = patch.name === undefined ? current.name : patch.name.trim()
  if (!name) throw new Error('请填写分组名')
  if (groups.some((item) => item.id !== id && item.name === name)) throw new Error('分组名已存在')
  const next: ProductGroup = {
    ...current,
    name,
    remark: patch.remark === undefined ? current.remark : patch.remark.trim(),
  }
  groups[index] = next
  saveStored(sortProductGroups(groups))
  return next
}

export function deleteProductGroup(id: string, products: ProductView[] = []): ProductGroup[] {
  const groups = listProductGroups(products)
  const current = groups.find((item) => item.id === id)
  if (!current) throw new Error('分组不存在')
  if (current.system || current.name === DEFAULT_GROUP_NAME) throw new Error('系统分组不能删除')
  const next = groups.filter((item) => item.id !== id)
  saveStored(next)
  return next
}

export function productsUsingGroup(products: ProductView[], name: string): ProductView[] {
  return products.filter((item) => productGroupName(item) === name)
}

export function replaceProductGroupName(product: ProductView, from: string, to: string): ProductView | null {
  const attributes = parseAttributes(product.attributes)
  const current = productGroupName(product)
  if (current !== from) return null
  return {
    ...product,
    category: product.category === from ? to : product.category,
    attributes: { ...product.attributes, ...attributes, groupName: to },
  }
}
