# Order Sync 契约 slice 2（多屏采集+分屏续传）— 20260915.1

冻结人：Root/总控。基线 `c113f0e`。slice 1（order-sync/20260915.1+.2）已真机验收，全部端点/形状不动。

## 0. 勘察事实（本轮实测，证据 recon-20260915-2/12–15）

- 订单**详情页**（列表行点击进入，Flutter）无障碍树**无订单号、无编号、无创建/付款/下单时间**（自顶至底 5 屏扫描，无 12 位以上数字串）；页面结构：订单状态页题 + 商品块 + 底部动作条（联系卖家/更多/再次购买/确认收货）+ 推荐流。
- **裁决**：`order_key` 维持 slice1 复合自然键（order-sync/20260915.2），不做「详情页订单号升级」；`occurred_at` 页面无源，slice2 不实现（保持可空）。碰撞局限已知并沿用。

## 1. steps v2（多屏采集）

command_type：`xianyu.collect_orders.steps.v2`

- 步骤序列：`ui.tap`(profile) → `ui.tap`(方向入口) → **readOrders(第1屏)** → [`ui.swipeUp`(列表内上滑一屏) → **readOrders(第 N 屏)**]×(screens-1) → `ui.screenshot` → `run.log`。
- `ui.readOrders` 参数不变（direction/maxRows 1..10/locatorRef），新增所在屏序号仅用于日志（`screen=N`），**不进 steps 哈希敏感字段**（steps[0] 头部仍不得含 `action` 键）。
- `ui.swipeUp` 为既有原语（waitFor 价格定位已用）；作用于订单列表容器区域（xianyu-anchors §3 容器的 bounds 内，禁止全屏滑（避免误触底部 tab/横幅））。
- v1（`xianyu.collect_orders.steps.v1`）完全保留：默认 screens=1 时后端**必须**继续生成 v1（已验收形状不变）；仅 screens≥2 生成 v2。

## 2. 编排入参（collect 扩展）

`POST /api/v1/xianyu/orders:collect` 入参在 slice1 基础上新增可选 `screens`（int，1..3，默认 1；非法 422）。`max_rows` 语义细化为**每屏上限**（1..10）。run_id 幂等键拼接含 screens。

## 3. 执行与上报语义（断点续传）

- **分屏上报**：每个 readOrders 步成功后**立即**调 §3 批量端点上报该屏行（每屏 ≤10，天然满足 batch 1..20）；后一屏滚动/读取失败时，前几屏数据已落库——这就是 slice2 的续传语义（幂等键去重，整任务重跑安全）。
- **跨屏去重**：同一 run 内 Companpanion 侧按 order_key 去重（重复行跳过，不计 duplicates 也不重复上报）；服务端幂等兜底不变。
- 滚动后新屏与旧屏内容重叠（闲鱼列表惯性）：重叠行被跨屏去重吸收。

## 4. Web（采集入口启用）

- `OrdersView.vue` 采集按钮从禁用态改为可用：选设备+方向+屏数（1..3）→ 调 v2 collect（screens=1 走 v1 入参兼容）→ 轮询 runs 至终态 → 刷新列表；失败/run 失败如实展示（fail-closed）。
- `orders.ts` 已有 collect/runs 封装，补 `screens` 参数与终态判断。

## 5. 门禁与边界

- W-S2API：`uv run pytest -q` 全量无新失败 + 新增 v2 用例（screens 边界/幂等/形状门禁 8 变异）+ `python3 scripts/export_openapi.py`；不迁移新表（复用 xianyu_order）。
- W-S2WEB：`pnpm --filter @cloudctl/web test` + typecheck + build。
- Android v2 执行器（swipeUp 作用于容器、screen 日志、跨屏去重）**不在本批**（mobile/companion 由 W4 线持有），随 W4 合并后下一切片实现；v2 任务发到当前 APK 会安全拒绝（未知形状），验收边界照旧：软件测试通过 ≠ 真机验收。
