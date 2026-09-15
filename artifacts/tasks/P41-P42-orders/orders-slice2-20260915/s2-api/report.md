# ORDERS-SLICE2-API 后端交付报告

- TaskID: ORDERS-SLICE2-API
- BaselineSHA: 7c5d284（worktree `p14-worktrees/s2-api`，基线核实通过后开工）
- BranchSHA: 712fb5f（分支 `agent/order-slice2-api`，交付提交 `Add order sync slice 2 backend: multi-screen collect (order-sync-slice2/20260915.1)`）
- ContractVersion: order-sync-slice2/20260915.1（`contracts/phase1/order-sync-slice2-20260915.md`，只读未改动）
- 交付时间: 2026-09-15（Asia/Shanghai）

## ChangedFiles（全部落在 Owned paths 内）

| 文件 | 改动 |
| --- | --- |
| `services/control-api/src/cloudctl_api/mobile_schemas.py` | +16：新增 `SwipeUpStep`（`action: "ui.swipeUp"`，LocatorStep 子类，locatorRef 指向列表容器）并加入 `MobileStep` 判别联合 |
| `services/control-api/src/cloudctl_api/mobile_actions.py` | +84/-5：`ORDERS_COMMAND_TYPE_V2`、`ORDERS_MAX_SCREENS=3`、`ORDERS_STEP_ACTIONS` 扩为 `{ui.readOrders, ui.swipeUp}`、`UNPINNED_STEPS_COMMANDS` 加入 v2；新增 `_orders_shape_error_v2` 精确形状校验；`validate_orders_steps` 改为 v1/v2 双形状单命中门禁（零命中 422）。未触碰任何维护形状/维护函数 |
| `services/control-api/src/cloudctl_api/xianyu_orders.py` | +201/-58：collect 入参新增 `screens`（int 1..3 默认 1，非法 422）；`build_collect_orders_steps` v1 输出一字不改（读步骤抽为 `_read_orders` 助手，字段与顺序逐字节等价）；新增 `build_collect_orders_steps_v2`（tap→tap→read→[swipeUp→read]×(screens-1)→screenshot→log）；screens≥2 时 uuid5 run 键材料追加 `:{screens}`（v1 路径保持原推导，跨版本重放不破）；`_stamp_run_fields` 头部 `orderCollection` 仅 v2 增加 `screens` 键；`get_run` 聚合 run 内全部任务的 `ORDERS_READ_*` LOG 事件为 `ordersReadLogs`（非 LOG 事件与其它 LOG 码不进聚合） |
| `tests/integration/test_orders_sync.py` | +402/-9：10 个新用例（见下） |
| `packages/api-contracts/openapi.json` | +48/-0：`uv run python scripts/export_openapi.py` 重新生成（`XianyuOrdersCollectRequest.screens` + `SwipeUpStep` schema + 判别映射） |

无数据库迁移（复用 `xianyu_order` 表，schema 零变更）；未改动 `xianyu_maintenance*`、`mobile_actions.py` 维护部分、`mobile/companion`、`apps/web`。

## 实现要点与契约对照

1. **screens=1（默认）必须生成 v1**：`run()` 在 screens==1 分支调用原 `build_collect_orders_steps`，v1 步骤序列、steps[0] 头部（无 `action` 键、`orderCollection` 四键精确等价）、run_id 推导、响应字段集全部不变（测试逐字段断言固化）。
2. **screens≥2 生成 v2**：序列 `ui.tap(profile) → ui.tap(方向入口) → ui.readOrders → [ui.swipeUp → ui.readOrders]×(screens-1) → ui.screenshot → run.log`；`max_rows` 语义=每屏上限（每个 read 步同值，门禁强制）；swipe 与 read 的 locatorRef 均为 `xianyu_orders_container`（容器内滑动，非全屏）。
3. **屏幕序号不进哈希敏感字段**：read/swipe 步骤字段与 slice1 参数集完全一致（无 `screen` 参数）；屏序只出现在 stepId 命名（`read-orders-2`、`swipe-up-2`，stepId 唯一性是 MobileTaskCreate 硬约束）与运行期 LOG 事件（`ORDERS_READ_N`，payload 携带 `screen=N`）。
4. **幂等**：同 key 同 screens 重放 200（`Idempotency-Replayed: true`，同 runId/taskIds）；同 key 不同 screens 按 uuid5 语义=不同 run 材料→各自新建 201，测试固化（含同 key 回落 v1 的情形）。
5. **形状门禁（仿 W1 的 8 变异 422 模式）**：v2 变异=4 屏超界、缺 swipe、swipe 错位、swipe 错 locator、跨屏方向不一致、跨屏 maxRows 不一致、缺 screenshot、错 log 码，共 8 个全部 422；合法 screens=2/3 原始任务 201 且落库 command_type=v2。游离 `ui.swipeUp`（不在任何冻结形状内）同样 422（`ORDERS_STEP_ACTIONS` 触发）。
6. **runs 聚合可见性（最小实现）**：`GET /api/v1/xianyu/orders/runs/{run_id}` 新增 `ordersReadLogs`（仅当存在 `ORDERS_READ_*` LOG 事件时出现，v1 run 视图字段集不变），逐条含 taskId/sequence/stepId/messageCode/occurredAt；非 LOG 事件与收尾 LOG 不进聚合。分屏上报本身（Companion 每屏读后即调 `/companion/v2/orders/batch`）是 Android 侧行为，本批不做。

