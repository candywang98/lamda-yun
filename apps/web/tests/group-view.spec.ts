import { fireEvent, render, screen, within, waitFor } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProductView } from '@cloudctl/api-contracts'
import ProductGroupView from '@/views/ProductGroupView.vue'
import PostGroupView from '@/views/PostGroupView.vue'
import { createProductGroup, PRODUCT_GROUPS_STORAGE_KEY, updateProductGroup } from '@/data/product-groups'
import { createPostGroup } from '@/data/post-groups'
import { emptyPost } from '@/data/post-fields'

const { products, posts } = vi.hoisted(() => ({
  products: { list: vi.fn(), save: vi.fn() }, posts: { list: vi.fn(), save: vi.fn() },
}))
vi.mock('@/api/product-catalog', () => ({ createProductCatalog: () => products }))
vi.mock('@/api/post-catalog', () => ({ createPostCatalog: () => posts }))
vi.mock('@/data/product-groups', async (original) => {
  const actual = await original<typeof import('@/data/product-groups')>()
  return { ...actual, updateProductGroup: vi.fn(actual.updateProductGroup) }
})

function product(index = 1): ProductView {
  return { id: 'p' + index, title: '商品' + index, spuCode: 'spu' + index, category: '原分组', description: '', stock: 1, price: '1', revision: 7, status: 'ACTIVE', media: [], mediaAssetIds: [], attributes: { groupName: '原分组' }, createdAt: '2026-01-01T00:00:00Z' }
}
async function openProduct(items = [product()]) {
  products.list.mockResolvedValue(items)
  render(ProductGroupView)
  await screen.findByRole('button', { name: '原分组' })
}
async function edit(name: string, next: string) {
  await fireEvent.click(screen.getByRole('button', { name: '编辑分组 ' + name }))
  const modal = screen.getByRole('dialog')
  await fireEvent.update(within(modal).getByLabelText('分组名'), next)
  return within(modal).getByRole('button', { name: '确定' })
}

