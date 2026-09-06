# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> operation details expose PDF source, page workflow and domain fields
- Location: e2e/smoke.spec.ts:45:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('#/set/system/watermark')
Expected: visible
Error: strict mode violation: getByText('#/set/system/watermark') resolved to 2 elements:
    1) <p>产品编辑 · #/set/system/watermark</p> aka getByText('产品编辑 · #/set/system/watermark')
    2) <code>#/set/system/watermark</code> aka getByText('#/set/system/watermark', { exact: true })

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('#/set/system/watermark')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary "运营导航" [ref=e4]:
    - strong [ref=e10]: 云控工作台
    - navigation [ref=e11]:
      - link "全部功能" [ref=e12] [cursor=pointer]:
        - /url: /operations
      - link "显示设置" [ref=e13] [cursor=pointer]:
        - /url: /operations/settings/display
      - button "系统主页 10" [ref=e18] [cursor=pointer]:
        - generic [ref=e22]: 系统主页
        - generic [ref=e23]: "10"
      - button "任务队列 1" [ref=e27] [cursor=pointer]:
        - generic [ref=e30]: 任务队列
        - generic [ref=e31]: "1"
      - generic [ref=e34]:
        - button "产品编辑 10" [ref=e35] [cursor=pointer]:
          - generic [ref=e39]: 产品编辑
          - generic [ref=e40]: "10"
        - generic [ref=e43]:
          - link "普通宝贝" [ref=e44] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-01
          - link "拍卖宝贝" [ref=e45] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-02
          - link "宝贝水印" [ref=e46] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-03
          - link "通用地址池" [ref=e47] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-04
          - link "设备地址池" [ref=e48] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-05
          - link "宝贝描述池" [ref=e49] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-06
          - link "宝贝标签池" [ref=e50] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-07
          - link "房屋出租" [ref=e51] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-08
          - link "免费送宝贝" [ref=e52] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-09
          - link "视频操作教程" [ref=e53] [cursor=pointer]:
            - /url: /operations/product-editor/product-editor-10
      - button "采集管理 14" [ref=e55] [cursor=pointer]:
        - generic [ref=e60]: 采集管理
        - generic [ref=e61]: "14"
      - button "商品管理 10" [ref=e65] [cursor=pointer]:
        - generic [ref=e70]: 商品管理
        - generic [ref=e71]: "10"
      - button "帖子管理 9" [ref=e75] [cursor=pointer]:
        - generic [ref=e79]: 帖子管理
        - generic [ref=e80]: "9"
      - button "订单管理 5" [ref=e84] [cursor=pointer]:
        - generic [ref=e88]: 订单管理
        - generic [ref=e89]: "5"
      - button "统计分析 3" [ref=e93] [cursor=pointer]:
        - generic [ref=e97]: 统计分析
        - generic [ref=e98]: "3"
      - button "闲鱼授权任务 31" [ref=e102] [cursor=pointer]:
        - generic [ref=e106]: 闲鱼授权任务
        - generic [ref=e107]: "31"
      - button "转转授权任务 9" [ref=e111] [cursor=pointer]:
        - generic [ref=e117]: 转转授权任务
        - generic [ref=e118]: "9"
      - button "小红书授权任务 4" [ref=e122] [cursor=pointer]:
        - generic [ref=e126]: 小红书授权任务
        - generic [ref=e127]: "4"
      - button "创意中心 4" [ref=e131] [cursor=pointer]:
        - generic [ref=e134]: 创意中心
        - generic [ref=e135]: "4"
      - button "聊天管理 11" [ref=e139] [cursor=pointer]:
        - generic [ref=e142]: 聊天管理
        - generic [ref=e143]: "11"
      - button "系统素材 8" [ref=e147] [cursor=pointer]:
        - generic [ref=e152]: 系统素材
        - generic [ref=e153]: "8"
      - button "个人中心 5" [ref=e157] [cursor=pointer]:
        - generic [ref=e161]: 个人中心
        - generic [ref=e162]: "5"
    - generic [ref=e165]: Control API 已连接
  - main [ref=e167]:
    - generic [ref=e168]:
      - button "打开导航" [ref=e169] [cursor=pointer]
      - button "刷新" [ref=e171] [cursor=pointer]
      - link [ref=e177] [cursor=pointer]:
        - /url: /operations/task-queue/task-queue-01
      - generic [ref=e180]: 功能配置如有疑问，请到对应教程查看。执行走授权设备与 Control API，不连接竞品服务。
    - generic "已打开页面" [ref=e181]:
      - link "全部功能" [ref=e182] [cursor=pointer]:
        - /url: /operations
      - link "显示设置" [ref=e183] [cursor=pointer]:
        - /url: /operations/settings/display
      - generic [ref=e184]:
        - link "宝贝水印" [ref=e185] [cursor=pointer]:
          - /url: /operations/product-editor/product-editor-03
        - button "关闭 宝贝水印" [ref=e186] [cursor=pointer]
    - generic [ref=e190]:
      - paragraph [ref=e191]: 宝贝水印
      - generic [ref=e192]:
        - generic [ref=e193]:
          - heading "宝贝水印" [level=2] [ref=e194]
          - paragraph [ref=e195]: "产品编辑 · #/set/system/watermark"
        - generic [ref=e196]:
          - button "重置" [ref=e197] [cursor=pointer]
          - button "保存配置" [ref=e198] [cursor=pointer]
          - button "连接后端中" [disabled] [ref=e199]
      - generic [ref=e202]:
        - link "运营目录" [ref=e203] [cursor=pointer]:
          - /url: /operations
        - generic [ref=e206]: 内容生产
        - strong [ref=e209]: 产品编辑
        - generic [ref=e210]: CONNECTING
        - combobox "切换当前模块功能" [ref=e211]:
          - option "012 · 普通宝贝"
          - option "013 · 拍卖宝贝"
          - option "014 · 宝贝水印" [selected]
          - option "015 · 通用地址池"
          - option "016 · 设备地址池"
          - option "017 · 宝贝描述池"
          - option "018 · 宝贝标签池"
          - option "019 · 房屋出租"
          - option "020 · 免费送宝贝"
          - option "021 · 视频操作教程"
      - generic [ref=e212]:
        - heading "宝贝水印" [level=3] [ref=e214]
        - generic [ref=e215]:
          - generic [ref=e216]:
            - generic [ref=e217]: 水印模板
            - combobox "水印模板" [ref=e218]:
              - option "品牌角标" [selected]
              - option "账号标识"
              - option "售后说明"
          - generic [ref=e219]:
            - generic [ref=e220]: 水印位置
            - combobox "水印位置" [ref=e221]:
              - option "右下角" [selected]
              - option "左下角"
              - option "居中"
          - generic [ref=e222]:
            - generic [ref=e223]: 不透明度（%）
            - spinbutton "不透明度（%）" [ref=e224]: "72"
          - generic [ref=e225]:
            - generic [ref=e226]: 仅生成预览
            - generic [ref=e227]:
              - checkbox "仅生成预览 已开启" [checked] [ref=e228]
              - generic [ref=e229]: 已开启
        - generic [ref=e230]:
          - button "brand-cover-01.jpg 图片 · 1080×1440 · 引用 12 次" [ref=e231] [cursor=pointer]:
            - generic [ref=e238]:
              - strong [ref=e239]: brand-cover-01.jpg
              - generic [ref=e240]: 图片 · 1080×1440 · 引用 12 次
          - button "product-demo-03.mp4 视频 · 00:24 · 引用 8 次" [ref=e241] [cursor=pointer]:
            - generic [ref=e248]:
              - strong [ref=e249]: product-demo-03.mp4
              - generic [ref=e250]: 视频 · 00:24 · 引用 8 次
          - button "service-intro.wav 音频 · 00:31 · 引用 3 次" [ref=e251] [cursor=pointer]:
            - generic [ref=e259]:
              - strong [ref=e260]: service-intro.wav
              - generic [ref=e261]: 音频 · 00:31 · 引用 3 次
          - button "authorized-address-pool 地址池 · 18 条 · revision 7" [ref=e262] [cursor=pointer]:
            - generic [ref=e266]:
              - strong [ref=e267]: authorized-address-pool
              - generic [ref=e268]: 地址池 · 18 条 · revision 7
        - button "导出索引" [ref=e270] [cursor=pointer]
        - generic [ref=e274]:
          - textbox "筛选当前功能记录" [ref=e279]:
            - /placeholder: 名称、设备、分组、负责人
          - combobox "设备筛选" [ref=e280]:
            - option "全部设备" [selected]
            - option "杭州-内容-023"
            - option "上海-内容-014"
            - option "北京-实验-008"
            - option "广州-内容-031"
          - combobox "状态筛选" [ref=e281]:
            - option "全部状态" [selected]
            - option "READY"
            - option "RUNNING"
            - option "SUCCEEDED"
            - option "PENDING_APPROVAL"
            - option "BLOCKED"
          - button "导出结果" [ref=e282] [cursor=pointer]
          - generic [ref=e286]: 0 条
        - generic [ref=e287]:
          - strong [ref=e292]: 已选择 0 项
          - button "取消选择" [ref=e293] [cursor=pointer]
          - button "连接后端中" [disabled] [ref=e294]
        - table [ref=e296]:
          - rowgroup [ref=e297]:
            - row [ref=e298]:
              - columnheader [ref=e299]:
                - checkbox "选择当前筛选全部记录" [ref=e300]
              - columnheader "对象" [ref=e301]
              - columnheader "分组" [ref=e302]
              - columnheader "设备" [ref=e303]
              - columnheader "负责人" [ref=e304]
              - columnheader "状态" [ref=e305]
              - columnheader "更新时间" [ref=e306]
              - columnheader "操作" [ref=e307]
          - rowgroup [ref=e308]:
            - row [ref=e309]:
              - cell "没有符合筛选条件的记录" [ref=e310]
      - generic [ref=e319]:
        - strong [ref=e320]: 可模拟 · 正在连接 Control API
        - paragraph [ref=e321]: Control API 不可用，页面已 fail closed；不会创建 Mock 回执或生产任务。
      - generic [ref=e322]:
        - generic [ref=e323]:
          - generic [ref=e324]:
            - heading "竞品页面依据" [level=3] [ref=e325]
            - paragraph [ref=e326]: PDF 第 21 页 · 产品编辑 › 宝贝水印
          - code [ref=e327]: "#/set/system/watermark"
        - generic [ref=e328]:
          - paragraph [ref=e329]: 选择水印规则、定位方式和预览输出，提交前只生成派生预览。
          - list "页面工作流程" [ref=e330]:
            - listitem [ref=e331]:
              - generic [ref=e332]: "1"
              - strong [ref=e333]: 选择图片
            - listitem [ref=e334]:
              - generic [ref=e335]: "2"
              - strong [ref=e336]: 套用水印模板
            - listitem [ref=e337]:
              - generic [ref=e338]: "3"
              - strong [ref=e339]: 检查不同尺寸预览
            - listitem [ref=e340]:
              - generic [ref=e341]: "4"
              - strong [ref=e342]: 保存规则版本
      - generic [ref=e343]: 页面规格 014
