import { CloudCtlApiError, type ProductCreate, type ProductUpdate, type ProductView } from '@cloudctl/api-contracts'
import { controlApiConfigured, createControlApiClient } from '@/api/control'

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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(products))
}

function isMissingApi(error: unknown): boolean {
  return error instanceof CloudCtlApiError && (error.status === 404 || error.status === 501)
}

export function createProductCatalog() {
  const api = createControlApiClient()
  let usingLocal = !controlApiConfigured

  return {
    usingLocal: () => usingLocal,
    async list(): Promise<ProductView[]> {
      if (!controlApiConfigured) {
        usingLocal = true
        return loadLocal()
      }
      try {
        const items = await api.products()
        usingLocal = false
        return items.filter((item) => item.status !== 'ARCHIVED')
      } catch (error) {
        if (!isMissingApi(error)) throw error
        usingLocal = true
        return loadLocal()
      }
    },
    async get(productId: string): Promise<ProductView> {
      if (!usingLocal && controlApiConfigured) {
        try {
          return await api.product(productId)
        } catch (error) {
          if (!isMissingApi(error)) throw error
          usingLocal = true
        }
      }
      const found = loadLocal().find((item) => item.id === productId)
      if (!found) throw new Error('商品不存在')
      return found
    },
    async save(input: { id?: string | null; payload: ProductCreate; expectedRevision?: number }): Promise<ProductView> {
      if (!usingLocal && controlApiConfigured) {
        try {
          if (input.id) {
            const body: ProductUpdate = { ...input.payload, expectedRevision: input.expectedRevision ?? 1 }
            return await api.updateProduct(input.id, body)
          }
          return await api.createProduct(input.payload)
        } catch (error) {
          if (!isMissingApi(error)) throw error
          usingLocal = true
        }
      }
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
      if (!usingLocal && controlApiConfigured) {
        try {
          await api.batchDeleteProducts({ productIds, reason })
          return
        } catch (error) {
          if (!isMissingApi(error)) {
            for (const productId of productIds) {
              await api.archiveProduct(productId, { reason })
            }
            return
          }
          usingLocal = true
        }
      }
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
          mediaAssetIds: [],
          attributes: product.attributes ?? {},
        },
      })
    },
  }
}