describe('group view boundaries and safe updates', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    products.list.mockReset()
    products.save.mockReset()
    posts.list.mockReset()
    posts.save.mockReset()
    localStorage.clear()
  })

  it('blocks deleting a nonempty product group without saving or migrating products', async () => {
    await openProduct()
    await fireEvent.click(screen.getByRole('button', { name: '删除分组 原分组' }))
    expect(screen.getByRole('alert').textContent).toContain('请先在商品列表移组')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(products.save).not.toHaveBeenCalled()
  })

  it('keeps the local source name until all revision-checked product saves succeed and guards reentry', async () => {
    await openProduct()
    let finish!: (value: ProductView) => void
    products.save.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const confirm = await edit('原分组', '新分组')
    await fireEvent.click(confirm)
    await fireEvent.click(confirm)
    expect(products.save).toHaveBeenCalledOnce()
    expect(updateProductGroup).not.toHaveBeenCalled()
    expect(products.save.mock.calls[0]![0]).toMatchObject({ id: 'p1', expectedRevision: 7, payload: { category: '新分组' } })
    expect((within(screen.getByRole('dialog')).getByLabelText('分组名') as HTMLInputElement).disabled).toBe(true)
    await fireEvent.update(within(screen.getByRole('dialog')).getByLabelText('分组名'), '篡改草稿')
    const saved = { ...product(), category: '新分组', attributes: { groupName: '新分组' }, revision: 8 }
    products.list.mockResolvedValue([saved])
    finish(saved)
    await flushPromises()
    expect(updateProductGroup).toHaveBeenCalledOnce()
    expect(await screen.findByRole('button', { name: '新分组' })).toBeTruthy()
  })

  it('reports partial rename and reloads both source and target without committing the source local name', async () => {
    await openProduct([product(1), product(2)])
    const saved = { ...product(1), category: '新分组', attributes: { groupName: '新分组' }, revision: 8 }
    products.save.mockResolvedValueOnce(saved).mockRejectedValueOnce(new Error('revision conflict'))
    products.list.mockResolvedValue([saved, product(2)])
    await fireEvent.click(await edit('原分组', '新分组'))
    await flushPromises()
    expect(updateProductGroup).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toContain('已确认更新 1 个，未确认或未发送 1 个')
    expect(screen.getByRole('button', { name: '原分组' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '新分组' })).toBeTruthy()
    await fireEvent.click(await edit('原分组', '新分组'))
    await flushPromises()
    expect(products.save).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('alert').textContent).toContain('目标分组已存在')
  })

  it('catches inline failures and leaves persisted group names unchanged', async () => {
    await openProduct()
    products.save.mockRejectedValue(new Error('offline'))
    await fireEvent.click(screen.getByRole('button', { name: '原分组' }))
    const field = screen.getByRole('textbox', { name: '分组名' })
    await fireEvent.update(field, '新分组')
    await fireEvent.keyDown(field, { key: 'Enter' })
    await flushPromises()
    expect(screen.getByRole('alert').textContent).toContain('offline')
    expect(updateProductGroup).not.toHaveBeenCalled()
    expect(localStorage.getItem(PRODUCT_GROUPS_STORAGE_KEY)).toContain('原分组')
  })

  it('rechecks membership before deleting an empty local suggestion', async () => {
    createProductGroup({ name: '空分组' })
    products.list.mockResolvedValue([])
    render(ProductGroupView)
    await screen.findByRole('button', { name: '空分组' })
    await fireEvent.click(screen.getByRole('button', { name: '删除分组 空分组' }))
    products.list.mockResolvedValue([{ ...product(), category: '空分组', attributes: { groupName: '空分组' } }])
    await fireEvent.click(screen.getByRole('button', { name: '确定删除本地建议' }))
    await flushPromises()
    expect(screen.getByRole('alert').textContent).toContain('仍有商品')
    expect(products.save).not.toHaveBeenCalled()
  })

  it('shows load failure separately from empty data and retries', async () => {
    products.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue([])
    render(ProductGroupView)
    await screen.findByRole('button', { name: '重试加载' })
    expect(screen.queryByText(/尚无分组建议/)).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: '重试加载' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(screen.getByText('系统默认（无真实创建时间）')).toBeTruthy()
  })

  it('does not rename or migrate posts and still permits local remarks', async () => {
    createPostGroup({ name: '帖子组' })
    posts.list.mockResolvedValue([{ ...emptyPost(), id: 'post1', groupName: '帖子组' }])
    render(PostGroupView)
    await screen.findByRole('button', { name: '帖子组' })
    expect((screen.getByRole('button', { name: '帖子组' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(screen.getByRole('button', { name: '删除分组 帖子组' }))
    expect(screen.getByRole('alert').textContent).toContain('不支持云端帖子移组')
    await fireEvent.click(screen.getByRole('button', { name: '编辑分组 帖子组' }))
    await fireEvent.update(within(screen.getByRole('dialog')).getByLabelText('备注'), '仅本地备注')
    await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确定' }))
    await flushPromises()
    expect(posts.save).not.toHaveBeenCalled()
    expect(screen.getByText('仅本地备注')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('未修改云端帖子')
  })

  it('renames empty post suggestions locally without catalog writes', async () => {
    createPostGroup({ name: '空帖子组' })
    posts.list.mockResolvedValue([])
    render(PostGroupView)
    await screen.findByRole('button', { name: '空帖子组' })
    await fireEvent.click(await edit('空帖子组', '本地新建议'))
    await flushPromises()
    expect(posts.save).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '本地新建议' })).toBeTruthy()
  })
  it('surfaces local storage update failure without claiming success', async () => {
    createProductGroup({ name: '原分组' })
    await openProduct([])
    vi.mocked(updateProductGroup).mockImplementationOnce(() => { throw new Error('storage quota') })
    await fireEvent.click(await edit('原分组', '新分组'))
    await flushPromises()
    expect(screen.getByRole('alert').textContent).toContain('storage quota')
    expect(products.save).not.toHaveBeenCalled()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('clamps the current page after deleting the final filtered row', async () => {
    for (let i = 1; i <= 11; i += 1) createProductGroup({ name: '页组' + i })
    products.list.mockResolvedValue([])
    render(ProductGroupView)
    await screen.findByRole('button', { name: '筛选' })
    await flushPromises()
    await fireEvent.click(screen.getByRole('button', { name: '筛选' }))
    await fireEvent.update(screen.getByLabelText('关键字'), '页组')
    await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确定' }))
    await fireEvent.click(screen.getByRole('button', { name: '›' }))
    const deletion = screen.getByRole('button', { name: /删除分组 页组/ })
    await fireEvent.click(deletion)
    await fireEvent.click(screen.getByRole('button', { name: '确定删除本地建议' }))
    await flushPromises()
    expect(screen.getByText('共 10 条')).toBeTruthy()
    expect((screen.getByRole('textbox', { name: '跳转页码' }) as HTMLInputElement).value).toBe('1')
  })

})
