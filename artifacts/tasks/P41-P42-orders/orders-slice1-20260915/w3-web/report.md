# ORDERS-SLICE1-W3 Web 交付报告

- TaskID=ORDERS-SLICE1-W3
- BaselineSHA=d942bd3（开工核实：`git log --oneline -1` = `d942bd3 Freeze the order sync slice contract (order-sync/20260915.1)`）
- BranchSHA=fd00b97（分支 `agent/order-web`，单 commit）
- ContractVersion=order-sync/20260915.1（`contracts/phase1/order-sync-20260915.md` §4 §6 §8）
- 需要的锁：无

## OwnedPaths

- `apps/web/src/api/orders.ts`（新增，手写，未动 `@cloudctl/api-contracts`）
- `apps/web/src/views/OrdersView.vue`（新增）
- `apps/web/src/router.ts`（coreRoutes 注册 `/orders`）
- `apps/web/tests/orders-api.spec.ts`、`apps/web/tests/orders-view.spec.ts`（新增）
- `apps/web/tests/router.spec.ts`（coreRoutes 计数 22→23 + orders 路由断言）
- `artifacts/tasks/P41-P42-orders/orders-slice1-20260915/w3-web/`（本目录）

## ChangedFiles（git diff --stat d942bd3..HEAD）

```
apps/web/src/api/orders.ts         | 187 ++++++++++++++++++++
apps/web/src/router.ts             |   2 +
apps/web/src/views/OrdersView.vue  | 346 ++++++++++++++++++++++++++++++++++
apps/web/tests/orders-api.spec.ts  | 189 ++++++++++++++++++++
apps/web/tests/orders-view.spec.ts | 145 ++++++++++++++
apps/web/tests/router.spec.ts      |  13 +-
6 files changed, 880 insertions(+), 2 deletions(-)
```

## 实现要点

- **API 模块** `src/api/orders.ts`：完全照 `src/api/im.ts` 模式（DTO + `request<T>` + `controlApiHeaders` + `OrdersApiError` + detail 扁平化）。封装 `listOrders`（`GET /api/v1/orders?device_id=&direction=&status_text=&limit=&offset=`，空过滤参数省略）、`fetchOrder`（`GET /api/v1/orders/{id}`，404 → 「订单不存在或已被删除」）、`startXianyuOrderCollect`（`POST /api/v1/xianyu/orders:collect`，Idempotency-Key 头 + snake_case body `{device_id, direction, max_rows}`）、`fetchXianyuOrderRun`（`GET /api/v1/xianyu/orders/runs/{run_id}`）。辅助：`formatOrderAmount`（分转元，整数运算）、`formatOrderTime`、方向标签。
- **DTO 线格式**：按契约/任务书字面 snake_case（`order_key`/`amount_cents`/...），与后端 im 端点的 camelCase 不同（已核实 `services/control-api/src/cloudctl_api/im_routes.py` 是 camelCase；订单契约查询参数与字段清单均为 snake_case）。
- **页面** `OrdersView.vue`：设备下拉复用 im 的 `loadDeviceOptions` 模式（`createControlApiClient().devices()` + `mapControlDevice`）；方向（全部/SOLD/BOUGHT）与 status_text 文本过滤；表格列 order_key / item_title / buyer_name / 金额（分转元）/ status_text / occurred_at（`toLocaleString('zh-CN')` 本地化）；行点击展开快照详情（字段 dl + raw JSON `<pre>`）；手动刷新；「加载更多」分页（limit=20 偏移翻页，显示「已加载 x / 共 y 条」）。
- **fail-closed**：`listOrders` 未配置 Control API 时直接抛错不发请求；后端报错如实展示错误消息，错误态下不渲染空态文案、不渲染任何占位数据；空态仅在成功加载且 total=0 时出现。已用测试钉死（错误态断言 `queryByText(/暂无订单/)` 为 null）。
- **采集入口**：最小实现——按钮禁用 + 文案「采集入口待真机定位器验证后启用（订单列表定位器未验证，fail-closed）」（契约 §7）。API 封装已就位，slice 2 可直接接线。
- **路由**：`{ path: '/orders', name: 'orders', component: OrdersView, meta: { title: '订单同步', section: '运营目录' } }` 注册进 coreRoutes。

