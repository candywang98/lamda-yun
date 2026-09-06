# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> operations sidebar exposes all 15 modules through scrolling
- Location: e2e/smoke.spec.ts:22:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('原始页面路由')
Expected: visible
Error: strict mode violation: getByText('原始页面路由') resolved to 2 elements:
    1) <span>原始页面路由</span> aka getByText('原始页面路由', { exact: true })
    2) <strong>原始页面路由对照竞品登录后可见菜单</strong> aka getByText('原始页面路由对照竞品登录后可见菜单')

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('原始页面路由')

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
      - generic [ref=e17]:
        - button "系统主页 10" [ref=e18] [cursor=pointer]:
          - generic [ref=e22]: 系统主页
          - generic [ref=e23]: "10"
        - generic [ref=e26]:
          - link "产品介绍" [ref=e27] [cursor=pointer]:
            - /url: /operations/system-home/system-home-01
          - link "设备列表" [ref=e28] [cursor=pointer]:
            - /url: /operations/system-home/system-home-02
          - link "系统授权" [ref=e29] [cursor=pointer]:
            - /url: /operations/system-home/system-home-03
          - link "常见问题" [ref=e30] [cursor=pointer]:
            - /url: /operations/system-home/system-home-04
          - link "常用工具" [ref=e31] [cursor=pointer]:
            - /url: /operations/system-home/system-home-05
          - link "更新日志" [ref=e32] [cursor=pointer]:
            - /url: /operations/system-home/system-home-06
          - link "超级擦亮" [ref=e33] [cursor=pointer]:
            - /url: /operations/system-home/system-home-07
          - link "建议反馈" [ref=e34] [cursor=pointer]:
            - /url: /operations/system-home/system-home-08
          - link "公告通知" [ref=e35] [cursor=pointer]:
            - /url: /operations/system-home/system-home-09
          - link "视频教程" [ref=e36] [cursor=pointer]:
            - /url: /operations/system-home/system-home-10
      - button "任务队列 1" [ref=e38] [cursor=pointer]:
        - generic [ref=e41]: 任务队列
        - generic [ref=e42]: "1"
      - button "产品编辑 10" [ref=e46] [cursor=pointer]:
        - generic [ref=e50]: 产品编辑
        - generic [ref=e51]: "10"
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
      - paragraph [ref=e185]: 运营功能目录
      - generic [ref=e187]:
        - heading "运营功能目录" [level=2] [ref=e188]
        - paragraph [ref=e189]: 15 个业务模块、134 个菜单入口。采集 → 编辑 → 发布 → 聊天 → 订单 → 复盘；执行走授权设备与 Control API。
      - generic [ref=e190]:
        - article [ref=e191]:
          - generic [ref=e192]: 业务模块
          - strong [ref=e199]: "15"
          - text: 侧栏按竞品 15 组展开，点模块进入对应功能
        - article [ref=e200]:
          - generic [ref=e201]: 菜单入口
          - strong [ref=e207]: "134"
          - text: 一项一页，重复路由仍按独立入口收录
        - article [ref=e208]:
          - generic [ref=e209]: 原始页面路由
          - strong [ref=e215]: "111"
          - text: 来自竞品调研截图中的真实前端路由
        - article [ref=e216]:
          - generic [ref=e217]: 风险分层
          - strong [ref=e221]: "22"
          - text: 可模拟 71 · 需审批 41 · 策略阻断 22
      - generic [ref=e222]:
        - textbox "搜索运营功能" [ref=e227]:
          - /placeholder: 搜索模块、功能、原始路由或页面字段
        - generic "链路筛选" [ref=e228]:
          - button "全部链路" [ref=e229] [cursor=pointer]
          - button "资产准备" [ref=e230] [cursor=pointer]
          - button "内容生产" [ref=e231] [cursor=pointer]
          - button "分发执行" [ref=e232] [cursor=pointer]
          - button "互动交易" [ref=e233] [cursor=pointer]
          - button "数据复盘" [ref=e234] [cursor=pointer]
        - generic "风险筛选" [ref=e235]:
          - button "全部" [ref=e236] [cursor=pointer]
          - button "可模拟" [ref=e237] [cursor=pointer]
          - button "需审批" [ref=e238] [cursor=pointer]
          - button "策略阻断" [ref=e239] [cursor=pointer]
        - generic [ref=e240]: 134 / 134 项
      - generic [ref=e241]:
        - generic [ref=e242]:
          - generic [ref=e243]:
            - link [ref=e244] [cursor=pointer]:
              - /url: /operations/system-home/system-home-01
              - text: 数据复盘
              - heading "系统主页" [level=3] [ref=e245]
            - strong [ref=e246]: 10 / 10
          - generic [ref=e247]:
            - 'link "001 产品介绍 #/home/main 可模拟" [ref=e248] [cursor=pointer]':
              - /url: /operations/system-home/system-home-01
              - generic [ref=e249]: "001"
              - generic [ref=e250]:
                - text: 产品介绍
                - generic [ref=e251]: "#/home/main"
              - generic [ref=e252]: 可模拟
            - 'link "002 设备列表 #/home/device_info 可模拟" [ref=e253] [cursor=pointer]':
              - /url: /operations/system-home/system-home-02
              - generic [ref=e254]: "002"
              - generic [ref=e255]:
                - text: 设备列表
                - generic [ref=e256]: "#/home/device_info"
              - generic [ref=e257]: 可模拟
            - 'link "003 系统授权 #/home/authorize 可模拟" [ref=e258] [cursor=pointer]':
              - /url: /operations/system-home/system-home-03
              - generic [ref=e259]: "003"
              - generic [ref=e260]:
                - text: 系统授权
                - generic [ref=e261]: "#/home/authorize"
              - generic [ref=e262]: 可模拟
            - 'link "004 常见问题 #/home/issue 可模拟" [ref=e263] [cursor=pointer]':
              - /url: /operations/system-home/system-home-04
              - generic [ref=e264]: "004"
              - generic [ref=e265]:
                - text: 常见问题
                - generic [ref=e266]: "#/home/issue"
              - generic [ref=e267]: 可模拟
            - 'link "005 常用工具 #/home/tools 可模拟" [ref=e268] [cursor=pointer]':
              - /url: /operations/system-home/system-home-05
              - generic [ref=e269]: "005"
              - generic [ref=e270]:
                - text: 常用工具
                - generic [ref=e271]: "#/home/tools"
              - generic [ref=e272]: 可模拟
            - 'link "006 更新日志 #/home/upload_log 可模拟" [ref=e273] [cursor=pointer]':
              - /url: /operations/system-home/system-home-06
              - generic [ref=e274]: "006"
              - generic [ref=e275]:
                - text: 更新日志
                - generic [ref=e276]: "#/home/upload_log"
              - generic [ref=e277]: 可模拟
            - 'link "007 超级擦亮 #/home/cjcl 需审批" [ref=e278] [cursor=pointer]':
              - /url: /operations/system-home/system-home-07
              - generic [ref=e279]: "007"
              - generic [ref=e280]:
                - text: 超级擦亮
                - generic [ref=e281]: "#/home/cjcl"
              - generic [ref=e282]: 需审批
            - 'link "008 建议反馈 #/system/feedback 可模拟" [ref=e283] [cursor=pointer]':
              - /url: /operations/system-home/system-home-08
              - generic [ref=e284]: "008"
              - generic [ref=e285]:
                - text: 建议反馈
                - generic [ref=e286]: "#/system/feedback"
              - generic [ref=e287]: 可模拟
            - 'link "009 公告通知 #/app/message/index 可模拟" [ref=e288] [cursor=pointer]':
              - /url: /operations/system-home/system-home-09
              - generic [ref=e289]: "009"
              - generic [ref=e290]:
                - text: 公告通知
                - generic [ref=e291]: "#/app/message/index"
              - generic [ref=e292]: 可模拟
            - 'link "010 视频教程 #/home/v/1 可模拟" [ref=e293] [cursor=pointer]':
              - /url: /operations/system-home/system-home-10
              - generic [ref=e294]: "010"
              - generic [ref=e295]:
                - text: 视频教程
                - generic [ref=e296]: "#/home/v/1"
              - generic [ref=e297]: 可模拟
        - generic [ref=e298]:
          - generic [ref=e299]:
            - link [ref=e300] [cursor=pointer]:
              - /url: /operations/task-queue/task-queue-01
              - text: 分发执行
              - heading "任务队列" [level=3] [ref=e301]
            - strong [ref=e302]: 1 / 1
          - 'link "011 任务队列 #/task/run 可模拟" [ref=e304] [cursor=pointer]':
            - /url: /operations/task-queue/task-queue-01
            - generic [ref=e305]: "011"
            - generic [ref=e306]:
              - text: 任务队列
              - generic [ref=e307]: "#/task/run"
            - generic [ref=e308]: 可模拟
        - generic [ref=e309]:
          - generic [ref=e310]:
            - link [ref=e311] [cursor=pointer]:
              - /url: /operations/product-editor/product-editor-01
              - text: 内容生产
              - heading "产品编辑" [level=3] [ref=e312]
            - strong [ref=e313]: 10 / 10
          - generic [ref=e314]:
            - 'link "012 普通宝贝 #/goods/edit/ykj 可模拟" [ref=e315] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-01
              - generic [ref=e316]: "012"
              - generic [ref=e317]:
                - text: 普通宝贝
                - generic [ref=e318]: "#/goods/edit/ykj"
              - generic [ref=e319]: 可模拟
            - 'link "013 拍卖宝贝 #/goods/edit/pm 可模拟" [ref=e320] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-02
              - generic [ref=e321]: "013"
              - generic [ref=e322]:
                - text: 拍卖宝贝
                - generic [ref=e323]: "#/goods/edit/pm"
              - generic [ref=e324]: 可模拟
            - 'link "014 宝贝水印 #/set/system/watermark 可模拟" [ref=e325] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-03
              - generic [ref=e326]: "014"
              - generic [ref=e327]:
                - text: 宝贝水印
                - generic [ref=e328]: "#/set/system/watermark"
              - generic [ref=e329]: 可模拟
            - 'link "015 通用地址池 #/task/xy_configure/area_pool 可模拟" [ref=e330] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-04
              - generic [ref=e331]: "015"
              - generic [ref=e332]:
                - text: 通用地址池
                - generic [ref=e333]: "#/task/xy_configure/area_pool"
              - generic [ref=e334]: 可模拟
            - 'link "016 设备地址池 #/task/xy_configure/area_dev_pool 可模拟" [ref=e335] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-05
              - generic [ref=e336]: "016"
              - generic [ref=e337]:
                - text: 设备地址池
                - generic [ref=e338]: "#/task/xy_configure/area_dev_pool"
              - generic [ref=e339]: 可模拟
            - 'link "017 宝贝描述池 #/set/material/desc_pool 可模拟" [ref=e340] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-06
              - generic [ref=e341]: "017"
              - generic [ref=e342]:
                - text: 宝贝描述池
                - generic [ref=e343]: "#/set/material/desc_pool"
              - generic [ref=e344]: 可模拟
            - 'link "018 宝贝标签池 #/set/material/tab_pool 可模拟" [ref=e345] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-07
              - generic [ref=e346]: "018"
              - generic [ref=e347]:
                - text: 宝贝标签池
                - generic [ref=e348]: "#/set/material/tab_pool"
              - generic [ref=e349]: 可模拟
            - 'link "019 房屋出租 #/goods/edit/zf 可模拟" [ref=e350] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-08
              - generic [ref=e351]: "019"
              - generic [ref=e352]:
                - text: 房屋出租
                - generic [ref=e353]: "#/goods/edit/zf"
              - generic [ref=e354]: 可模拟
            - 'link "020 免费送宝贝 #/goods/edit/mfs 可模拟" [ref=e355] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-09
              - generic [ref=e356]: "020"
              - generic [ref=e357]:
                - text: 免费送宝贝
                - generic [ref=e358]: "#/goods/edit/mfs"
              - generic [ref=e359]: 可模拟
            - 'link "021 视频操作教程 #/goods/edit/v/1 可模拟" [ref=e360] [cursor=pointer]':
              - /url: /operations/product-editor/product-editor-10
              - generic [ref=e361]: "021"
              - generic [ref=e362]:
                - text: 视频操作教程
                - generic [ref=e363]: "#/goods/edit/v/1"
              - generic [ref=e364]: 可模拟
        - generic [ref=e365]:
          - generic [ref=e366]:
            - link [ref=e367] [cursor=pointer]:
              - /url: /operations/collection/collection-01
              - text: 资产准备
              - heading "采集管理" [level=3] [ref=e368]
            - strong [ref=e369]: 14 / 14
          - generic [ref=e370]:
            - 'link "022 商品链接采集 #/goods/spider/run 策略阻断" [ref=e371] [cursor=pointer]':
              - /url: /operations/collection/collection-01
              - generic [ref=e372]: "022"
              - generic [ref=e373]:
                - text: 商品链接采集
                - generic [ref=e374]: "#/goods/spider/run"
              - generic [ref=e375]: 策略阻断
            - 'link "023 闲鱼店铺解析 #/goods/spider/xy_shop_batch 策略阻断" [ref=e376] [cursor=pointer]':
              - /url: /operations/collection/collection-02
              - generic [ref=e377]: "023"
              - generic [ref=e378]:
                - text: 闲鱼店铺解析
                - generic [ref=e379]: "#/goods/spider/xy_shop_batch"
              - generic [ref=e380]: 策略阻断
            - 'link "024 搜索闲鱼宝贝 #/goods/spider/search_xy 策略阻断" [ref=e381] [cursor=pointer]':
              - /url: /operations/collection/collection-03
              - generic [ref=e382]: "024"
              - generic [ref=e383]:
                - text: 搜索闲鱼宝贝
                - generic [ref=e384]: "#/goods/spider/search_xy"
              - generic [ref=e385]: 策略阻断
            - 'link "025 淘宝店铺解析 #/goods/spider/tb_shop 策略阻断" [ref=e386] [cursor=pointer]':
              - /url: /operations/collection/collection-04
              - generic [ref=e387]: "025"
              - generic [ref=e388]:
                - text: 淘宝店铺解析
                - generic [ref=e389]: "#/goods/spider/tb_shop"
              - generic [ref=e390]: 策略阻断
            - 'link "026 转转店铺解析 #/goods/spider/zz_shop 策略阻断" [ref=e391] [cursor=pointer]':
              - /url: /operations/collection/collection-05
              - generic [ref=e392]: "026"
              - generic [ref=e393]:
                - text: 转转店铺解析
                - generic [ref=e394]: "#/goods/spider/zz_shop"
              - generic [ref=e395]: 策略阻断
            - 'link "027 微商相册解析 #/goods/spider/wsxc_shop 策略阻断" [ref=e396] [cursor=pointer]':
              - /url: /operations/collection/collection-06
              - generic [ref=e397]: "027"
              - generic [ref=e398]:
                - text: 微商相册解析
                - generic [ref=e399]: "#/goods/spider/wsxc_shop"
              - generic [ref=e400]: 策略阻断
            - 'link "028 孔网店铺解析 #/goods/spider/kfz_shop 策略阻断" [ref=e401] [cursor=pointer]':
              - /url: /operations/collection/collection-07
              - generic [ref=e402]: "028"
              - generic [ref=e403]:
                - text: 孔网店铺解析
                - generic [ref=e404]: "#/goods/spider/kfz_shop"
              - generic [ref=e405]: 策略阻断
            - 'link "029 阿里巴巴解析 #/goods/spider/1688_shop 策略阻断" [ref=e406] [cursor=pointer]':
              - /url: /operations/collection/collection-08
              - generic [ref=e407]: "029"
              - generic [ref=e408]:
                - text: 阿里巴巴解析
                - generic [ref=e409]: "#/goods/spider/1688_shop"
              - generic [ref=e410]: 策略阻断
            - 'link "030 宝贝详情解析 #/goods/spider/goods_details 策略阻断" [ref=e411] [cursor=pointer]':
              - /url: /operations/collection/collection-09
              - generic [ref=e412]: "030"
              - generic [ref=e413]:
                - text: 宝贝详情解析
                - generic [ref=e414]: "#/goods/spider/goods_details"
              - generic [ref=e415]: 策略阻断
            - 'link "031 宝贝视频解析 #/goods/spider/goods_video 策略阻断" [ref=e416] [cursor=pointer]':
              - /url: /operations/collection/collection-10
              - generic [ref=e417]: "031"
              - generic [ref=e418]:
                - text: 宝贝视频解析
                - generic [ref=e419]: "#/goods/spider/goods_video"
              - generic [ref=e420]: 策略阻断
            - 'link "032 文章链接采集 #/goods/spider/run_post 策略阻断" [ref=e421] [cursor=pointer]':
              - /url: /operations/collection/collection-11
              - generic [ref=e422]: "032"
              - generic [ref=e423]:
                - text: 文章链接采集
                - generic [ref=e424]: "#/goods/spider/run_post"
              - generic [ref=e425]: 策略阻断
            - 'link "033 多多宝贝采集 #/goods/spider/pdd_goods 策略阻断" [ref=e426] [cursor=pointer]':
              - /url: /operations/collection/collection-12
              - generic [ref=e427]: "033"
              - generic [ref=e428]:
                - text: 多多宝贝采集
                - generic [ref=e429]: "#/goods/spider/pdd_goods"
              - generic [ref=e430]: 策略阻断
            - 'link "034 采集任务列表 #/goods/spider/log 可模拟" [ref=e431] [cursor=pointer]':
              - /url: /operations/collection/collection-13
              - generic [ref=e432]: "034"
              - generic [ref=e433]:
                - text: 采集任务列表
                - generic [ref=e434]: "#/goods/spider/log"
              - generic [ref=e435]: 可模拟
            - 'link "035 视频操作教程 #/goods/spider/v/1 可模拟" [ref=e436] [cursor=pointer]':
              - /url: /operations/collection/collection-14
              - generic [ref=e437]: "035"
              - generic [ref=e438]:
                - text: 视频操作教程
                - generic [ref=e439]: "#/goods/spider/v/1"
              - generic [ref=e440]: 可模拟
        - generic [ref=e441]:
          - generic [ref=e442]:
            - link [ref=e443] [cursor=pointer]:
              - /url: /operations/product-management/product-management-01
              - text: 内容生产
              - heading "商品管理" [level=3] [ref=e444]
            - strong [ref=e445]: 10 / 10
          - generic [ref=e446]:
            - 'link "036 商品列表 #/goods/list 可模拟" [ref=e447] [cursor=pointer]':
              - /url: /operations/product-management/product-management-01
              - generic [ref=e448]: "036"
              - generic [ref=e449]:
                - text: 商品列表
                - generic [ref=e450]: "#/goods/list"
              - generic [ref=e451]: 可模拟
            - 'link "037 商品导入 #/goods/import 可模拟" [ref=e452] [cursor=pointer]':
              - /url: /operations/product-management/product-management-02
              - generic [ref=e453]: "037"
              - generic [ref=e454]:
                - text: 商品导入
                - generic [ref=e455]: "#/goods/import"
              - generic [ref=e456]: 可模拟
            - 'link "038 商品分组 #/goods/group 可模拟" [ref=e457] [cursor=pointer]':
              - /url: /operations/product-management/product-management-03
              - generic [ref=e458]: "038"
              - generic [ref=e459]:
                - text: 商品分组
                - generic [ref=e460]: "#/goods/group"
              - generic [ref=e461]: 可模拟
            - 'link "039 货源共享 #/goods/list_share 需审批" [ref=e462] [cursor=pointer]':
              - /url: /operations/product-management/product-management-04
              - generic [ref=e463]: "039"
              - generic [ref=e464]:
                - text: 货源共享
                - generic [ref=e465]: "#/goods/list_share"
              - generic [ref=e466]: 需审批
            - 'link "040 发布闲鱼 #/task/xy_task/goods_add2 需审批" [ref=e467] [cursor=pointer]':
              - /url: /operations/product-management/product-management-05
              - generic [ref=e468]: "040"
              - generic [ref=e469]:
                - text: 发布闲鱼
                - generic [ref=e470]: "#/task/xy_task/goods_add2"
              - generic [ref=e471]: 需审批
            - 'link "041 发布转转 #/task/zz_task/goods_add 需审批" [ref=e472] [cursor=pointer]':
              - /url: /operations/product-management/product-management-06
              - generic [ref=e473]: "041"
              - generic [ref=e474]:
                - text: 发布转转
                - generic [ref=e475]: "#/task/zz_task/goods_add"
              - generic [ref=e476]: 需审批
            - 'link "042 多多数据包 #/goods/pdd_import 可模拟" [ref=e477] [cursor=pointer]':
              - /url: /operations/product-management/product-management-07
              - generic [ref=e478]: "042"
              - generic [ref=e479]:
                - text: 多多数据包
                - generic [ref=e480]: "#/goods/pdd_import"
              - generic [ref=e481]: 可模拟
            - 'link "043 淘宝数据包 #/goods/tb_import 可模拟" [ref=e482] [cursor=pointer]':
              - /url: /operations/product-management/product-management-08
              - generic [ref=e483]: "043"
              - generic [ref=e484]:
                - text: 淘宝数据包
                - generic [ref=e485]: "#/goods/tb_import"
              - generic [ref=e486]: 可模拟
            - 'link "044 违禁词检测 #/goods/analyze_foul 可模拟" [ref=e487] [cursor=pointer]':
              - /url: /operations/product-management/product-management-09
              - generic [ref=e488]: "044"
              - generic [ref=e489]:
                - text: 违禁词检测
                - generic [ref=e490]: "#/goods/analyze_foul"
              - generic [ref=e491]: 可模拟
            - 'link "045 视频操作教程 #/goods/v/1 可模拟" [ref=e492] [cursor=pointer]':
              - /url: /operations/product-management/product-management-10
              - generic [ref=e493]: "045"
              - generic [ref=e494]:
                - text: 视频操作教程
                - generic [ref=e495]: "#/goods/v/1"
              - generic [ref=e496]: 可模拟
        - generic [ref=e497]:
          - generic [ref=e498]:
            - link [ref=e499] [cursor=pointer]:
              - /url: /operations/post-management/post-management-01
              - text: 内容生产
              - heading "帖子管理" [level=3] [ref=e500]
            - strong [ref=e501]: 9 / 9
          - generic [ref=e502]:
            - 'link "046 帖子编辑 #/post/edit 可模拟" [ref=e503] [cursor=pointer]':
              - /url: /operations/post-management/post-management-01
              - generic [ref=e504]: "046"
              - generic [ref=e505]:
                - text: 帖子编辑
                - generic [ref=e506]: "#/post/edit"
              - generic [ref=e507]: 可模拟
            - 'link "047 帖子采集 #/goods/spider/run_post 可模拟" [ref=e508] [cursor=pointer]':
              - /url: /operations/post-management/post-management-02
              - generic [ref=e509]: "047"
              - generic [ref=e510]:
                - text: 帖子采集
                - generic [ref=e511]: "#/goods/spider/run_post"
              - generic [ref=e512]: 可模拟
            - 'link "048 帖子列表 #/post/list 可模拟" [ref=e513] [cursor=pointer]':
              - /url: /operations/post-management/post-management-03
              - generic [ref=e514]: "048"
              - generic [ref=e515]:
                - text: 帖子列表
                - generic [ref=e516]: "#/post/list"
              - generic [ref=e517]: 可模拟
            - 'link "049 帖子分组 #/post/group 可模拟" [ref=e518] [cursor=pointer]':
              - /url: /operations/post-management/post-management-04
              - generic [ref=e519]: "049"
              - generic [ref=e520]:
                - text: 帖子分组
                - generic [ref=e521]: "#/post/group"
              - generic [ref=e522]: 可模拟
            - 'link "050 帖子水印 #/set/system/watermark 可模拟" [ref=e523] [cursor=pointer]':
              - /url: /operations/post-management/post-management-05
              - generic [ref=e524]: "050"
              - generic [ref=e525]:
                - text: 帖子水印
                - generic [ref=e526]: "#/set/system/watermark"
              - generic [ref=e527]: 可模拟
            - 'link "051 删除帖子 #/task/xy_task/xy_post_del 需审批" [ref=e528] [cursor=pointer]':
              - /url: /operations/post-management/post-management-06
              - generic [ref=e529]: "051"
              - generic [ref=e530]:
                - text: 删除帖子
                - generic [ref=e531]: "#/task/xy_task/xy_post_del"
              - generic [ref=e532]: 需审批
            - 'link "052 发布闲鱼 #/task/xy_task/post_add 需审批" [ref=e533] [cursor=pointer]':
              - /url: /operations/post-management/post-management-07
              - generic [ref=e534]: "052"
              - generic [ref=e535]:
                - text: 发布闲鱼
                - generic [ref=e536]: "#/task/xy_task/post_add"
              - generic [ref=e537]: 需审批
            - 'link "053 发布小红书 #/task/hs_task/post_add 需审批" [ref=e538] [cursor=pointer]':
              - /url: /operations/post-management/post-management-08
              - generic [ref=e539]: "053"
              - generic [ref=e540]:
                - text: 发布小红书
                - generic [ref=e541]: "#/task/hs_task/post_add"
              - generic [ref=e542]: 需审批
            - 'link "054 视频教程 #/post/v/1 可模拟" [ref=e543] [cursor=pointer]':
              - /url: /operations/post-management/post-management-09
              - generic [ref=e544]: "054"
              - generic [ref=e545]:
                - text: 视频教程
                - generic [ref=e546]: "#/post/v/1"
              - generic [ref=e547]: 可模拟
        - generic [ref=e548]:
          - generic [ref=e549]:
            - link [ref=e550] [cursor=pointer]:
              - /url: /operations/orders/orders-01
              - text: 互动交易
              - heading "订单管理" [level=3] [ref=e551]
            - strong [ref=e552]: 5 / 5
          - generic [ref=e553]:
            - 'link "055 同步闲鱼订单 #/order/get_order 需审批" [ref=e554] [cursor=pointer]':
              - /url: /operations/orders/orders-01
              - generic [ref=e555]: "055"
              - generic [ref=e556]:
                - text: 同步闲鱼订单
                - generic [ref=e557]: "#/order/get_order"
              - generic [ref=e558]: 需审批
            - 'link "056 去拼多多采购 #/order/from_pdd_buy 策略阻断" [ref=e559] [cursor=pointer]':
              - /url: /operations/orders/orders-02
              - generic [ref=e560]: "056"
              - generic [ref=e561]:
                - text: 去拼多多采购
                - generic [ref=e562]: "#/order/from_pdd_buy"
              - generic [ref=e563]: 策略阻断
            - 'link "057 取拼多多单号 #/order/get_pdd_order 策略阻断" [ref=e564] [cursor=pointer]':
              - /url: /operations/orders/orders-03
              - generic [ref=e565]: "057"
              - generic [ref=e566]:
                - text: 取拼多多单号
                - generic [ref=e567]: "#/order/get_pdd_order"
              - generic [ref=e568]: 策略阻断
            - 'link "058 查看全部订单 #/order/order_list 可模拟" [ref=e569] [cursor=pointer]':
              - /url: /operations/orders/orders-04
              - generic [ref=e570]: "058"
              - generic [ref=e571]:
                - text: 查看全部订单
                - generic [ref=e572]: "#/order/order_list"
              - generic [ref=e573]: 可模拟
            - 'link "059 视频操作教程 #/order/v/1 可模拟" [ref=e574] [cursor=pointer]':
              - /url: /operations/orders/orders-05
              - generic [ref=e575]: "059"
              - generic [ref=e576]:
                - text: 视频操作教程
                - generic [ref=e577]: "#/order/v/1"
              - generic [ref=e578]: 可模拟
        - generic [ref=e579]:
          - generic [ref=e580]:
            - link [ref=e581] [cursor=pointer]:
              - /url: /operations/analytics/analytics-01
              - text: 数据复盘
              - heading "统计分析" [level=3] [ref=e582]
            - strong [ref=e583]: 3 / 3
          - generic [ref=e584]:
            - 'link "060 采集宝贝信息 #/task/xy_task/xy_goods_get 可模拟" [ref=e585] [cursor=pointer]':
              - /url: /operations/analytics/analytics-01
              - generic [ref=e586]: "060"
              - generic [ref=e587]:
                - text: 采集宝贝信息
                - generic [ref=e588]: "#/task/xy_task/xy_goods_get"
              - generic [ref=e589]: 可模拟
            - 'link "061 宝贝流量变化 #/count/list 可模拟" [ref=e590] [cursor=pointer]':
              - /url: /operations/analytics/analytics-02
              - generic [ref=e591]: "061"
              - generic [ref=e592]:
                - text: 宝贝流量变化
                - generic [ref=e593]: "#/count/list"
              - generic [ref=e594]: 可模拟
            - 'link "062 视频操作教程 #/count/v/1 可模拟" [ref=e595] [cursor=pointer]':
              - /url: /operations/analytics/analytics-03
              - generic [ref=e596]: "062"
              - generic [ref=e597]:
                - text: 视频操作教程
                - generic [ref=e598]: "#/count/v/1"
              - generic [ref=e599]: 可模拟
        - generic [ref=e600]:
          - generic [ref=e601]:
            - link [ref=e602] [cursor=pointer]:
              - /url: /operations/xy-tasks/xy-tasks-01
              - text: 分发执行
              - heading "闲鱼授权任务" [level=3] [ref=e603]
            - strong [ref=e604]: 31 / 31
          - generic [ref=e605]:
            - 'link "063 发布商品 #/task/xy_task/goods_add2 需审批" [ref=e606] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-01
              - generic [ref=e607]: "063"
              - generic [ref=e608]:
                - text: 发布商品
                - generic [ref=e609]: "#/task/xy_task/goods_add2"
              - generic [ref=e610]: 需审批
            - 'link "064 发布帖子 #/task/xy_task/post_add 需审批" [ref=e611] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-02
              - generic [ref=e612]: "064"
              - generic [ref=e613]:
                - text: 发布帖子
                - generic [ref=e614]: "#/task/xy_task/post_add"
              - generic [ref=e615]: 需审批
            - 'link "065 擦亮商品 #/task/xy_task/xy_goods_polish 需审批" [ref=e616] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-03
              - generic [ref=e617]: "065"
              - generic [ref=e618]:
                - text: 擦亮商品
                - generic [ref=e619]: "#/task/xy_task/xy_goods_polish"
              - generic [ref=e620]: 需审批
            - 'link "066 上架商品 #/task/xy_task/xy_goods_shelf_up 需审批" [ref=e621] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-04
              - generic [ref=e622]: "066"
              - generic [ref=e623]:
                - text: 上架商品
                - generic [ref=e624]: "#/task/xy_task/xy_goods_shelf_up"
              - generic [ref=e625]: 需审批
            - 'link "067 下架商品 #/task/xy_task/xy_goods_shelf_down 需审批" [ref=e626] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-05
              - generic [ref=e627]: "067"
              - generic [ref=e628]:
                - text: 下架商品
                - generic [ref=e629]: "#/task/xy_task/xy_goods_shelf_down"
              - generic [ref=e630]: 需审批
            - 'link "068 删除商品 #/task/xy_task/xy_del_down_goods 需审批" [ref=e631] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-06
              - generic [ref=e632]: "068"
              - generic [ref=e633]:
                - text: 删除商品
                - generic [ref=e634]: "#/task/xy_task/xy_del_down_goods"
              - generic [ref=e635]: 需审批
            - 'link "069 删除帖子 #/task/xy_task/xy_post_del 需审批" [ref=e636] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-07
              - generic [ref=e637]: "069"
              - generic [ref=e638]:
                - text: 删除帖子
                - generic [ref=e639]: "#/task/xy_task/xy_post_del"
              - generic [ref=e640]: 需审批
            - 'link "070 绑定闲鱼 #/task/xy_task/xy_init 需审批" [ref=e641] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-08
              - generic [ref=e642]: "070"
              - generic [ref=e643]:
                - text: 绑定闲鱼
                - generic [ref=e644]: "#/task/xy_task/xy_init"
              - generic [ref=e645]: 需审批
            - 'link "071 签到鱼币 #/task/xy_task/register 策略阻断" [ref=e646] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-09
              - generic [ref=e647]: "071"
              - generic [ref=e648]:
                - text: 签到鱼币
                - generic [ref=e649]: "#/task/xy_task/register"
              - generic [ref=e650]: 策略阻断
            - 'link "072 鱼币抵扣 #/task/xy_task/dikou 策略阻断" [ref=e651] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-10
              - generic [ref=e652]: "072"
              - generic [ref=e653]:
                - text: 鱼币抵扣
                - generic [ref=e654]: "#/task/xy_task/dikou"
              - generic [ref=e655]: 策略阻断
            - 'link "073 鱼币推广 #/task/xy_task/jisumai 策略阻断" [ref=e656] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-11
              - generic [ref=e657]: "073"
              - generic [ref=e658]:
                - text: 鱼币推广
                - generic [ref=e659]: "#/task/xy_task/jisumai"
              - generic [ref=e660]: 策略阻断
            - 'link "074 一键小刀 #/task/xy_task/xiaodao 需审批" [ref=e661] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-12
              - generic [ref=e662]: "074"
              - generic [ref=e663]:
                - text: 一键小刀
                - generic [ref=e664]: "#/task/xy_task/xiaodao"
              - generic [ref=e665]: 需审批
            - 'link "075 一键降价 #/task/xy_task/xy_goods_price_cut 需审批" [ref=e666] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-13
              - generic [ref=e667]: "075"
              - generic [ref=e668]:
                - text: 一键降价
                - generic [ref=e669]: "#/task/xy_task/xy_goods_price_cut"
              - generic [ref=e670]: 需审批
            - 'link "076 一键好评 #/task/xy_task/xy_goods_haoping 策略阻断" [ref=e671] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-14
              - generic [ref=e672]: "076"
              - generic [ref=e673]:
                - text: 一键好评
                - generic [ref=e674]: "#/task/xy_task/xy_goods_haoping"
              - generic [ref=e675]: 策略阻断
            - 'link "077 重启闲鱼 #/task/xy_task/xy_restart 需审批" [ref=e676] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-15
              - generic [ref=e677]: "077"
              - generic [ref=e678]:
                - text: 重启闲鱼
                - generic [ref=e679]: "#/task/xy_task/xy_restart"
              - generic [ref=e680]: 需审批
            - 'link "078 删除动态 #/task/xy_task/remove_dongtai 需审批" [ref=e681] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-16
              - generic [ref=e682]: "078"
              - generic [ref=e683]:
                - text: 删除动态
                - generic [ref=e684]: "#/task/xy_task/remove_dongtai"
              - generic [ref=e685]: 需审批
            - 'link "079 删除消息 #/task/xy_task/del_message 需审批" [ref=e686] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-17
              - generic [ref=e687]: "079"
              - generic [ref=e688]:
                - text: 删除消息
                - generic [ref=e689]: "#/task/xy_task/del_message"
              - generic [ref=e690]: 需审批
            - 'link "080 删除留言 #/task/xy_task/remove_liuyan 需审批" [ref=e691] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-18
              - generic [ref=e692]: "080"
              - generic [ref=e693]:
                - text: 删除留言
                - generic [ref=e694]: "#/task/xy_task/remove_liuyan"
              - generic [ref=e695]: 需审批
            - 'link "081 草稿上架 #/task/xy_task/xy_caogao_shelf_up 需审批" [ref=e696] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-19
              - generic [ref=e697]: "081"
              - generic [ref=e698]:
                - text: 草稿上架
                - generic [ref=e699]: "#/task/xy_task/xy_caogao_shelf_up"
              - generic [ref=e700]: 需审批
            - 'link "082 编辑重发 #/task/xy_configure/re_edit 需审批" [ref=e701] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-20
              - generic [ref=e702]: "082"
              - generic [ref=e703]:
                - text: 编辑重发
                - generic [ref=e704]: "#/task/xy_configure/re_edit"
              - generic [ref=e705]: 需审批
            - 'link "083 托管无忧卖 #/task/xy_task/wuyoumai 需审批" [ref=e706] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-21
              - generic [ref=e707]: "083"
              - generic [ref=e708]:
                - text: 托管无忧卖
                - generic [ref=e709]: "#/task/xy_task/wuyoumai"
              - generic [ref=e710]: 需审批
            - 'link "084 快速编辑重发 #/task/xy_configure/fast_re_edit 需审批" [ref=e711] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-22
              - generic [ref=e712]: "084"
              - generic [ref=e713]:
                - text: 快速编辑重发
                - generic [ref=e714]: "#/task/xy_configure/fast_re_edit"
              - generic [ref=e715]: 需审批
            - 'link "085 快速下架商品 #/task/xy_task/fast_goods_del 需审批" [ref=e716] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-23
              - generic [ref=e717]: "085"
              - generic [ref=e718]:
                - text: 快速下架商品
                - generic [ref=e719]: "#/task/xy_task/fast_goods_del"
              - generic [ref=e720]: 需审批
            - 'link "086 采集宝贝信息 #/task/xy_task/xy_goods_get 可模拟" [ref=e721] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-24
              - generic [ref=e722]: "086"
              - generic [ref=e723]:
                - text: 采集宝贝信息
                - generic [ref=e724]: "#/task/xy_task/xy_goods_get"
              - generic [ref=e725]: 可模拟
            - 'link "087 通用地址池 #/task/xy_configure/area_pool 可模拟" [ref=e726] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-25
              - generic [ref=e727]: "087"
              - generic [ref=e728]:
                - text: 通用地址池
                - generic [ref=e729]: "#/task/xy_configure/area_pool"
              - generic [ref=e730]: 可模拟
            - 'link "088 设备地址池 #/task/xy_configure/area_dev_pool 可模拟" [ref=e731] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-26
              - generic [ref=e732]: "088"
              - generic [ref=e733]:
                - text: 设备地址池
                - generic [ref=e734]: "#/task/xy_configure/area_dev_pool"
              - generic [ref=e735]: 可模拟
            - 'link "089 描述池 #/set/material/desc_pool 可模拟" [ref=e736] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-27
              - generic [ref=e737]: "089"
              - generic [ref=e738]:
                - text: 描述池
                - generic [ref=e739]: "#/set/material/desc_pool"
              - generic [ref=e740]: 可模拟
            - 'link "090 标签池 #/set/material/tab_pool 可模拟" [ref=e741] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-28
              - generic [ref=e742]: "090"
              - generic [ref=e743]:
                - text: 标签池
                - generic [ref=e744]: "#/set/material/tab_pool"
              - generic [ref=e745]: 可模拟
            - 'link "091 图片水印 #/set/system/watermark 可模拟" [ref=e746] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-29
              - generic [ref=e747]: "091"
              - generic [ref=e748]:
                - text: 图片水印
                - generic [ref=e749]: "#/set/system/watermark"
              - generic [ref=e750]: 可模拟
            - 'link "092 违禁词检测 #/goods/analyze_foul 可模拟" [ref=e751] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-30
              - generic [ref=e752]: "092"
              - generic [ref=e753]:
                - text: 违禁词检测
                - generic [ref=e754]: "#/goods/analyze_foul"
              - generic [ref=e755]: 可模拟
            - 'link "093 视频操作教程 #/task/xy_task/v/1 可模拟" [ref=e756] [cursor=pointer]':
              - /url: /operations/xy-tasks/xy-tasks-31
              - generic [ref=e757]: "093"
              - generic [ref=e758]:
                - text: 视频操作教程
                - generic [ref=e759]: "#/task/xy_task/v/1"
              - generic [ref=e760]: 可模拟
        - generic [ref=e761]:
          - generic [ref=e762]:
            - link [ref=e763] [cursor=pointer]:
              - /url: /operations/zz-tasks/zz-tasks-01
              - text: 分发执行
              - heading "转转授权任务" [level=3] [ref=e764]
            - strong [ref=e765]: 9 / 9
          - generic [ref=e766]:
            - 'link "094 发布商品 #/task/zz_task/goods_add 需审批" [ref=e767] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-01
              - generic [ref=e768]: "094"
              - generic [ref=e769]:
                - text: 发布商品
                - generic [ref=e770]: "#/task/zz_task/goods_add"
              - generic [ref=e771]: 需审批
            - 'link "095 擦亮商品 #/task/zz_task/goods_rub 需审批" [ref=e772] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-02
              - generic [ref=e773]: "095"
              - generic [ref=e774]:
                - text: 擦亮商品
                - generic [ref=e775]: "#/task/zz_task/goods_rub"
              - generic [ref=e776]: 需审批
            - 'link "096 下架商品 #/task/zz_task/goods_down 需审批" [ref=e777] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-03
              - generic [ref=e778]: "096"
              - generic [ref=e779]:
                - text: 下架商品
                - generic [ref=e780]: "#/task/zz_task/goods_down"
              - generic [ref=e781]: 需审批
            - 'link "097 上架商品 #/task/zz_task/goods_up 需审批" [ref=e782] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-04
              - generic [ref=e783]: "097"
              - generic [ref=e784]:
                - text: 上架商品
                - generic [ref=e785]: "#/task/zz_task/goods_up"
              - generic [ref=e786]: 需审批
            - 'link "098 删除商品 #/task/zz_task/goods_del 需审批" [ref=e787] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-05
              - generic [ref=e788]: "098"
              - generic [ref=e789]:
                - text: 删除商品
                - generic [ref=e790]: "#/task/zz_task/goods_del"
              - generic [ref=e791]: 需审批
            - 'link "099 转转养号 #/task/zz_task/yanghao 策略阻断" [ref=e792] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-06
              - generic [ref=e793]: "099"
              - generic [ref=e794]:
                - text: 转转养号
                - generic [ref=e795]: "#/task/zz_task/yanghao"
              - generic [ref=e796]: 策略阻断
            - 'link "100 流量模式 #/task/zz_task/re_edit 策略阻断" [ref=e797] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-07
              - generic [ref=e798]: "100"
              - generic [ref=e799]:
                - text: 流量模式
                - generic [ref=e800]: "#/task/zz_task/re_edit"
              - generic [ref=e801]: 策略阻断
            - 'link "101 违禁词检测 #/goods/analyze_foul 可模拟" [ref=e802] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-08
              - generic [ref=e803]: "101"
              - generic [ref=e804]:
                - text: 违禁词检测
                - generic [ref=e805]: "#/goods/analyze_foul"
              - generic [ref=e806]: 可模拟
            - 'link "102 视频操作教程 #/task/zz_task/v/1 可模拟" [ref=e807] [cursor=pointer]':
              - /url: /operations/zz-tasks/zz-tasks-09
              - generic [ref=e808]: "102"
              - generic [ref=e809]:
                - text: 视频操作教程
                - generic [ref=e810]: "#/task/zz_task/v/1"
              - generic [ref=e811]: 可模拟
        - generic [ref=e812]:
          - generic [ref=e813]:
            - link [ref=e814] [cursor=pointer]:
              - /url: /operations/red-tasks/red-tasks-01
              - text: 分发执行
              - heading "小红书授权任务" [level=3] [ref=e815]
            - strong [ref=e816]: 4 / 4
          - generic [ref=e817]:
            - 'link "103 发布笔记 #/task/hs_task/post_add 需审批" [ref=e818] [cursor=pointer]':
              - /url: /operations/red-tasks/red-tasks-01
              - generic [ref=e819]: "103"
              - generic [ref=e820]:
                - text: 发布笔记
                - generic [ref=e821]: "#/task/hs_task/post_add"
              - generic [ref=e822]: 需审批
            - 'link "104 删除笔记 #/task/hs_task/post_del 需审批" [ref=e823] [cursor=pointer]':
              - /url: /operations/red-tasks/red-tasks-02
              - generic [ref=e824]: "104"
              - generic [ref=e825]:
                - text: 删除笔记
                - generic [ref=e826]: "#/task/hs_task/post_del"
              - generic [ref=e827]: 需审批
            - 'link "105 小红书养号 #/task/hs_task/yanghao 策略阻断" [ref=e828] [cursor=pointer]':
              - /url: /operations/red-tasks/red-tasks-03
              - generic [ref=e829]: "105"
              - generic [ref=e830]:
                - text: 小红书养号
                - generic [ref=e831]: "#/task/hs_task/yanghao"
              - generic [ref=e832]: 策略阻断
            - 'link "106 搜索养号 #/task/hs_task/flow_search 策略阻断" [ref=e833] [cursor=pointer]':
              - /url: /operations/red-tasks/red-tasks-04
              - generic [ref=e834]: "106"
              - generic [ref=e835]:
                - text: 搜索养号
                - generic [ref=e836]: "#/task/hs_task/flow_search"
              - generic [ref=e837]: 策略阻断
        - generic [ref=e838]:
          - generic [ref=e839]:
            - link [ref=e840] [cursor=pointer]:
              - /url: /operations/creative/creative-01
              - text: 内容生产
              - heading "创意中心" [level=3] [ref=e841]
            - strong [ref=e842]: 4 / 4
          - generic [ref=e843]:
            - 'link "107 爆款商品分析 #/idea/fiery 可模拟" [ref=e844] [cursor=pointer]':
              - /url: /operations/creative/creative-01
              - generic [ref=e845]: "107"
              - generic [ref=e846]:
                - text: 爆款商品分析
                - generic [ref=e847]: "#/idea/fiery"
              - generic [ref=e848]: 可模拟
            - 'link "108 创意文案 #/idea/wenan 可模拟" [ref=e849] [cursor=pointer]':
              - /url: /operations/creative/creative-02
              - generic [ref=e850]: "108"
              - generic [ref=e851]:
                - text: 创意文案
                - generic [ref=e852]: "#/idea/wenan"
              - generic [ref=e853]: 可模拟
            - 'link "109 TOP5000蓝海词 #/idea/blue 可模拟" [ref=e854] [cursor=pointer]':
              - /url: /operations/creative/creative-03
              - generic [ref=e855]: "109"
              - generic [ref=e856]:
                - text: TOP5000蓝海词
                - generic [ref=e857]: "#/idea/blue"
              - generic [ref=e858]: 可模拟
            - 'link "110 视频教程 #/idea/v/1 可模拟" [ref=e859] [cursor=pointer]':
              - /url: /operations/creative/creative-04
              - generic [ref=e860]: "110"
              - generic [ref=e861]:
                - text: 视频教程
                - generic [ref=e862]: "#/idea/v/1"
              - generic [ref=e863]: 可模拟
        - generic [ref=e864]:
          - generic [ref=e865]:
            - link [ref=e866] [cursor=pointer]:
              - /url: /operations/chat/chat-01
              - text: 互动交易
              - heading "聊天管理" [level=3] [ref=e867]
            - strong [ref=e868]: 11 / 11
          - generic [ref=e869]:
            - 'link "111 开启消息回复 #/im/open_im 需审批" [ref=e870] [cursor=pointer]':
              - /url: /operations/chat/chat-01
              - generic [ref=e871]: "111"
              - generic [ref=e872]:
                - text: 开启消息回复
                - generic [ref=e873]: "#/im/open_im"
              - generic [ref=e874]: 需审批
            - 'link "112 关闭消息回复 #/im/close_im 需审批" [ref=e875] [cursor=pointer]':
              - /url: /operations/chat/chat-02
              - generic [ref=e876]: "112"
              - generic [ref=e877]:
                - text: 关闭消息回复
                - generic [ref=e878]: "#/im/close_im"
              - generic [ref=e879]: 需审批
            - 'link "113 关键词回复 #/im/word 需审批" [ref=e880] [cursor=pointer]':
              - /url: /operations/chat/chat-03
              - generic [ref=e881]: "113"
              - generic [ref=e882]:
                - text: 关键词回复
                - generic [ref=e883]: "#/im/word"
              - generic [ref=e884]: 需审批
            - 'link "114 场景回复组 #/im/scenes 需审批" [ref=e885] [cursor=pointer]':
              - /url: /operations/chat/chat-04
              - generic [ref=e886]: "114"
              - generic [ref=e887]:
                - text: 场景回复组
                - generic [ref=e888]: "#/im/scenes"
              - generic [ref=e889]: 需审批
            - 'link "115 手机端回复 #/im/mim 需审批" [ref=e890] [cursor=pointer]':
              - /url: /operations/chat/chat-05
              - generic [ref=e891]: "115"
              - generic [ref=e892]:
                - text: 手机端回复
                - generic [ref=e893]: "#/im/mim"
              - generic [ref=e894]: 需审批
            - 'link "116 消息回复格式 #/im/message_text 需审批" [ref=e895] [cursor=pointer]':
              - /url: /operations/chat/chat-06
              - generic [ref=e896]: "116"
              - generic [ref=e897]:
                - text: 消息回复格式
                - generic [ref=e898]: "#/im/message_text"
              - generic [ref=e899]: 需审批
            - 'link "117 快捷回复管理 #/im/fast 需审批" [ref=e900] [cursor=pointer]':
              - /url: /operations/chat/chat-07
              - generic [ref=e901]: "117"
              - generic [ref=e902]:
                - text: 快捷回复管理
                - generic [ref=e903]: "#/im/fast"
              - generic [ref=e904]: 需审批
            - 'link "118 表情素材管理 #/im/xy_face 可模拟" [ref=e905] [cursor=pointer]':
              - /url: /operations/chat/chat-08
              - generic [ref=e906]: "118"
              - generic [ref=e907]:
                - text: 表情素材管理
                - generic [ref=e908]: "#/im/xy_face"
              - generic [ref=e909]: 可模拟
            - 'link "119 图片素材管理 #/set/material/image 可模拟" [ref=e910] [cursor=pointer]':
              - /url: /operations/chat/chat-09
              - generic [ref=e911]: "119"
              - generic [ref=e912]:
                - text: 图片素材管理
                - generic [ref=e913]: "#/set/material/image"
              - generic [ref=e914]: 可模拟
            - 'link "120 音频素材管理 #/set/material/audio 可模拟" [ref=e915] [cursor=pointer]':
              - /url: /operations/chat/chat-10
              - generic [ref=e916]: "120"
              - generic [ref=e917]:
                - text: 音频素材管理
                - generic [ref=e918]: "#/set/material/audio"
              - generic [ref=e919]: 可模拟
            - 'link "121 视频素材管理 #/set/material/video 可模拟" [ref=e920] [cursor=pointer]':
              - /url: /operations/chat/chat-11
              - generic [ref=e921]: "121"
              - generic [ref=e922]:
                - text: 视频素材管理
                - generic [ref=e923]: "#/set/material/video"
              - generic [ref=e924]: 可模拟
        - generic [ref=e925]:
          - generic [ref=e926]:
            - link [ref=e927] [cursor=pointer]:
              - /url: /operations/assets/assets-01
              - text: 资产准备
              - heading "系统素材" [level=3] [ref=e928]
            - strong [ref=e929]: 8 / 8
          - generic [ref=e930]:
            - 'link "122 图片水印 #/set/system/watermark 可模拟" [ref=e931] [cursor=pointer]':
              - /url: /operations/assets/assets-01
              - generic [ref=e932]: "122"
              - generic [ref=e933]:
                - text: 图片水印
                - generic [ref=e934]: "#/set/system/watermark"
              - generic [ref=e935]: 可模拟
            - 'link "123 图片素材 #/set/material/image 可模拟" [ref=e936] [cursor=pointer]':
              - /url: /operations/assets/assets-02
              - generic [ref=e937]: "123"
              - generic [ref=e938]:
                - text: 图片素材
                - generic [ref=e939]: "#/set/material/image"
              - generic [ref=e940]: 可模拟
            - 'link "124 音频素材 #/set/material/audio 可模拟" [ref=e941] [cursor=pointer]':
              - /url: /operations/assets/assets-03
              - generic [ref=e942]: "124"
              - generic [ref=e943]:
                - text: 音频素材
                - generic [ref=e944]: "#/set/material/audio"
              - generic [ref=e945]: 可模拟
            - 'link "125 视频素材 #/set/material/video 可模拟" [ref=e946] [cursor=pointer]':
              - /url: /operations/assets/assets-04
              - generic [ref=e947]: "125"
              - generic [ref=e948]:
                - text: 视频素材
                - generic [ref=e949]: "#/set/material/video"
              - generic [ref=e950]: 可模拟
            - 'link "126 通用地址池 #/task/xy_configure/area_pool 可模拟" [ref=e951] [cursor=pointer]':
              - /url: /operations/assets/assets-05
              - generic [ref=e952]: "126"
              - generic [ref=e953]:
                - text: 通用地址池
                - generic [ref=e954]: "#/task/xy_configure/area_pool"
              - generic [ref=e955]: 可模拟
            - 'link "127 设备地址池 #/task/xy_configure/area_dev_pool 可模拟" [ref=e956] [cursor=pointer]':
              - /url: /operations/assets/assets-06
              - generic [ref=e957]: "127"
              - generic [ref=e958]:
                - text: 设备地址池
                - generic [ref=e959]: "#/task/xy_configure/area_dev_pool"
              - generic [ref=e960]: 可模拟
            - 'link "128 描述池 #/set/material/desc_pool 可模拟" [ref=e961] [cursor=pointer]':
              - /url: /operations/assets/assets-07
              - generic [ref=e962]: "128"
              - generic [ref=e963]:
                - text: 描述池
                - generic [ref=e964]: "#/set/material/desc_pool"
              - generic [ref=e965]: 可模拟
            - 'link "129 标签池 #/set/material/tab_pool 可模拟" [ref=e966] [cursor=pointer]':
              - /url: /operations/assets/assets-08
              - generic [ref=e967]: "129"
              - generic [ref=e968]:
                - text: 标签池
                - generic [ref=e969]: "#/set/material/tab_pool"
              - generic [ref=e970]: 可模拟
        - generic [ref=e971]:
          - generic [ref=e972]:
            - link [ref=e973] [cursor=pointer]:
              - /url: /operations/profile/profile-01
              - text: 数据复盘
              - heading "个人中心" [level=3] [ref=e974]
            - strong [ref=e975]: 5 / 5
          - generic [ref=e976]:
            - 'link "130 基本资料 #/set/user/info 可模拟" [ref=e977] [cursor=pointer]':
              - /url: /operations/profile/profile-01
              - generic [ref=e978]: "130"
              - generic [ref=e979]:
                - text: 基本资料
                - generic [ref=e980]: "#/set/user/info"
              - generic [ref=e981]: 可模拟
            - 'link "131 修改密码 #/set/user/password 可模拟" [ref=e982] [cursor=pointer]':
              - /url: /operations/profile/profile-02
              - generic [ref=e983]: "131"
              - generic [ref=e984]:
                - text: 修改密码
                - generic [ref=e985]: "#/set/user/password"
              - generic [ref=e986]: 可模拟
            - 'link "132 邀请好友 #/set/user/invite 可模拟" [ref=e987] [cursor=pointer]':
              - /url: /operations/profile/profile-03
              - generic [ref=e988]: "132"
              - generic [ref=e989]:
                - text: 邀请好友
                - generic [ref=e990]: "#/set/user/invite"
              - generic [ref=e991]: 可模拟
            - 'link "133 积分明细 #/set/user/jf 可模拟" [ref=e992] [cursor=pointer]':
              - /url: /operations/profile/profile-04
              - generic [ref=e993]: "133"
              - generic [ref=e994]:
                - text: 积分明细
                - generic [ref=e995]: "#/set/user/jf"
              - generic [ref=e996]: 可模拟
            - 'link "134 AI功能设置 #/set/user/prompt 可模拟" [ref=e997] [cursor=pointer]':
              - /url: /operations/profile/profile-05
              - generic [ref=e998]: "134"
              - generic [ref=e999]:
                - text: AI功能设置
                - generic [ref=e1000]: "#/set/user/prompt"
              - generic [ref=e1001]: 可模拟
      - generic [ref=e1003]:
        - strong [ref=e1004]: 原始页面路由对照竞品登录后可见菜单
        - paragraph [ref=e1005]: 同一路由若从不同菜单出现，仍按独立入口收录。采集、养号、鱼币等能力保留页面规格，生产策略保持阻断；可执行入口走 LAMDA Control API。
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
> 30  |   await expect(page.getByText('原始页面路由')).toBeVisible()
      |                                          ^ Error: expect(locator).toBeVisible() failed
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
  49  |   await expect(page.getByText('#/set/system/watermark')).toBeVisible()
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