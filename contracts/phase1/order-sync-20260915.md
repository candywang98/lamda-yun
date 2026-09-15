# Order Sync 契约（P41/P42 slice 1）— 20260915.1

冻结人：Root/总控。基线 `50b4fda`。三端（W1 后端 / W2 Android / W3 Web）按本文件实现；语义冲突由总控裁定，不自行变更。

## 1. 范围与边界

- 平台：闲鱼（`platform="xianyu"`），方向 `SOLD`（我卖出的）/ `BOUGHT`（我买到的）。其他平台留字段不留实现。
- 本切片交付：订单表 + 迁移、companion 批量上报（幂等）、操作员查询 API、采集任务 steps 形状、Companion 执行与上报、Web 订单列表/详情页。
- **不做**：分页断点续传（slice 2）、订单详情页采集、发货/售后动作、扣费/评价（G3 范畴）。本切片无第三方写副作用，不涉及 G3。
- 真实订单数据为只读采集；不删除、不修改平台订单。

## 2. 数据模型（后端迁移 `20260915_0021_xianyu_orders`）

表 `xianyu_order`（ORM `OrderRow`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | UUID PK | 服务端生成 |
| tenant_id | STR FK | 租户隔离，同 im_thread 模式 |
| device_id | STR FK | 上报设备 |
| platform | STR | 默认 `xianyu`，check in (xianyu,) |
| direction | STR | `SOLD` / `BOUGHT`，check 约束 |
| order_key | STR | 平台订单自然键（页面读到的订单号/条目键，去空白截 128） |
| item_title | STR | 商品标题快照，可空 |
| buyer_name | STR | 对手昵称快照，可空 |
| amount_cents | INT | 金额分，可空（>0 校验） |
| status_text | STR | 页面状态原文（如 待发货/已发货/交易成功），截 64 |
| occurred_at | DATETIME | 页面时间解析失败则空 |
| raw | JSON | 行原文（title/desc 拼接），最小化保存 |
| created_at / updated_at | DATETIME | TimestampMixin |

- 唯一约束：`(tenant_id, device_id, platform, order_key)`。order_key 取不到时该行**拒收**（422 明细），不落库——宁缺勿假键。
- 迁移：`revision="20260915_0021"`，`down_revision="20260915_0020"`，SQLite 用 `batch_alter_table` 兼容写法；down 干净回滚。

## 3. Companion 上报端点（幂等批量）

`POST /companion/v2/orders/batch`

- 认证：与 `/companion/v2/im/messages` 相同的 binding 认证。
- 请求体：`{"orders": [{"direction","order_key","item_title?","buyer_name?","amount_cents?","status_text?","occurred_at?(ISO)","raw?"}], "collected_at": "ISO"}`；batch 1..20，超限 422。
- 服务端按唯一键 select-by-key 存在即跳过（不更新快照，slice 1 以首次为准），返回 `201 {"accepted": n, "duplicates": m}`；全重复返回 200 同结构。重放安全。
- 校验失败逐条返回 422 `{"detail":[...]}`，指明 index 与字段。

## 4. 操作员查询 API

- `GET /api/v1/orders?device_id=&direction=&status_text=&limit=&offset=` → `{"items":[...],"total": n}`，limit 1..100 默认 20，按 occurred_at/created_at DESC。
- `GET /api/v1/orders/{id}` → 单条 404 语义。
- 权限：与 `/api/v1/im` 相同的 `current_actor`；只读。

## 5. 采集任务 steps 形状（冻结）

command_type：`xianyu.collect_orders.steps.v1`

- 步骤序列（固定顺序）：导航至订单列表（`ui.tapText`/`ui.tap` 既有定位器）→ **恰好一个** `ui.readOrders` → `ui.screenshot` → 收尾 `run.log`。
- `ui.readOrders` 参数：`direction`（SOLD/BOUGHT，必填）、`maxRows`（1..10，必填）、`locatorRef`（列表容器定位器，必填）。
- 执行语义：进入对应列表页 → 读当前屏订单行（行=列表容器内可点击子节点，文本来自 text/content-desc）→ 解析出 order_key/item_title/amount/buyer/status → **任务内**先经既有 complete 事件上报摘要，并在步成功后由 Companion 立即调 §3 批量端点落库；解析不出 order_key 的行记入 `skipped_rows`（原因：NO_KEY），不算失败。
- 行数不足 maxRows：读到多少算多少，任务成功；空列表任务成功并上报 0 行。
- 步失败语义沿用既有：超时 `STEP_TIMEOUT`、定位器未验证 `LOCATOR_UNVERIFIED`（见 §7）。
- steps 哈希不变量与维护动作一致：编排元数据可入 steps[0] 头部但**不得含 `action` 键**。

## 6. 后端编排（W1）

`POST /api/v1/xianyu/orders:collect`（Idempotency-Key 头，模式同 `maintenance:run`）：入参 `{device_id, direction, max_rows}` → 生成 §5 形状任务（run_id=uuid5 幂等）→ `GET /api/v1/xianyu/orders/runs/{run_id}` 聚合状态（复用 MobileTaskRow.batch_id 模式）。

## 7. Android 定位器（本轮未验证，fail-closed）

以下定位器**未经真机验证**，注册表条目一律 `verified=false`：`resolve()` 返回 null → 步失败 `LOCATOR_UNVERIFIED`，任务安全终止、零副作用。真机勘测后由总控冻结坐标/锚点并翻转 verified。

- `xianyu_order_list_sold` / `xianyu_order_list_bought`：我的页 → 我卖出的 / 我买到的 入口（预填锚点假设：desc/文本含「我卖出的」「我买到的」，具体以真机为准）。
- `xianyu_orders_container`：订单列表容器（可滚动列表）。
- 订单行读取：行内文本节点组合解析；歧义行跳过并记 `skipped_rows`。

## 8. Web（W3）

- 路由 `/orders`（name `orders`，coreRoutes）。
- `src/api/orders.ts` 手写模块（模式抄 `src/api/im.ts`：DTO + request<T> + controlApiHeaders）；**不得改** `@cloudctl/api-contracts` 生成客户端。
- 页面 `OrdersView.vue`：设备下拉（复用 im 的 loadDeviceOptions 模式）、方向/状态过滤、列表（order_key、item_title、buyer_name、金额、status_text、occurred_at）、详情展开、手动刷新、空态/错误态 fail-closed（不 mock 数据）。
- 采集入口按钮：选设备+方向后调 §6 `orders:collect`，展示 run 状态轮询（可选做，最小为禁用态+说明）。

## 9. 门禁

- W1：`uv run pytest -q tests/integration/test_orders_sync.py tests/integration/test_openapi_contract.py`（先 `python3 scripts/export_openapi.py`）；全量回归无新失败；迁移 up/down 各一次。
- W2：`cd mobile/companion && ./gradlew testDebugUnitTest`（独立 GRADLE_USER_HOME），新增单测覆盖 readOrders 解析/跳过/LOCATOR_UNVERIFIED。
- W3：`pnpm --filter @cloudctl/web test`、`vue-tsc` typecheck、`build` 全过。
- 验收边界：软件测试通过 ≠ 真机采集验收；真机验收由总控持 DEVICE 锁串行执行后记录。