## 门禁（真实执行）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `uv run python scripts/export_openapi.py` | 0 | `packages/api-contracts/openapi.json` +48/-0，纯增量 |
| `uv run python -m pytest -q tests/integration/test_orders_sync.py tests/contracts/test_openapi_contract.py` | 0 | 31 passed（orders 30 + openapi 契约 1） |
| `uv run python -m pytest -q`（全量） | 0 | **636 passed, 1 skipped**（基线 626 passed / 1 skipped，+10 全为本批新用例，零新失败） |

说明：worktree 环境需先 `uv sync --extra dev`（pytest 在 dev extra；本机 PATH 的 3.10 pytest 不可用），随后以 `uv run python -m pytest` 执行。ruff 对本批改动文件全绿（`mobile_actions.py` 两处 E501 为基线既有，非本批引入，未动）。

## 新增用例清单（tests/integration/test_orders_sync.py）

1. `test_collect_explicit_screens_one_keeps_v1_shape`：默认与显式 screens=1 均生成 v1，逐字段断言（含响应/头部/存储三处均无 `screens` 键，run 视图无 `ordersReadLogs`）
2. `test_collect_screens_two_generates_v2_shape`：screens=2 完整 v2 形状（动作序列、逐参数、无 `screen` 字段、哈希步数 7、头部含 screens:2）
3. `test_collect_screens_three_bought_generates_v2_shape`：screens=3 + BOUGHT（3 read / 2 swipe / 入口 locator / stepId 命名）
4. `test_collect_screens_validation`（4 参数化 + 显式 null）：0 / 4 / 2.5 / "three" / null 全部 422 且报 `screens`
5. `test_collect_v2_idempotency_same_and_different_screens`：同 key 同 screens 重放 200；同 key 换 screens=3 或回落 v1 均为独立 run（uuid5 语义固化）
6. `test_v2_shape_gate_eight_mutations`：合法 2/3 屏 201 + 8 变异 422
7. `test_v2_run_view_aggregates_orders_read_logs`：claim 后上报 ORDERS_READ_1..3 LOG 事件（含 1 条非 LOG 干扰与 1 条收尾 LOG），run 视图聚合恰好 3 条

v1 不回归：slice1 原 20 个用例原样通过（含真机验收过的形状断言）。

## 未决项

- **Android v2 执行器不在本批**（mobile/companion 由 W4 线持有）：`ui.swipeUp` 作为任务步骤 action 是本批新定义——worktree 内既有 AutomationStep（后端 `MobileStep` 联合与 Android `AutomationTask.kt` 解析器）此前均无 swipe 步骤；契约所称「ui.swipeUp 为既有原语」实为执行器内部原语（`LocalAutomationExecutor.waitFor` 价格定位轮询中调用的 `ui.swipeUp()`），非任务步骤名。本批按契约字面名 `ui.swipeUp` 注册后端步骤类型；当前 APK 收到 v2 任务会安全拒绝（未知 action），符合契约 §5 预期。W4 需在执行器实现：容器内滑动、screen 日志、跨屏 order_key 去重、每屏读后立即批量上报。
- **真机验收待总控**：软件测试通过 ≠ 真机验收（契约 §5 验收边界照旧）。
- 屏序进 stepId 命名（`read-orders-2` 等）是对「screen 只进日志/事件、不进 steps 敏感字段」的字面最小实现——stepId 唯一性是 MobileTaskCreate 硬约束，重复 read/swipe 步必须有区分后缀；若 W4 执行器对 stepId 命名另有要求，改名只影响 stepId 字符串、形状门禁不校验 stepId 取值。
- 同 key 不同 screens 的 uuid5 材料后缀存在理论字符串边界碰撞（如 key=`a:2`+screens=1 与 key=`a`+screens=2 同材料），与 slice1 既有 key 拼接语义同类，未做转义；如需彻底消除由总控定夺。

## 下一步

- W-S2WEB（s2-web 线）：OrdersView 采集按钮启用、`orders.ts` 补 screens 参数（契约 §4）。
- W4 线合并后下一切片：Android v2 执行器（swipeUp 作用于容器、screen 日志、跨屏去重、分屏上报）。
- 总控：v2 端到端真机验收 + OpenAPI 总 regeneration 后恢复严格契约相等门禁。

## 需要的锁

无。
