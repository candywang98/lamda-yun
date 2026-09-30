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
    routes: [{ path: '/', component: ProductManagementView }, { path: '/operations/:module/:operation', component: { template: '<div />' } }],
  })
  await router.push('/')
  const view = render(ProductManagementView, { global: { plugins: [router] } })
  if (items.length) await screen.findByText(items[0]!.title)
  else await flushPromises()
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
    await waitFor(() => expect(screen.getAllByText(/批量操作失败/).length).toBeGreaterThan(0))

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
    await waitFor(() => expect(screen.getAllByText(/批量操作失败/).length).toBeGreaterThan(0))
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
  it('finds exact normalized duplicate titles, not descriptions containing 查重', async () => {
    await openProducts([{ ...product(1), title: 'ABC 商品' }, { ...product(2), title: ' abc  商品 ' }, { ...product(3), description: '查重' }])
    await fireEvent.update(screen.getByPlaceholderText('搜索ID、标题或内容'), ' 查重 ')
    expect(screen.getByText('ABC 商品')).toBeTruthy()
    expect(screen.queryByText('商品-3')).toBeNull()
    expect(screen.getByText('共 2 条')).toBeTruthy()
  })

  it('toggles real table columns', async () => {
    await openProducts()
    await fireEvent.click(screen.getByRole('button', { name: '显示列' }))
    await fireEvent.click(screen.getByRole('checkbox', { name: '描述' }))
    expect(screen.queryByRole('columnheader', { name: '描述' })).toBeNull()
    expect(screen.queryByText('商品描述')).toBeNull()
  })

  it('previews literal replacements and retains captured targets and revisions', async () => {
    const first = { ...product(1), description: '旧文，旧文', revision: 7 }
    await openProducts([first, product(2)])
    await fireEvent.click(screen.getByRole('checkbox', { name: '选择商品 商品-1' }))
    await fireEvent.click(screen.getByRole('button', { name: '替换内容' }))
    const modal = screen.getByRole('dialog')
    expect((within(modal).getByRole('button', { name: '确定' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.update(screen.getByRole('textbox', { name: '替换原文' }), '旧文')
    await fireEvent.update(screen.getByRole('textbox', { name: '替换为' }), '新文')
    expect(screen.getByText('命中 1 个商品，共 2 处（仅替换描述）')).toBeTruthy()
    expect(screen.getByText('新文，新文')).toBeTruthy()
    expect(catalog.save).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('checkbox', { name: '选择商品 商品-2' }))
    catalog.save.mockResolvedValue({ ...first, description: '新文，新文', revision: 8 })
    await fireEvent.click(within(modal).getByRole('button', { name: '确定' }))
    await flushPromises()
    expect(catalog.save).toHaveBeenCalledOnce()
    expect(catalog.save.mock.calls[0]![0]).toMatchObject({ id: first.id, expectedRevision: 7, payload: { description: '新文，新文' } })
  })

  it.each([['库存', '-1'], ['库存', '1.5'], ['改价', 'abc'], ['改价', '']])('rejects invalid %s value %s', async (action, value) => {
    await openProducts()
    await fireEvent.click(await batchEdit(action, value))
    expect(catalog.save).not.toHaveBeenCalled()
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
  })

  it('prevents duplicate archive submissions and makes no restore promise', async () => {
    await openProducts()
    let resolve!: () => void
    catalog.archive.mockReturnValue(new Promise<void>((done) => { resolve = done }))
    await fireEvent.click(screen.getByRole('checkbox', { name: '选择本页全部商品' }))
    await fireEvent.click(screen.getByRole('button', { name: '归档' }))
    const confirm = screen.getByRole('button', { name: '确定归档' })
    await fireEvent.click(confirm)
    await fireEvent.click(confirm)
    expect(catalog.archive).toHaveBeenCalledOnce()
    expect(screen.queryByText(/保留 3 天/)).toBeNull()
    resolve()
    await flushPromises()
  })

  it('distinguishes no matches from an empty catalog', async () => {
    await openProducts()
    await fireEvent.update(screen.getByPlaceholderText('搜索ID、标题或内容'), '不存在的商品')
    expect(screen.getByText('没有符合条件的商品。')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '清除筛选' }))
    expect(screen.getByText('商品-1')).toBeTruthy()
  })

  it('offers create/import only for a genuinely empty catalog', async () => {
    await openProducts([])
    expect(screen.getByRole('link', { name: '新建商品' }).getAttribute('href')).toBe('/operations/product-editor/product-editor-01')
    expect(screen.getByRole('link', { name: '导入商品' }).getAttribute('href')).toBe('/operations/product-management/product-management-02')
  })

  it('shows a retryable load error rather than an empty catalog', async () => {
    catalog.list.mockRejectedValueOnce(new Error('offline'))
    await openProducts([])
    expect(screen.queryByRole('link', { name: '新建商品' })).toBeNull()
    catalog.list.mockResolvedValue([product(1)])
    await fireEvent.click(screen.getByRole('button', { name: '重试加载' }))
    expect(await screen.findByText('商品-1')).toBeTruthy()
  })

  it('returns focus to the action when dismissing the batch dialog with Escape', async () => {
    await openProducts()
    await fireEvent.click(screen.getByRole('checkbox', { name: '选择本页全部商品' }))
    const action = screen.getByRole('button', { name: '改价' })
    action.focus()
    await fireEvent.click(action)
    await flushPromises()
    expect(document.activeElement).toBe(screen.getByRole('textbox', { name: '改价' }))
    await fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
    await flushPromises()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(action)
  })

  it('exports only the visible textual columns in table order', async () => {
    await openProducts()
    await fireEvent.click(screen.getByRole('button', { name: '显示列' }))
    await fireEvent.click(screen.getByRole('checkbox', { name: '描述' }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      const csv = decodeURIComponent(this.href.split(',').slice(1).join(','))
      expect(csv.split('\n')[0]).not.toContain('描述')
      expect(csv.split('\n')[0]).toContain('标题')
    })
    await fireEvent.click(screen.getByRole('button', { name: '导出' }))
    expect(click).toHaveBeenCalledOnce()
    click.mockRestore()
  })

  it('reports an inverted price range instead of silently showing no matches', async () => {
    await openProducts()
    await fireEvent.update(screen.getByRole('spinbutton', { name: '最低价格' }), '200')
    await fireEvent.update(screen.getByRole('spinbutton', { name: '最高价格' }), '100')
    expect(screen.getByRole('alert').textContent).toContain('最低价格不能大于最高价格')
    expect(screen.queryByText('没有符合条件的商品。')).toBeNull()
  })

})