```

# Test source

```ts
  1   | import { expect, test } from '@playwright/test'
  2   | import { operationPath, operationsCatalog } from '../src/data/operations-catalog'
  3   | 
  4   | test('legacy CloudCtl URLs land in the single operations workspace', async ({ page }) => {
  5   |   await page.goto('/mobile-automation', { waitUntil: 'domcontentloaded' })
  6   |   await expect(page).toHaveURL(/\/operations\/system-home\/system-home-02/)
  7   |   await expect(page.locator('.yy-shell')).toBeVisible()
  8   |   await expect(page.getByText('云控工作台')).toBeVisible()
  9   |   await expect(page.locator('body')).not.toContainText('Internal Server Error')
  10  | })
  11  | 
  12  | test('root and device list URLs stay inside the operations workspace', async ({ page }) => {
  13  |   await page.goto('/', { waitUntil: 'domcontentloaded' })
  14  |   await expect(page).toHaveURL(/\/operations$/)
  15  |   await expect(page.locator('.yy-shell')).toBeVisible()
  16  | 
  17  |   await page.goto('/devices', { waitUntil: 'domcontentloaded' })
  18  |   await expect(page).toHaveURL(/\/operations\/system-home\/system-home-02/)
  19  |   await expect(page.getByText('设备列表').first()).toBeVisible()
  20  | })
  21  | 
  22  | test('operations sidebar exposes all 15 modules through scrolling', async ({ page }, testInfo) => {
  23  |   await page.goto('/operations')
  24  |   if (testInfo.project.name === 'mobile') await page.locator('.mobile-menu').click()
  25  | 
  26  |   const navigation = page.locator('.yy-nav, .nav-scroll').first()
  27  |   const moduleLinks = page.locator('.operation-module-nav')
  28  |   await expect(moduleLinks).toHaveCount(15)
  29  |   await expect(page.getByText('云控工作台')).toBeVisible()
  30  |   await expect(page.getByText('原始页面路由')).toBeVisible()
  31  | 
  32  |   const dimensions = await navigation.evaluate((element) => ({
  33  |     clientHeight: element.clientHeight,
  34  |     scrollHeight: element.scrollHeight,
  35  |     overflowY: getComputedStyle(element).overflowY,
  36  |   }))
  37  |   expect(dimensions.overflowY).toBe('auto')
  38  |   expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight)
  39  | 
  40  |   await navigation.evaluate((element) => { element.scrollTop = element.scrollHeight })
  41  |   await expect(moduleLinks.last()).toContainText('个人中心')
  42  |   await expect(moduleLinks.last()).toBeInViewport()
  43  | })
  44  | 
  45  | test('operation details expose PDF source, page workflow and domain fields', async ({ page }, testInfo) => {
  46  |   if (testInfo.project.name === 'mobile') await page.setViewportSize({ width: 390, height: 844 })
  47  |   await page.goto('/operations/product-editor/product-editor-03')
  48  |   await expect(page.getByText('竞品页面依据')).toBeVisible()
> 49  |   await expect(page.getByText('#/set/system/watermark')).toBeVisible()
      |                                                          ^ Error: expect(locator).toBeVisible() failed
  50  |   await expect(page.getByLabel('水印模板')).toBeVisible()
  51  |   await expect(page.getByLabel('不透明度（%）')).toHaveValue('72')
  52  |   await expect(page.getByRole('list', { name: '页面工作流程' })).toContainText('检查不同尺寸预览')
  53  |   await page.getByRole('button', { name: '保存配置' }).click()
  54  |   await expect(page.getByRole('status')).toContainText('配置已保存到当前浏览器')
  55  |   const assetDownload = page.waitForEvent('download')
  56  |   await page.getByRole('button', { name: '导出索引' }).click()
  57  |   await expect((await assetDownload).suggestedFilename()).toBe('cloudctl-product-editor-03-assets.json')
  58  | 
  59  |   await page.goto('/operations/collection/collection-01')
  60  |   await expect(page.getByLabel('公开链接')).toBeVisible()
  61  |   await expect(page.getByRole('button', { name: '策略已阻断' }).first()).toBeDisabled()
  62  |   const recordsDownload = page.waitForEvent('download')
  63  |   await page.getByRole('button', { name: '导出结果' }).click()
  64  |   await expect((await recordsDownload).suggestedFilename()).toBe('cloudctl-collection-01-records.csv')
  65  | })
  66  | 
  67  | test('operations catalog exposes all 134 unique pages and 111 source routes', async ({ page }) => {
  68  |   await page.goto('/operations')
  69  |   const operationLinks = page.locator('.operation-link-list a')
  70  |   await expect(operationLinks).toHaveCount(134)
  71  | 
  72  |   const paths = await operationLinks.evaluateAll((links) => links.map((link) => new URL((link as HTMLAnchorElement).href).pathname))
  73  |   expect(new Set(paths).size).toBe(134)
  74  |   expect(new Set(paths)).toEqual(new Set(operationsCatalog.map(operationPath)))
  75  | 
  76  |   const sourceRoutes = await page.locator('.operation-link-copy small').allTextContents()
  77  |   expect(sourceRoutes).toHaveLength(134)
  78  |   expect(new Set(sourceRoutes).size).toBe(111)
  79  | })
  80  | 
  81  | const operationBatches = Array.from({ length: 8 }, (_, batchIndex) => (
  82  |   operationsCatalog.filter((_, operationIndex) => operationIndex % 8 === batchIndex)
  83  | ))
  84  | 
  85  | for (const [batchIndex, operations] of operationBatches.entries()) {
  86  |   test(`operation pages batch ${batchIndex + 1} renders exact PDF metadata`, async ({ page }, testInfo) => {
  87  |     test.skip(testInfo.project.name !== 'chromium', 'The full catalog traversal runs once on desktop Chromium.')
  88  |     test.setTimeout(60_000)
  89  | 
  90  |     for (const operation of operations) {
  91  |       await page.goto(operationPath(operation), { waitUntil: 'domcontentloaded' })
  92  |       await expect(page.locator('.page-header h2')).toHaveText(operation.title)
  93  |       const sourcePanel = page.locator('.operation-source-panel')
  94  |       await expect(sourcePanel).toContainText(`PDF 第 ${operation.sourcePage} 页`)
  95  |       await expect(sourcePanel.locator('code')).toHaveText(operation.sourceRoute)
  96  |       await expect(page.locator('.operation-page-spec')).toContainText(`页面规格 ${String(operation.index).padStart(3, '0')}`)
  97  |     }
  98  |   })
  99  | }
  100 | 
  101 | test('unknown operation URLs redirect to the catalog', async ({ page }) => {
  102 |   await page.goto('/operations/not-a-module/not-an-operation')
  103 |   await expect(page).toHaveURL(/\/operations$/)
  104 |   await expect(page.locator('.page-header h2')).toHaveText('运营功能目录')
  105 | })
  106 | 
```