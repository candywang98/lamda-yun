# ORDERS-SLICE2-WEB 交付报告

- TaskID=ORDERS-SLICE2-WEB
- BaselineSHA=7c5d284（开工核实：`git log --oneline -1` = `7c5d284 contracts: freeze order sync slice 2`，分支 `agent/web-collect`，工作树干净）
- BranchSHA=1a7d6c8（分支 `agent/web-collect`，代码单 commit；本报告为后续 evidence commit）
- ContractVersion=order-sync-slice2/20260915.1 §4（`contracts/phase1/order-sync-slice2-20260915.md`）+ slice1 §8 背景（`contracts/phase1/order-sync-20260915.md`）
- 需要的锁：无

## OwnedPaths（均在授权内）

- `apps/web/src/api/orders.ts`
- `apps/web/src/views/OrdersView.vue`
- `apps/web/tests/orders-api.spec.ts`
- `apps/web/tests/orders-view.spec.ts`
- `artifacts/tasks/P41-P42-orders/orders-slice2-20260915/s2-web/`（本目录）

## ChangedFiles（git diff --stat 7c5d284..1a7d6c8）

```
apps/web/src/api/orders.ts         |  29 +++++-
apps/web/src/views/OrdersView.vue  | 164 +++++++++++++++++++++++++++++-
apps/web/tests/orders-api.spec.ts  |  84 ++++++++++
apps/web/tests/orders-view.spec.ts | 190 +++++++++++++++++++++++++++++++++-
4 files changed, 458 insertions(+), 9 deletions(-)
```

## 实现要点

### orders.ts（契约 slice2 §2 §4）

- `XianyuOrderCollectInput` 新增可选 `screens?: number`；`startXianyuOrderCollect` 请求体在 `screens !== undefined` 时才带该字段（缺省不发 = 后端默认 1，即 slice1 v1 入参兼容）。
- 终态判断辅助，词汇**已核实后端源码**（`services/control-api/src/cloudctl_api/xianyu_orders.py:44` `TERMINAL_BUSINESS = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"})`，未猜测）：
  - `XIANYU_ORDER_TERMINAL_STATES`：冻结词汇导出；
  - `isXianyuOrderTaskTerminal(state)`：单任务终态（空值视为未终态，继续轮询）；
  - `isXianyuOrderRunTerminal(run)`：以后端 `allTerminal` 布尔为权威，缺失时按 tasks 逐个用同一词汇兜底。
- 未动 `@cloudctl/api-contracts` 生成客户端（红线遵守）。

### OrdersView.vue（采集入口启用）

- 控件：设备复用页头现有「设备」过滤下拉（「全部」= 未选设备 → 按钮禁用 + 提示「请先在上方『设备』下拉选择具体设备」）；方向 SOLD/BOUGHT 独立下拉（默认 SOLD）；屏数 1..3 下拉（默认 1）；「开始采集」按钮（busy 时禁用并显示「采集运行中…」）。
- 点击流程：`crypto.randomUUID()` 生成 Idempotency-Key → `startXianyuOrderCollect({deviceId, direction, maxRows: 10, screens?})`（`maxRows` 取每屏上限 10，契约 slice2 §2 语义；屏数 1 不发 screens 字段）→ `window.setTimeout` 链轮询 `fetchXianyuOrderRun`，间隔 2s、总上限 60s（模式仿 OperationsView 的 clearPoll/schedulePoll）。
- 终态处理（fail-closed）：
  - run 终态且全部任务 SUCCEEDED → 提示「采集完成（N 个任务全部成功），已刷新订单列表」并自动 `refresh()`；
  - 终态但有非 SUCCEEDED 任务 → 提示「采集未全部成功：STATE（errorCode）…」逐任务展示，**不**刷新列表；
  - 60s 超时 → 如实提示「采集仍在运行（已轮询超过 60 秒），结果请稍后手动刷新确认」，不算失败也不算成功；
  - 提交失败 / 轮询读状态失败 → `OrdersApiError.message` 原样展示并停止轮询，不吞错。