## 门禁（真实执行记录）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `pnpm install --frozen-lockfile`（worktree 根） | 0 | Done in 2.6s |
| `pnpm --filter @cloudctl/api-contracts build`（前置，生成客户端 dist，未改其源码） | 0 | tsc -p 通过 |
| `pnpm --filter @cloudctl/web test` | 0 | **176 passed / 32 files**（基线 155 + 新增 21：orders-api 12 + orders-view 8 + router +1） |
| `pnpm --filter @cloudctl/web typecheck`（vue-tsc -b） | 0 | 无错误 |
| `pnpm --filter @cloudctl/web build` | 0 | built in 2.62s（chunk 体积 warning 为既有） |
| `pnpm --filter @cloudctl/web lint`（非门禁项，参考） | 1 | **基线既有失败**：`ScheduleEditor.vue:16`、`product-fields.ts:103` 等未改动文件的 no-unused-vars error；我的 6 个文件 0 error 0 warning |

### 基线差异说明

- 基线实测与任务书一致（155 passed）。注意：跑测试前必须先构建 `@cloudctl/api-contracts` 的 dist（该包 main 指向 dist，worktree 无缓存产物），否则 10 个测试文件报 "Failed to resolve entry"。此为环境前置步骤，非代码缺陷。
- lint 在基线 `d942bd3` 上即为 fail（pre-existing errors），与本次改动无关，且不在门禁清单内。

## 测试覆盖（任务书要求项）

- DTO 请求参数拼装：`orders-api.spec.ts`「assembles snake_case query params and omits empty filters」+ view 级「reloads from the first page when the direction filter changes」。
- 金额分转元：`formatOrderAmount` 整数运算无浮点漂移（12345→¥123.45、5→¥0.05、-150→-¥1.50、null→—）；view 渲染断言 `¥123.45`。
- 空态/错误态 fail-closed 渲染：错误态展示错误且无假数据/无空态；空态仅在成功空加载时出现；未配置 Control API 时零请求直接抛错。
- 另覆盖：404 语义、422 detail 扁平化、500 透传、collect 的 Idempotency-Key + snake_case body、run 查询、展开/收起详情、加载更多 offset 翻页、设备下拉装载、采集按钮禁用态。

## 未决项

1. **DTO 线格式假设**：契约 §2/§4 与任务书给的是 snake_case 字段清单，本实现按字面 snake_case；W1 后端若最终套用 im 的 camelCase 序列化（alias=camel），需要对齐重命名（api 模块集中在一处，改动成本低）。
2. **collect / runs 响应形状**：契约 §6 只冻结了入参与 run_id 幂等（uuid5），未冻结响应视图。`XianyuOrderCollectResult` 按 `{run_id}` 最小假设；`XianyuOrderRunView` 为宽松透传（`[key: string]: unknown`），W1 冻结 run 视图后收紧。页面采集按钮未接线（禁用态），等真机定位器验证（契约 §7）。
3. **侧边栏导航入口未加**：`OperationsShell.vue` 不在本任务 owned paths，未越界；`/orders` 已可通过 URL 直达并注册进 coreRoutes，建议总控集成时在侧栏补一行链接（与 /im 同款 `yy-catalog-link`）。
4. `status_text` 过滤为前端直传后端子串匹配，未做防抖（@change 触发即查询），与 im 页过滤交互一致。

## 下一步

- 等 W1 后端合入后做真实联调（重点核对 §4 响应字段大小写与 total 语义）。
- 真机定位器验证（总控持 DEVICE 锁）后启用采集按钮并接 run 状态轮询。
- 建议总控在 OperationsShell 侧栏补 `/orders` 导航入口。

---

# 集成修正（integration fix，2026-09-15 第二轮）

- 本轮 BranchSHA=220e3ea（`agent/order-web`）；前一轮交付 SHA=2353cbc。
- 裁决依据：W1 后端已合并（`afca8c2`），响应线格式为仓库 camelCase 惯例，总控裁定以 W1 实测线格式为准，W3 修正。

