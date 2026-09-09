import type { ProductCreate, ProductUpdate, ProductView } from '@cloudctl/api-contracts'
import { controlApiConfigured, createControlApiClient } from '@/api/control'
import { localBusinessDataAllowed, requireApiMode } from '@/api/runtime-mode'

const STORAGE_KEY = 'cloudctl.local-products'

function loadLocal(): ProductView[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ProductView[]
    return Array.isArray(parsed) ? parsed.filter((item) => item.status !== 'ARCHIVED') : []
  } catch {
    return []
  }
}

function saveLocal(products: ProductView[]) {
  if (!localBusinessDataAllowed()) {
    throw new Error('生产环境禁止将商品写入 localStorage')
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(products))
}

export function createProductCatalog() {
  const api = createControlApiClient()

  return {
    usingLocal: () => !controlApiConfigured && localBusinessDataAllowed(),
    async list(): Promise<ProductView[]> {
      if (controlApiConfigured) {
        const items = await api.products()
        return items.filter((item) => item.status !== 'ARCHIVED')
      }
      if (!localBusinessDataAllowed()) return []
      return loadLocal()
    },
    async get(productId: string): Promise<ProductView> {
      if (controlApiConfigured) {
        return api.product(productId)
      }
      if (!localBusinessDataAllowed()) throw new Error('商品不存在')
      const found = loadLocal().find((item) => item.id === productId)
      if (!found) throw new Error('商品不存在')
      return found
    },
    async save(input: { id?: string | null; payload: ProductCreate; expectedRevision?: number }): Promise<ProductView> {
      if (controlApiConfigured) {
        if (input.id) {
          const body: ProductUpdate = { ...input.payload, expectedRevision: input.expectedRevision ?? 1 }
          return api.updateProduct(input.id, body)
        }
        return api.createProduct(input.payload)
      }
      requireApiMode('保存商品')
      const now = new Date().toISOString()
      const current = loadLocal()
      if (input.id) {
        const index = current.findIndex((item) => item.id === input.id)
        if (index < 0) throw new Error('商品不存在')
        const next: ProductView = {
          ...current[index]!,
          ...input.payload,
          mediaAssetIds: input.payload.mediaAssetIds ?? [],
          media: current[index]!.media,
          revision: current[index]!.revision + 1,
          updatedAt: now,
        }
        current[index] = next
        saveLocal(current)
        return next
      }
      const created: ProductView = {
        id: crypto.randomUUID(),
        spuCode: input.payload.spuCode,
        title: input.payload.title,
        description: input.payload.description ?? '',
        category: input.payload.category,
        price: input.payload.price,
        stock: input.payload.stock,
        status: 'ACTIVE',
        revision: 1,
        mediaAssetIds: input.payload.mediaAssetIds ?? [],
        media: [],
        attributes: input.payload.attributes,
        createdAt: now,
        updatedAt: now,
      }
      saveLocal([created, ...current])
      return created
    },
    async archive(productIds: string[], reason: string): Promise<void> {
      if (controlApiConfigured) {
        await api.batchDeleteProducts({ productIds, reason })
        return
      }
      requireApiMode('归档商品')
      saveLocal(loadLocal().filter((item) => !productIds.includes(item.id)))
    },
    async duplicate(product: ProductView): Promise<ProductView> {
      return this.save({
        payload: {
          spuCode: `SPU-${Date.now()}`,
          title: `${product.title} 副本`,
          description: product.description,
          category: product.category,
          price: product.price,
          stock: product.stock,
          mediaAssetIds: product.mediaAssetIds ?? [],
          attributes: product.attributes ?? {},
        },
      })
    },
  }
}
