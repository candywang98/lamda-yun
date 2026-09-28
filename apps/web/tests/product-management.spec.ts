import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProductView } from '@cloudctl/api-contracts'
import ProductManagementView from '@/views/ProductManagementView.vue'

const { catalog } = vi.hoisted(() => ({
  catalog: { list: vi.fn(), save: vi.fn(), duplicate: vi.fn(), archive: vi.fn() },
}))
vi.mock('@/api/product-catalog', () => ({ createProductCatalog: () => catalog }))

function product(index: number): ProductView {
  return {
    id: `product-${index}`, spuCode: `SPU-${index}`, title: `商品-${index}`, description: '商品描述',
    category: '默认分组', price: '100', stock: 1, status: 'ACTIVE', revision: 1,
    media: [], mediaAssetIds: [], attributes: { customMetadata: 'preserve-me' },
    createdAt: '2026-09-28T00:00:00Z',
  }
}

async function openProducts(items = [product(1)]) {
  catalog.list.mockResolvedValue(items)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: ProductManagementView }],
  })
  await router.push('/')
  const view = render(ProductManagementView, { global: { plugins: [router] } })
  await screen.findByText(items[0]!.title)
  return view
}

async function batchEdit(action: string, value: string) {
  await fireEvent.click(screen.getAllByRole('checkbox')[0]!)
  await fireEvent.click(screen.getByRole('button', { name: action }))
  const modal = document.querySelector('.mask .modal') as HTMLElement
  await fireEvent.update(within(modal).getByRole('textbox'), value)
  return within(modal).getByRole('button', { name: '确定' })
}

describe('product management regressions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    catalog.save.mockReset()
    localStorage.clear()
  })

  it('resets pagination when a live filter reduces the result set', async () => {
    await openProducts(Array.from({ length: 12 }, (_, index) => product(index + 1)))
    await fireEvent.click(screen.getByRole('button', { name: '2' }))
    await screen.findByText('商品-11')
    await fireEvent.update(screen.getByPlaceholderText('搜索ID、标题或内容'), '商品-2')

    expect(screen.getByText('商品-2')).toBeTruthy()
    expect(screen.queryByText(/还没有商品/)).toBeNull()
  })

  it('does not change visible data when a batch save is rejected', async () => {
    const original = product(1)
    await openProducts([original])
    catalog.save.mockRejectedValue(new Error('Revision conflict'))
    await fireEvent.click(await batchEdit('插入标题', '新-'))
    await screen.findByText(/批量操作失败/)

    expect(screen.getByText('商品-1')).toBeTruthy()
    expect(original.title).toBe('商品-1')
    expect(screen.queryByText('新-商品-1')).toBeNull()
  })

  it('retries only unfinished products after a partially successful batch', async () => {
    await openProducts([product(1), product(2)])
    catalog.save.mockResolvedValueOnce({ ...product(1), title: '新-商品-1', revision: 2 })
      .mockRejectedValueOnce(new Error('temporarily unavailable'))
      .mockResolvedValueOnce({ ...product(2), title: '新-商品-2', revision: 2 })
    const confirm = await batchEdit('插入标题', '新-')
    await fireEvent.click(confirm)
    await screen.findByText(/批量操作失败/)
    await fireEvent.click(confirm)
    await flushPromises()

    expect(catalog.save.mock.calls.map(([input]) => input.id)).toEqual(['product-1', 'product-2', 'product-2'])
    expect(catalog.save.mock.calls[2]![0].payload.title).toBe('新-商品-2')
  })

  it('preserves unrelated product metadata in a batch update', async () => {
    await openProducts()
    catalog.save.mockResolvedValue({ ...product(1), price: '200', revision: 2 })
    await fireEvent.click(await batchEdit('改价', '200'))
    await waitFor(() => expect(catalog.save).toHaveBeenCalledOnce())

    expect(catalog.save.mock.calls[0]![0].payload.attributes.customMetadata).toBe('preserve-me')
  })

  it('prevents a second batch submission while the first is pending', async () => {
    await openProducts()
    let resolve!: (value: ProductView) => void
    catalog.save.mockReturnValue(new Promise<ProductView>((done) => { resolve = done }))
    const confirm = await batchEdit('改价', '200')
    await fireEvent.click(confirm)
    await fireEvent.click(confirm)
    expect(catalog.save).toHaveBeenCalledOnce()
    expect((confirm as HTMLButtonElement).disabled).toBe(true)
    resolve({ ...product(1), price: '200', revision: 2 })
    await flushPromises()
  })
})