## 步骤 0：合入集成分支

`git merge integration/p14-20260909` → 干净合入（exit 0，无冲突），带入 W1 后端 + 总控提交（含 `da63740 web: add /orders sidebar entry`，侧栏入口已由总控补上，前一轮未决项 3 关闭）。我的两个提交已在集成分支中，无重复。

## W1 实测线格式（源码核实，与裁决一致）

1. `GET /api/v1/orders` → `{"items":[…],"total":n}`，item 字段 camelCase：`id, deviceId, platform, direction, orderKey, itemTitle, buyerName, amountCents, statusText, occurredAt, createdAt, updatedAt`（`orders_service._order_view`，无 tenantId）；**列表项不含 raw**。
2. `GET /api/v1/orders/{id}` → 同上 + `raw`；404 → `order was not found`。
3. 查询参数保持 snake_case（W1 `Query` 参数即 snake，未改）。
4. `POST /api/v1/xianyu/orders:collect`：请求体 `{device_id, direction, max_rows}` 未改（后端 populate_by_name 双兼容）；响应 201/200 + 头 `Idempotency-Replayed: false|true`，体含 `runId`、`taskIds`、`tasks[{taskId, state, …}]`（state=businessState 回退 status）。
5. `GET /api/v1/xianyu/orders/runs/{run_id}` → `{runId, deviceId, direction, maxRows, commandType, taskCount, summary, allTerminal, tasks[{taskId, state, runnerStatus, errorCode, stallReason, createdAt, completedAt}]}`。

## W3 修正内容（commit 220e3ea，4 files +273 -92）

- `apps/web/src/api/orders.ts`：`OrderRow` 全字段改 camelCase；新增 `OrderDetail = OrderRow + raw`（对齐列表无 raw / 详情有 raw）；collect 结果类型对齐 W1 形状并把 `Idempotency-Replayed` 响应头解析为 `idempotencyReplayed`；runs 视图按 W1 冻结形状收紧（保留索引签名前向兼容）；request 辅助重构为 `performRequest` 以透出响应头。查询参数拼装与 collect 请求体**未动**。
- `apps/web/src/views/OrdersView.vue`：行取值全部改 camelCase；行展开改为按需 `fetchOrder(id)` 拉 raw（列表行已无 raw 字段），带过期响应守卫、加载态与 fail-closed 错误态（详情拉取失败不渲染占位 raw）。raw 详情/空态/错误态行为语义不变。
- `apps/web/tests/orders-api.spec.ts`：fixture 拆为列表行/详情两套（camelCase）；新增 collect 重放头解析、runs camelCase 形状断言（12→13 个测试）。
- `apps/web/tests/orders-view.spec.ts`：断言 camelCase；新增「详情拉取失败 fail-closed」用例（8→9 个测试）。
- `apps/web/tests/router.spec.ts`：本轮无改动（集成未动 web 路由测试）。

## 门禁（本轮真实执行）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `pnpm install --frozen-lockfile` | 0 | Done in 485ms |
| `pnpm --filter @cloudctl/web test` | 0 | **178 passed / 32 files**（上轮 176 + 新增 2：详情拉取失败 api/view 用例） |
| `pnpm --filter @cloudctl/web typecheck`（vue-tsc -b） | 0 | 无错误 |
| `pnpm --filter @cloudctl/web build` | 0 | built in 2.55s |

## 未决项更新

- ~~DTO 线格式假设~~：已按 W1 afca8c2 实测 camelCase 对齐（本轮完成）。
- ~~侧边栏导航入口~~：总控已在集成分支补上（`da63740`），随合并带入。
- collect/runs 响应形状：已按 W1 源码收紧 typing；采集按钮仍为禁用态 + fail-closed 说明，待真机定位器验证（契约 §7）后接线。
- 备注：W1 的 `status_text` 过滤是**精确匹配**（`OrderRow.status_text == status_text`），前端照传原文，placeholder 提示「如：待发货」按精确匹配语义使用。

