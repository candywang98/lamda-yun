import { createPinia } from 'pinia'
import { fireEvent, render, screen, within } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/control', () => ({
  controlApiConfigured: false,
  operationsMockEnabled: true,
  createControlApiClient: () => ({}),
}))

import OperationsView from '@/views/OperationsView.vue'

async function renderRoute(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/operations', component: { template: '<div>目录</div>' } },
      { path: '/operations/:moduleId/:operationId', component: OperationsView },
    ],
  })
  await router.push(path)
  await router.isReady()
  return render(OperationsView, { global: { plugins: [createPinia(), router] } })
}

describe('OperationsView', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('filters, selects and creates a confirmed mock run', async () => {
    await renderRoute('/operations/product-editor/product-editor-03')
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.getByLabelText('水印模板')).toBeTruthy()
    expect(screen.getByLabelText('不透明度（%）')).toBeTruthy()
    await fireEvent.click(screen.getByLabelText('选择 宝贝水印 · 01'))
    const actions = screen.getAllByRole('button', { name: '创建模拟任务' })
    await fireEvent.click(actions.at(-1)!)
    expect(screen.getByRole('dialog', { name: '批量操作确认' })).toBeTruthy()
    await fireEvent.update(screen.getByPlaceholderText('填写授权依据或业务用途，写入审计'), '授权内容维护')
    await fireEvent.update(screen.getByPlaceholderText('确认模拟范围'), '确认模拟范围')
    await fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
    expect(screen.getByText('Mock 请求已接收')).toBeTruthy()
    expect(screen.getByText(/QUEUED/)).toBeTruthy()
  })

  it('keeps prohibited collection actions visible but disabled', async () => {
    await renderRoute('/operations/collection/collection-01')
    expect(screen.getByLabelText('公开链接')).toBeTruthy()
    const blockedButtons = screen.getAllByRole('button', { name: '策略已阻断' })
    expect(blockedButtons.length).toBeGreaterThan(0)
    expect((blockedButtons[0] as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('disables unmapped operations instead of fabricating backend support', async () => {
    await renderRoute('/operations/product-editor/product-editor-02')
    expect((screen.getAllByRole('button', { name: '暂无执行适配器' })[0] as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('saves Xiaohongshu or Douyin posts without idlefish dispatch', async () => {
    await renderRoute('/operations/post-management/post-management-01')
    expect(screen.getByLabelText('帖子标题')).toBeTruthy()
    expect(screen.getByLabelText('帖子内容')).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存帖子' })).toBeTruthy()
    expect(screen.queryByLabelText('闲鱼价格')).toBeNull()
    expect(screen.queryByRole('button', { name: '下发到闲鱼填表' })).toBeNull()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('collects public post links into the local post library', async () => {
    await renderRoute('/operations/post-management/post-management-02')
    expect(screen.getByLabelText('帖子链接')).toBeTruthy()
    expect(screen.getByRole('button', { name: '开始采集' })).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    await fireEvent.update(screen.getByLabelText('帖子链接'), 'https://example.com/notes/demo-1')
    await fireEvent.click(screen.getByRole('button', { name: '开始采集' }))
    expect(await screen.findByText(/已记录 1 条链接到帖子库/)).toBeTruthy()
  })

  it('lists collected posts without competitor chrome', async () => {
    window.localStorage.setItem('cloudctl.local-posts', JSON.stringify([{
      id: 'post-demo-1',
      title: '示例笔记',
      body: 'https://example.com/notes/demo-1',
      images: [],
      videoName: '',
      videoUrl: '',
      topics: [],
      location: '',
      notes: '',
      groupName: '默认分组',
      sourceLinks: ['https://example.com/notes/demo-1'],
      createdAt: '2026-09-06T00:00:00.000Z',
      updatedAt: '2026-09-06T00:00:00.000Z',
      status: 'ACTIVE',
    }]))
    await renderRoute('/operations/post-management/post-management-03')
    expect(screen.getByText('帖子/笔记列表')).toBeTruthy()
    expect(await screen.findByText('示例笔记')).toBeTruthy()
    expect(screen.getByTitle('编辑')).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('shows post image watermark form without adapter chrome', async () => {
    await renderRoute('/operations/post-management/post-management-05')
    expect(screen.getByRole('heading', { name: '图片水印' })).toBeTruthy()
    expect(screen.getByLabelText('自定义文字')).toBeTruthy()
    expect(screen.getByLabelText('水印文字')).toBeTruthy()
    await fireEvent.click(screen.getByLabelText('图片水印'))
    expect(screen.getByText('上传logo')).toBeTruthy()
    expect(screen.getByLabelText('水印大小')).toBeTruthy()
    expect(screen.getByRole('button', { name: '预览' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存配置' })).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.queryByText('暂无执行适配器')).toBeNull()
  })

  it('retires xianyu post publish instead of showing the old form', async () => {
    await renderRoute('/operations/post-management/post-management-07')
    expect(screen.getByRole('heading', { name: '发布闲鱼' })).toBeTruthy()
    expect(screen.getByText(/闲鱼已下线帖子相关能力/)).toBeTruthy()
    expect(screen.queryByRole('heading', { name: '发布某鱼帖子' })).toBeNull()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('aligns xianyu publish goods with product list fields', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-01')
    expect(screen.getByRole('heading', { name: '发布某鱼商品' })).toBeTruthy()
    expect(screen.getByLabelText('主闲鱼')).toBeTruthy()
    expect(screen.getByLabelText('均匀分配')).toBeTruthy()
    expect(screen.getByText('智能视频')).toBeTruthy()
    expect(screen.getByRole('button', { name: '添加至待发布' })).toBeTruthy()
    expect(screen.getAllByRole('button', { name: '创建任务' }).length).toBeGreaterThan(0)
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('aligns xianyu polish form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-03')
    expect(screen.getByRole('heading', { name: '某鱼擦亮商品' })).toBeTruthy()
    expect(screen.getByLabelText('先主后副')).toBeTruthy()
    expect(screen.getByLabelText('擦亮间隔')).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('aligns xianyu bind form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-08')
    expect(screen.getByRole('heading', { name: '绑定闲鱼' })).toBeTruthy()
    expect(screen.getByLabelText('会员名')).toBeTruthy()
    expect(screen.getByText(/新设备首次使用会自动/)).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('aligns xianyu shelf down filters', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-05')
    expect(screen.getByRole('heading', { name: '闲鱼下架商品' })).toBeTruthy()
    expect(screen.getByLabelText('曝光量')).toBeTruthy()
    expect(screen.getByLabelText('关键词')).toBeTruthy()
    expect(screen.getByText(/符合条件的商品才会被下架，0表示不启用/)).toBeTruthy()
  })

  it('aligns xianyu coin register form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-09')
    expect(screen.getByRole('heading', { name: '签到鱼币' })).toBeTruthy()
    expect(screen.getByText(/想了解能做哪些任务/)).toBeTruthy()
    expect(document.getElementById('xy-jump-on')).toBeTruthy()
    expect(document.getElementById('xy-jump-off')).toBeTruthy()
  })

  it('aligns xianyu coin deduct form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-10')
    expect(screen.getByRole('heading', { name: '鱼币抵扣' })).toBeTruthy()
    expect(screen.getByLabelText('30%')).toBeTruthy()
    expect(screen.getByLabelText('未开启抵扣宝贝')).toBeTruthy()
  })

  it('aligns xianyu promote form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-11')
    expect(screen.getByRole('heading', { name: '急速卖鱼币推广' })).toBeTruthy()
    expect(screen.getByLabelText('浏览最高宝贝')).toBeTruthy()
    expect(screen.getByLabelText('特惠套餐50-75人')).toBeTruthy()
  })

  it('aligns xianyu bargain form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-12')
    expect(screen.getByRole('heading', { name: '闲鱼一键2人小刀' })).toBeTruthy()
    expect(screen.getByLabelText('操作类型')).toBeTruthy()
  })

  it('aligns xianyu price-cut form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-13')
    expect(screen.getByRole('heading', { name: '闲鱼一键降价' })).toBeTruthy()
    expect(screen.getByLabelText('比例降价')).toBeTruthy()
    expect(screen.getByLabelText('数值降价')).toBeTruthy()
  })

  it('aligns xianyu review form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-14')
    expect(screen.getByRole('heading', { name: '闲鱼一键好评' })).toBeTruthy()
    expect(screen.getByLabelText('私信内容')).toBeTruthy()
    expect(screen.getByLabelText('好评内容')).toBeTruthy()
    expect(screen.getByLabelText('我卖出的')).toBeTruthy()
  })

  it('aligns xianyu restart form without dual-app option', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-15')
    expect(screen.getByRole('heading', { name: '重启闲鱼' })).toBeTruthy()
    expect(screen.queryByLabelText('先主后副')).toBeNull()
    expect(screen.getByText(/刚刚来过/)).toBeTruthy()
  })

  it('aligns xianyu delete-feed form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-16')
    expect(screen.getByRole('heading', { name: '闲鱼删除动态' })).toBeTruthy()
    expect(screen.getByLabelText('删除间隔')).toBeTruthy()
    expect(screen.getByText(/无法删除卖出信息和交易评价信息/)).toBeTruthy()
  })

  it('aligns xianyu delete-message form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-17')
    expect(screen.getByRole('heading', { name: '闲鱼删除消息' })).toBeTruthy()
    expect(screen.getByLabelText('删除对话框')).toBeTruthy()
    expect(screen.getByLabelText('点开小红点')).toBeTruthy()
  })

  it('aligns xianyu delete-comment form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-18')
    expect(screen.getByRole('heading', { name: '闲鱼删除留言' })).toBeTruthy()
    expect(screen.getByLabelText('操作对象')).toBeTruthy()
    expect(screen.getByText(/该任务可删除闲鱼宝贝的留言/)).toBeTruthy()
  })

  it('aligns xianyu draft-up form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-19')
    expect(screen.getByRole('heading', { name: '闲鱼草稿上架' })).toBeTruthy()
    expect(screen.getByLabelText('上架间隔')).toBeTruthy()
    expect(screen.getByText(/不要跟发布商品功能混淆/)).toBeTruthy()
  })

  it('aligns xianyu reedit form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-20')
    expect(screen.getByRole('heading', { name: '编辑重发任务' })).toBeTruthy()
    expect(screen.getByLabelText('间隔')).toBeTruthy()
    expect(screen.getByLabelText('数量')).toBeTruthy()
    expect(screen.getByLabelText('地址池一')).toBeTruthy()
  })

  it('aligns xianyu wuyoumai form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-21')
    expect(screen.getByRole('heading', { name: '托管无忧卖' })).toBeTruthy()
    expect(screen.getByLabelText('全部托管')).toBeTruthy()
    expect(screen.getByLabelText('全部退出')).toBeTruthy()
  })

  it('aligns xianyu fast-reedit form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-22')
    expect(screen.getByRole('heading', { name: '快速编辑重发任务' })).toBeTruthy()
    expect(screen.getByLabelText('遍数')).toBeTruthy()
    expect(screen.getByLabelText('操作对象')).toBeTruthy()
    expect(screen.getByLabelText('间隔')).toBeTruthy()
  })

  it('aligns xianyu fast-down form', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-23')
    expect(screen.getByRole('heading', { name: '下架全部闲鱼商品' })).toBeTruthy()
    expect(screen.getByLabelText('删除间隔')).toBeTruthy()
    expect(screen.getByText(/快速下架商品会直接下架全部商品/)).toBeTruthy()
  })

  it('reuses listing collect form on xianyu task entry', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-24')
    expect(screen.getByRole('heading', { name: '宝贝信息' })).toBeTruthy()
    expect(screen.getByText(/统计分析->宝贝流量变化/)).toBeTruthy()
  })

  it('aligns xianyu device address pool', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-26')
    expect(screen.getByRole('heading', { name: '设备地址池' })).toBeTruthy()
    expect(screen.getByPlaceholderText('搜索设备名、手机品牌、会员名等')).toBeTruthy()
    expect(screen.getByText(/设备地址模式/)).toBeTruthy()
  })

  it('aligns xianyu description pool', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-27')
    expect(screen.getByRole('heading', { name: '描述池' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '添加描述池一' })).toBeTruthy()
    expect(screen.getByText(/可追加随机描述/)).toBeTruthy()
  })

  it('aligns xianyu tag pool', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-28')
    expect(screen.getByRole('heading', { name: '标签池' })).toBeTruthy()
    expect(screen.getByText('黄金首饰')).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存全部标签池' })).toBeTruthy()
  })

  it('reuses watermark form on xianyu task entry', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-29')
    expect(screen.getByRole('heading', { name: '图片水印' })).toBeTruthy()
    expect(screen.getByLabelText('自定义文字')).toBeTruthy()
    expect(screen.getByRole('button', { name: '预览' })).toBeTruthy()
  })

  it('aligns xianyu forbidden word detector', async () => {
    await renderRoute('/operations/xy-tasks/xy-tasks-30')
    expect(screen.getByRole('heading', { name: '商品违禁词检测' })).toBeTruthy()
    expect(screen.getByLabelText('请输入文案')).toBeTruthy()
    await fireEvent.update(screen.getByLabelText('请输入文案'), '全网最低加微信')
    await fireEvent.click(screen.getByRole('button', { name: '开始检测' }))
    expect(screen.getByDisplayValue(/【高危】微信/)).toBeTruthy()
    expect(screen.getByDisplayValue(/【风险】全网最低/)).toBeTruthy()
  })

  it('shows listing info collect form without competitor chrome', async () => {
    await renderRoute('/operations/analytics/analytics-01')
    expect(screen.getByRole('heading', { name: '宝贝信息' })).toBeTruthy()
    expect(screen.getByLabelText('主闲鱼')).toBeTruthy()
    expect(screen.getByLabelText('先主后副')).toBeTruthy()
    expect(screen.getByRole('button', { name: '创建任务' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存配置' })).toBeTruthy()
    expect(screen.getByText(/请勿发布相同标题的宝贝/)).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('shows xiaohongshu note publish form without competitor chrome', async () => {
    await renderRoute('/operations/post-management/post-management-08')
    expect(screen.getByRole('heading', { name: '发布红薯笔记' })).toBeTruthy()
    expect(screen.getByLabelText('红薯多开')).toBeTruthy()
    expect(screen.getByLabelText('存草稿')).toBeTruthy()
    expect(screen.getByRole('button', { name: '设置水印' })).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
  })

  it('shows product import without adapter chrome', async () => {
    await renderRoute('/operations/product-management/product-management-02')
    expect(screen.getByRole('heading', { name: 'Excel / CSV 导入商品' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '上传文件' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '下载 Excel 模板' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '下载 CSV 模板' })).toBeTruthy()
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.queryByText('暂无执行适配器')).toBeNull()
  })

  it('edits ordinary products without adapter chrome', async () => {
    await renderRoute('/operations/product-editor/product-editor-01')
    expect(screen.getByLabelText('标题')).toBeTruthy()
    expect(screen.getByLabelText('描述')).toBeTruthy()
    expect(screen.getByLabelText('价格')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: '保存编辑' }).length).toBeGreaterThan(0)
    expect(screen.queryByText('竞品页面依据')).toBeNull()
    expect(screen.queryByRole('button', { name: '下发到闲鱼填表' })).toBeNull()
    expect(screen.queryByText('暂无执行适配器')).toBeNull()
  })

  it('persists the current view and opens a local record detail dialog', async () => {
    const rendered = await renderRoute('/operations/product-editor/product-editor-03')
    await fireEvent.update(screen.getByLabelText('筛选当前功能记录'), '宝贝水印')
    await fireEvent.update(screen.getByLabelText('不透明度（%）'), '65')
    await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    const saved = JSON.parse(window.localStorage.getItem('cloudctl:operation-view:product-editor-03') ?? '{}') as { search?: string; pageParameters?: Record<string, unknown> }
    expect(saved.search).toBe('宝贝水印')
    expect(saved.pageParameters).toEqual(expect.objectContaining({ watermarkTemplate: '品牌角标', watermarkOpacity: 65, previewOnly: true }))
    expect(screen.getByRole('status').textContent).toContain('配置已保存到当前浏览器')

    rendered.unmount()
    await renderRoute('/operations/product-editor/product-editor-03')
    expect((screen.getByLabelText('筛选当前功能记录') as HTMLInputElement).value).toBe('宝贝水印')
    expect((screen.getByLabelText('不透明度（%）') as HTMLInputElement).value).toBe('65')

    await fireEvent.click(screen.getAllByRole('button', { name: '查看' })[0]!)
    const dialog = screen.getByRole('dialog', { name: '记录详情' })
    expect(within(dialog).getByText('宝贝水印 · 01')).toBeTruthy()
    expect(within(dialog).getByText(/PDF 21 · #\/set\/system\/watermark/)).toBeTruthy()
    expect(within(dialog).getByText('品牌角标')).toBeTruthy()
    await fireEvent.click(within(dialog).getByRole('button', { name: '关闭详情' }))
    expect(screen.queryByRole('dialog', { name: '记录详情' })).toBeNull()
  })

  it('downloads asset JSON and filtered record CSV exports', async () => {
    const createdUrls: string[] = []
    const revokedUrls: string[] = []
    const downloadedNames: string[] = []
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => {
      const url = `blob:operation-${createdUrls.length + 1}`
      createdUrls.push(url)
      return url
    }) })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn((url: string) => revokedUrls.push(url)) })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloadedNames.push(this.download)
    })

    await renderRoute('/operations/product-editor/product-editor-03')
    await fireEvent.click(screen.getByRole('button', { name: '导出索引' }))
    await fireEvent.click(screen.getByRole('button', { name: '导出结果' }))
    await new Promise((resolve) => window.setTimeout(resolve, 0))

    expect(downloadedNames).toEqual(['cloudctl-product-editor-03-assets.json', 'cloudctl-product-editor-03-records.csv'])
    expect(createdUrls).toHaveLength(2)
    expect(revokedUrls).toEqual(createdUrls)
    expect(screen.getByRole('status').textContent).toContain('已导出当前筛选结果')
  })
})
