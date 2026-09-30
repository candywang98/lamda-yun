import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProductImportView from '@/views/ProductImportView.vue'
import type { ParsedImportRow } from '@/data/product-import'

const { catalog, parseFile } = vi.hoisted(() => ({
  catalog: { list: vi.fn(), save: vi.fn() }, parseFile: vi.fn(),
}))
vi.mock('@/api/product-catalog', () => ({ createProductCatalog: () => catalog }))
vi.mock('@/data/product-import', async (original) => ({ ...await original<object>(), parseImportFile: parseFile }))
vi.mock('@/data/product-groups', () => ({ DEFAULT_GROUP_NAME: '默认分组', listProductGroups: () => [{ name: '默认分组' }, { name: '测试分组' }], createProductGroup: vi.fn() }))

function row(line = 2, images = ['https://example.com/a.jpg']): ParsedImportRow {
  return { line, images, title: '商品 ' + line, price: '10', description: '描述', notes: '', costPrice: '', stock: 1, shippingFee: '', collectionLink: '', address: [] }
}
async function openImport() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: ProductImportView }, { path: '/operations/:module/:operation', component: { template: '<div />' } }] })
  await router.push('/')
  const view = render(ProductImportView, { global: { plugins: [router] } })
  await flushPromises()
  return view
}
async function chooseFile() {
  await fireEvent.change(screen.getByLabelText('商品表格文件'), { target: { files: [new File(['csv'], 'products.csv')] } })
  await flushPromises()
}
async function chooseFolder(files: File[]) {
  await fireEvent.change(screen.getByLabelText('本地图片文件夹'), { target: { files } })
  await flushPromises()
}

describe('product import confirmation workflow', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.unstubAllEnvs()
    catalog.list.mockResolvedValue([])
    catalog.save.mockResolvedValue({ id: 'saved-product' })
    parseFile.mockResolvedValue({ rows: [row()], errors: [], localImageRefs: [] })
  })

  it('parses without writes and saves only after explicit confirmation with the captured group', async () => {
    await openImport()
    await fireEvent.update(screen.getByLabelText('导入到分组'), '测试分组')
    await chooseFile()
    expect(catalog.save).not.toHaveBeenCalled()
    expect(screen.getByText(/本批次分组：测试分组/)).toBeTruthy()
    expect((screen.getByLabelText('导入到分组') as HTMLSelectElement).disabled).toBe(true)
    // Even synthetic changes cannot change the captured group.
    await fireEvent.update(screen.getByLabelText('导入到分组'), '默认分组')
    await fireEvent.click(screen.getByRole('button', { name: '确认导入 1 个商品' }))
    await flushPromises()
    expect(catalog.save.mock.calls[0]![0].payload.category).toBe('测试分组')
    expect(catalog.save.mock.calls[0]![0].payload.mediaAssetIds).toEqual([])
    expect(screen.getByRole('link', { name: '查看商品列表并核实' })).toBeTruthy()
  })

  it('requires acknowledging skipped or invalid rows', async () => {
    parseFile.mockResolvedValue({ rows: [row()], errors: ['第 3 行缺少价格', '另有 2 行未处理'], localImageRefs: [] })
    await openImport()
    await chooseFile()
    const confirm = screen.getByRole('button', { name: '确认导入 1 个商品' })
    expect((confirm as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(screen.getByRole('checkbox'))
    expect((confirm as HTMLButtonElement).disabled).toBe(false)
    expect(catalog.save).not.toHaveBeenCalled()
  })

  it('rejects missing and ambiguous local image basenames before any save', async () => {
    parseFile.mockResolvedValue({ rows: [row(2, ['a.jpg'])], errors: [], localImageRefs: ['a.jpg'] })
    await openImport()
    await chooseFile()
    await chooseFolder([new File(['x'], 'b.jpg')])
    expect(screen.getByRole('alert').textContent).toContain('缺少图片：a.jpg')
    await chooseFolder([new File(['x'], 'a.jpg'), new File(['y'], 'A.JPG')])
    expect(screen.getByRole('alert').textContent).toContain('同名图片无法唯一匹配')
    expect(catalog.save).not.toHaveBeenCalled()
  })

  it('matches local filenames without uploading or serializing image bytes', async () => {
    parseFile.mockResolvedValue({ rows: [row(2, ['photos/a.jpg'])], errors: [], localImageRefs: ['photos/a.jpg'] })
    await openImport()
    await chooseFile()
    expect((screen.getByRole('button', { name: '确认导入 1 个商品' }) as HTMLButtonElement).disabled).toBe(true)
    await chooseFolder([new File(['private-image-bytes'], 'a.jpg')])
    expect(catalog.save).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('button', { name: '确认导入 1 个商品' }))
    await flushPromises()
    const payload = catalog.save.mock.calls[0]![0].payload
    expect(payload.attributes.importedImageRefs).toEqual(['photos/a.jpg'])
    expect(payload.attributes.images).toEqual([])
    expect(payload.mediaAssetIds).toEqual([])
    expect(JSON.stringify(payload)).not.toContain('private-image-bytes')
  })

  it('continues only known unsent rows and never retries an uncertain create', async () => {
    parseFile.mockResolvedValue({ rows: [row(2), row(3), row(4)], errors: [], localImageRefs: [] })
    catalog.save.mockResolvedValueOnce({ id: 'first' }).mockRejectedValueOnce(new Error('response lost')).mockResolvedValueOnce({ id: 'third' })
    await openImport()
    await chooseFile()
    await fireEvent.click(screen.getByRole('button', { name: '确认导入 3 个商品' }))
    await flushPromises()
    expect(catalog.save).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('alert').textContent).toContain('第 3 行保存结果未确认，可能已保存')
    expect(screen.getByText(/第 2 行：已确认保存/)).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '仅继续尚未发送的 1 行' }))
    await flushPromises()
    expect(catalog.save.mock.calls.map(([input]) => input.payload.title)).toEqual(['商品 2', '商品 3', '商品 4'])
    expect(screen.getByText(/已确认保存 2 个商品；结果未确认 1 个；尚未发送 0 个/)).toBeTruthy()
  })

  it('guards against reentry and file or folder changes while saving', async () => {
    let resolve!: (value: { id: string }) => void
    catalog.save.mockReturnValue(new Promise((done) => { resolve = done }))
    await openImport()
    await chooseFile()
    const confirm = screen.getByRole('button', { name: '确认导入 1 个商品' })
    await fireEvent.click(confirm)
    await fireEvent.click(confirm)
    await chooseFile()
    expect(catalog.save).toHaveBeenCalledOnce()
    expect(parseFile).toHaveBeenCalledOnce()
    expect((screen.getByLabelText('商品表格文件') as HTMLInputElement).disabled).toBe(true)
    resolve({ id: 'saved' })
    await flushPromises()
  })

  it('shows and retries group load failure without silently falling back', async () => {
    catalog.list.mockRejectedValueOnce(new Error('offline'))
    await openImport()
    expect(screen.getByRole('alert').textContent).toContain('分组加载失败')
    await chooseFile()
    expect(parseFile).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('button', { name: '重试加载分组' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect((screen.getByRole('button', { name: '选择文件并解析' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('downloads templates relative to the configured base path', async () => {
    vi.stubEnv('BASE_URL', '/cloudctl/')
    await openImport()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(decodeURI(this.getAttribute('href')!)).toBe('/cloudctl/templates/商品导入模板.csv')
    })
    await fireEvent.click(screen.getByRole('button', { name: '下载 CSV 模板' }))
    expect(click).toHaveBeenCalledOnce()
    click.mockRestore()
  })
})