- run 状态展示：run id 前 8 位 + 每任务 state chip（`data-state`，含 errorCode 括注），轮询每次回包即时更新。
- 轮询清理：`onUnmounted(clearRunPoll)`；旧禁用态说明文案（「待真机定位器验证后启用」）已移除。
- 风格对齐既有页面（yy-field/yy-btn/yy-sub/yy-error + 局部 BEM 样式），零新依赖。

## 门禁（真实执行记录）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `pnpm install --frozen-lockfile`（worktree 首次） | 0 | Done in 3.7s（pnpm 10.15.0） |
| `pnpm --filter @cloudctl/api-contracts build`（环境前置，非门禁） | 0 | tsc 生成 dist（worktree 无缓存产物；不构建则 10 个测试文件 resolve entry 失败，slice1 报告已记录同问题；未改其源码） |
| `pnpm --filter @cloudctl/web test` | 0 | **184 passed / 32 files，0 failed**（基线 178 + 新增 6：orders-view 净 +4、orders-api +2；无新失败） |
| `pnpm --filter @cloudctl/web typecheck`（vue-tsc -b） | 0 | 无错误 |
| `pnpm --filter @cloudctl/web build` | 0 | ✓ built in 2.36s（chunk >500kB warning 为既有，非本次引入） |

## 测试覆盖（任务书要求项 → 用例）

`orders-view.spec.ts`（9 → 13 个）：

1. 未选设备点击禁用：`disables the collect button with a hint until a concrete device is selected`（含旧文案已移除断言）。
2. collect 发起参数含 direction/screens：`starts a collect run carrying the chosen direction and screens (screens=1 omitted)`——断言 `screens: 3` 传入与屏数回 1 时请求体无 screens 字段（toEqual 精确匹配）。
3. 轮询到 SUCCEEDED 后刷新列表：`polls the run to a terminal SUCCEEDED state and refreshes the order list`（fake timers，2 次轮询 RUNNING→SUCCEEDED，listOrders 调用数增加）。
4. 轮询到 FAILED 展示错误码且不刷新：`polls to a FAILED run, surfaces the errorCode and never refreshes the list`（STEP_TIMEOUT 在错误段落与任务 chip 双处展示，listOrders 调用数不变，终态后不再轮询）。
5. 卸载后轮询停止：`stops polling when the view unmounts`（unmount 后快进 60s，fetchXianyuOrderRun 零调用）。

`orders-api.spec.ts`（13 → 15 个）：

6. screens 序列化与缺省省略：`sends screens only when provided (slice2 §2 …)`（body deep equal：带 screens 3 / 不带时无该键）。
7. 终态判断：`classifies run terminality against the backend TERMINAL_BUSINESS vocabulary`（SUCCEEDED/FAILED/CANCELLED/EXPIRED=true；QUEUED/RUNNING/null=false；allTerminal 权威与缺失兜底路径）。

## 未决项

1. **采集设备复用「设备」过滤下拉**：任务书「选设备（复用现有下拉）」按字面实现为复用页头过滤下拉（「全部」→ 禁用+提示）。若总控期望独立采集设备下拉（与过滤互不影响），改动集中在 OrdersView 一处，成本小。
2. **v2 真机执行**：Android v2 执行器（swipeUp 分屏）不在本批（契约 slice2 §5，mobile/companion 由 W4 线持有）；当前 APK 对 screens≥2 任务会安全拒绝。Web 端已按契约放开 1..3，验收边界照旧：软件测试通过 ≠ 真机验收。
3. **max_rows 固定 10**：采集控件未暴露每屏行数（任务书未要求），按每屏上限 10 常量发送；如需可调再扩展。
4. **轮询失败即停**：单次 run 状态读取失败按 fail-closed 停止并展示错误（不静默重试）；如总控期望在 60s 窗口内容忍瞬时错误重试，需明确指示。

## 下一步

- 等 W4 合入 Android v2 执行器后做 screens≥2 真机联调。
- 建议总控在真机验收时跑一次 SOLD/BOUGHT × screens 1/2/3 组合采集核对 Web 轮询展示与自动刷新。
