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
