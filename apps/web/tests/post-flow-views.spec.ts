import { flushPromises } from '@vue/test-utils'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PostCollectView from '@/views/PostCollectView.vue'
import PostPublishView from '@/views/PostPublishView.vue'
import { emptyPost } from '@/data/post-fields'
import { configStorageKey, emptyPublishConfig } from '@/data/post-publish'

const mocks = vi.hoisted(() => ({ configured: true, list: vi.fn(), save: vi.fn(), devices: vi.fn(), task: vi.fn(), download: vi.fn() }))
vi.mock('@/data/product-fields', async (original) => ({ ...await original<typeof import('@/data/product-fields')>(), downloadDataUrl: mocks.download }))
vi.mock('@/api/post-catalog', () => ({ createPostCatalog: () => ({ list: mocks.list, save: mocks.save }) }))
vi.mock('@/api/control', () => ({ get controlApiConfigured() { return mocks.configured }, createControlApiClient: () => ({ createPlatformTask: mocks.task, devices: mocks.devices }) }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
async function mountCollect() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/operations/post-management/post-management-02')
  const result = render(PostCollectView, { global: { plugins: [router] } })
  await flushPromises()
  await waitFor(() => expect(screen.queryByText('正在读取帖子分组…')).toBeNull())
  return result
}
async function mountPublish(platform: 'xianyu' | 'xiaohongshu' = 'xiaohongshu') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/operations/post-management/post-management-08')
  render(PostPublishView, { props: { platform }, global: { plugins: [router], stubs: { MediaThumb: true } } })
  await flushPromises()
  await waitFor(() => expect(screen.queryByText('正在读取设备与帖子…')).toBeNull())
}
beforeEach(() => {
  vi.clearAllMocks()
  mocks.configured = true
  localStorage.clear()
  mocks.list.mockReset().mockResolvedValue([])
  mocks.save.mockReset().mockImplementation(async ({ post }) => post)
  mocks.devices.mockReset().mockResolvedValue([{ id: 'd1', logical_name: '计划设备', last_seen_at: new Date().toISOString() }])
})

