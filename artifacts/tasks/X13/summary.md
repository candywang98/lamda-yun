# X13 宝贝信息采集与商品同步——软件层切片（2026-09-20）

## 交付
- 后端 `fleet_listings.py`：POST /companion/v2/fleet/listings/screens（组合自然键身份去重upsert + 内容哈希变更历史 + 同屏重放守卫）+ GET /api/v1/fleet/listings/history（游标分页+租户隔离）；迁移 0030（fleet_listing / fleet_listing_snapshot / fleet_listing_screen 三表）
- companion：ListingReading 解析器（U+200B清洗、标题64/键128上限、拒绝无价/无题卡片）+ CloudTaskClient.sendListingsScreen
- Web：listings-api.ts + 采集页真实派发（Idempotency-Key 逐设备）+ 采集结果表
- 已部署首尔生产（迁移至0030，端点200实测）

## 验证
- 后端 4 新集成测 + 全量 1063 过/11 跳；companion 单测过；vue-tsc 绿；OpenAPI 重导 +245；ruff 新文件零问题；plan_guard exit 0
- 页面结构真机核验：C机「我发布的」三标签（在卖/n草稿/已下架）+ 空态文案（dump 存 /tmp/recon-listings/06-published.xml）

## 接缝（登记，不阻塞）
- 执行器 ui.readListings 动作接线（导航我发布的→逐屏读→上报）= 下一波
- 卡片级行料校准：唯一有真实商品的 A机(OnePlus 9R) 闲鱼登录态 2026-09-20 失效，等用户重登后 30 分钟内可完成校准+真机采集

## 2026-09-20 深夜追加：真实数据闭环 + 竞品情报校准

### 真实商品入库（生产链路）
- A机(OnePlus 9R)真实卡片三张经 companion 生产客户端(CloudTaskClient.sendListingsScreen, 真实binding token+pin)推送
- 服务器返回 accepted:3；DB 与 /api/v1/fleet/listings/history 均可见：
  《小升初新思维作文》¥18.88 曝光2/浏览2/想要0；《漫画好玩的心理学》¥18.88 曝光0/浏览7/想要0；《十万个为什么》¥8.88 曝光13/浏览2/想要0
- 修复生产缺陷：迁移0030 updated_at NOT NULL 与 ORM(TimestampMixin仅created_at)不一致 → 0032 放宽（测试环境从ORM建表故未暴露）

### 竞品(鱼游)反编译情报采纳的三项校准
1. 「万」单位：曝光1.2万 → 12000（解析器已实现+单测）
2. 标题防污染：CDN图片文件名(TB1...png_110x10000.jpg_)误入标题位 → 识别为噪音跳过（已实现+单测）
3. 缺省补零：卡片缺统计行 → 曝光/浏览/想要默认0（edit_count语义，已实现+单测）

### 裁决记录（用户拍板）
- 封面：统计线零采集；不走分享链接解析（竞品add_fiery2是养号场景，自家品不传图）；封面如需为独立切片（无障碍bounds裁切/详情截图），不绑闲鱼分享口令
- 身份键：保持 title|price 组合键；同标题同价多品统计合并为已知限制（竞品同缺陷且更弱——纯title）；真实商品ID锚定为后续差异点（REAL_ID字段已预留）
- 曝光口径：单品曝光=卡片「曝光」字段（非店级「今日曝光」）
- 执行器规格：滚动终止锚点=「所有宝贝加载完成」文案出现（或达屏数上限）