describe('link recording boundaries', () => {
  it('validates every nonempty line before writing and explains actual behavior', async () => {
    await mountCollect()
    expect(screen.getByRole('heading', { name: '帖子链接记录 / 导入' })).toBeTruthy()
    expect(screen.getByText(/不会抓取小红书或其他网站的正文、图片/)).toBeTruthy()
    expect(screen.queryByText('图片MD5处理')).toBeNull()
    expect((screen.getByLabelText('帖子分组') as HTMLSelectElement).disabled).toBe(true)
    await fireEvent.update(screen.getByLabelText('帖子链接'), 'https://example.test/a\nnot-a-link\nhttps://example.test/b')
    await fireEvent.click(screen.getByRole('button', { name: '记录链接' }))
    expect(screen.getByRole('alert').textContent).toContain('第 2 行')
    expect(mocks.save).not.toHaveBeenCalled()
  })
  it('deduplicates server records that retain only body, plus duplicates in the batch', async () => {
    mocks.list.mockResolvedValue([emptyPost({ body: 'https://example.test/a', sourceLinks: [] })])
    await mountCollect()
    await fireEvent.update(screen.getByLabelText('帖子链接'), 'https://example.test/a\nhttps://example.test/b\nhttps://example.test/b')
    await fireEvent.click(screen.getByRole('button', { name: '记录链接' }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('已记录 1 条链接，跳过 2 条'))
    expect(mocks.save).toHaveBeenCalledTimes(1)
    expect(mocks.save.mock.calls[0]![0].post.notes).toBe('')
  })
  it('freezes input and dedupe across awaits, guards double submission, and never replays successful or uncertain entries', async () => {
    await mountCollect()
    const read = deferred<ReturnType<typeof emptyPost>[]>()
    mocks.list.mockReturnValueOnce(read.promise)
    mocks.save.mockResolvedValueOnce(emptyPost()).mockRejectedValueOnce(new Error('connection lost'))
    await fireEvent.update(screen.getByLabelText('帖子链接'), 'https://example.test/a\nhttps://example.test/b\nhttps://example.test/c')
    await fireEvent.click(screen.getByRole('button', { name: '记录链接' }))
    await fireEvent.click(screen.getByRole('button', { name: '正在记录…' }))
    await fireEvent.update(screen.getByLabelText('帖子链接'), 'https://example.test/replaced')
    await fireEvent.click(screen.getByLabelText('允许重复记录'))
    read.resolve([])
    await waitFor(() => expect(screen.getByText(/记录中断：已确认保存 1 条/)).toBeTruthy())
    expect(mocks.save.mock.calls.map(([input]) => input.post.body)).toEqual(['https://example.test/a', 'https://example.test/b'])
    expect((screen.getByLabelText('帖子链接') as HTMLTextAreaElement).value).toBe('https://example.test/c')
    expect(screen.getByText('1 条保存结果待核实')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '记录链接' }))
    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(3))
    expect(mocks.save.mock.calls[2]![0].post.body).toBe('https://example.test/c')
  })
  it('keeps the submitted dedupe choice while the existing library is loading', async () => {
    await mountCollect()
    const read = deferred<ReturnType<typeof emptyPost>[]>()
    mocks.list.mockReturnValueOnce(read.promise)
    await fireEvent.update(screen.getByLabelText('帖子链接'), 'https://example.test/a')
    await fireEvent.click(screen.getByRole('button', { name: '记录链接' }))
    await fireEvent.click(screen.getByLabelText('允许重复记录'))
    read.resolve([emptyPost({ body: 'https://example.test/a' })])
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('已记录 0 条链接，跳过 1 条'))
    expect(mocks.save).not.toHaveBeenCalled()
  })
  it('shows read errors and offers an actual retry without writing', async () => {
    mocks.list.mockRejectedValueOnce(new Error('permission denied'))
    await mountCollect()
    expect(screen.getByRole('alert').textContent).toContain('permission denied')
    await fireEvent.click(screen.getByRole('button', { name: '重试读取分组' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(mocks.list).toHaveBeenCalledTimes(2)
    expect(mocks.save).not.toHaveBeenCalled()
  })
})

describe('browser-only post allocation plans', () => {
  it('previews and saves a browser snapshot without creating a platform task or media processing', async () => {
    mocks.list.mockResolvedValue([emptyPost({ id: 'p1', title: '测试笔记' })])
    localStorage.setItem(configStorageKey('xiaohongshu'), JSON.stringify(emptyPublishConfig({ postIds: ['p1'], deviceIds: ['d1'], autoVideo: true, watermark: true })))
    await mountPublish()
    expect(screen.queryByRole('button', { name: '创建任务' })).toBeNull()
    expect(screen.queryByLabelText('一键成片')).toBeNull()
    expect(screen.getByText('分配预览 · 1 条计划记录')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '保存浏览器计划' }))
    expect(screen.getByRole('status').textContent).toContain('未创建任务，未下发到手机，未发布内容')
    const saved = JSON.parse(localStorage.getItem(configStorageKey('xiaohongshu'))!)
    expect(saved).toMatchObject({ postIds: ['p1'], deviceIds: ['d1'], autoVideo: false, watermark: false })
    await fireEvent.click(screen.getByRole('button', { name: '清空' }))
    expect(JSON.parse(localStorage.getItem(configStorageKey('xiaohongshu'))!).postIds).toEqual(['p1'])
    expect(mocks.task).not.toHaveBeenCalled()
    expect(mocks.save).not.toHaveBeenCalled()
  })
  it('neutralizes spreadsheet formulas when exporting a plan content list', async () => {
    mocks.list.mockResolvedValue([emptyPost({ title: '  =SUM(1)', body: '+payload', groupName: '@group' })])
    await mountPublish()
    await fireEvent.click(screen.getByRole('button', { name: '导出' }))
    const csv = decodeURIComponent(mocks.download.mock.calls[0]![0])
    for (const value of ['  =SUM(1)', '+payload', '@group']) expect(csv).toContain('"' + "'" + value + '"')
  })
  it('excludes video posts from restored plans and from selection', async () => {
    mocks.list.mockResolvedValue([emptyPost({ id: 'v1', title: '视频条目', videoAssetId: 'video-asset' })])
    localStorage.setItem(configStorageKey('xiaohongshu'), JSON.stringify(emptyPublishConfig({ postIds: ['v1'], deviceIds: ['d1'] })))
    await mountPublish()
    expect(screen.getByText('分配预览 · 0 条计划记录')).toBeTruthy()
    expect((screen.getByRole('button', { name: '加入或移出计划' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(screen.getByRole('button', { name: '保存浏览器计划' }))
    expect(screen.getByRole('alert').textContent).toContain('请先选择计划设备和笔记')
    expect(mocks.task).not.toHaveBeenCalled()
  })
  it('reports local storage errors without claiming the plan was saved', async () => {
    mocks.list.mockResolvedValue([emptyPost({ id: 'p1', title: '测试笔记' })])
    localStorage.setItem(configStorageKey('xiaohongshu'), JSON.stringify(emptyPublishConfig({ postIds: ['p1'], deviceIds: ['d1'] })))
    await mountPublish()
    const setItem = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('storage full') })
    try {
      await fireEvent.click(screen.getByRole('button', { name: '保存浏览器计划' }))
      expect(screen.getByRole('alert').textContent).toContain('storage full')
      expect(screen.queryByRole('status')).toBeNull()
      expect(mocks.task).not.toHaveBeenCalled()
    } finally { setItem.mockRestore() }
  })
  it('handles read failure/retry and cannot save an unloaded plan', async () => {
    mocks.list.mockRejectedValueOnce(new Error('posts unavailable'))
    await mountPublish()
    expect(screen.getByRole('alert').textContent).toContain('posts unavailable')
    expect((screen.getByRole('button', { name: '保存浏览器计划' }) as HTMLButtonElement).disabled).toBe(true)
    await fireEvent.click(screen.getByRole('button', { name: '重试读取' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(await screen.findByText('没有符合条件的内容。可先编辑帖子或调整筛选。')).toBeTruthy()
    expect(mocks.task).not.toHaveBeenCalled()
  })
  it('reports rejected device reads and keeps the plan disabled', async () => {
    mocks.devices.mockRejectedValueOnce(new Error('设备读取失败'))
    await mountPublish()
    expect(screen.getByRole('alert').textContent).toContain('设备读取失败')
    expect((screen.getByRole('button', { name: '保存浏览器计划' }) as HTMLButtonElement).disabled).toBe(true)
  })
  it('does not read devices or preserve stale device selections when API is unconfigured', async () => {
    mocks.configured = false
    mocks.list.mockResolvedValue([emptyPost({ id: 'p1', title: '测试笔记' })])
    localStorage.setItem(configStorageKey('xiaohongshu'), JSON.stringify(emptyPublishConfig({ postIds: ['p1'], deviceIds: ['stale'] })))
    await mountPublish()
    expect(mocks.devices).not.toHaveBeenCalled()
    expect(screen.getByText('分配预览 · 0 条计划记录')).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '保存浏览器计划' }))
    expect(screen.getByRole('alert').textContent).toContain('请先选择计划设备和笔记')
    expect(mocks.task).not.toHaveBeenCalled()
  })
  it('clamps jumps and resets the page when search narrows results', async () => {
    mocks.list.mockResolvedValue(Array.from({ length: 12 }, (_, index) => emptyPost({ id: String(index), title: '条目' + index })))
    await mountPublish()
    await fireEvent.update(screen.getByLabelText('跳转页码'), '999')
    await fireEvent.click(screen.getByRole('button', { name: '确定' }))
    expect(screen.getByRole('button', { name: '2' })).toBeTruthy()
    await fireEvent.update(screen.getByLabelText('搜索标题、内容'), '条目0')
    await fireEvent.click(screen.getByRole('button', { name: '查找' }))
    expect(screen.getByRole('button', { name: '1' })).toBeTruthy()
    expect(screen.getByText('共 1 条')).toBeTruthy()
  })
  it('limits the unavailable notice to this CloudCtl page rather than a platform-wide claim', async () => {
    await mountPublish('xianyu')
    expect(screen.getByText('当前 CloudCtl 版本未接入闲鱼帖子发布。')).toBeTruthy()
    expect(screen.queryByText(/闲鱼已下线/)).toBeNull()
    expect((screen.getByRole('button', { name: '保存浏览器计划' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
