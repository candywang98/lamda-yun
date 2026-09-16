# ORDERS-SLICE2-ANDROID 多屏采集执行器交付报告

- TaskID: ORDER-S2-WB
- BaselineSHA: 5c4d100（worktree `p14-worktrees/s2-android`，分支 `agent/order-sync-s2-android`）
- BranchSHA: 见下方「提交记录」（代码提交 + 本证据提交）
- ContractVersion: order-sync-slice2/20260915.1（`contracts/phase1/order-sync-slice2-20260915.md`，唯一事实源，只读未改动；slice1 契约 order-sync/20260915.1+补遗 .2 与锚点契约 xianyu-anchors/20260915.1 §3 同样只读）
- 交付时间: 2026-09-16（Asia/Shanghai）
- 验收边界: 软件测试通过 ≠ 真机验收；未触碰 adb/真机/Excel/OpenAPI 重新生成（后端 W-S2API 已完成）

## ChangedFiles（全部落在订单路径，未触碰 PublishedCardLocator.kt / XianyuMaintenance* / 维护删除分支）

| 文件 | 改动 |
| --- | --- |
| `mobile/companion/.../automation/AutomationTask.kt` | +25：新增 `AutomationStep.SwipeUp(stepId, timeoutMs, locatorRef)` 与 `ui.swipeUp` 解析分支（键集精确 = stepId/action/timeoutMs/locatorRef）。任何携带 `screen` 字段（或任何多余字段）的步骤体在解析期即拒绝——companion 侧哈希红线由键集校验承载 |
| `mobile/companion/.../automation/OrderReading.kt` | +44：`OrderReporter.reportOrders` 增加 `screen: Int`（仅日志通道）；新增纯函数 `OrderSwipeGeometry`（容器 bounds → 容器内一屏上滑行程，零 Android 依赖可单测） |
| `mobile/companion/.../automation/LocalAutomationExecutor.kt` | +99/-10：`LocalAutomationUi.swipeUpWithin(targetPackage, locatorRef)` 新原语（默认 fail-closed）；`executeSwipeUp`（xianyu-only 守卫、§7 LOCATOR_UNVERIFIED fail-closed、LOCATOR_NOT_FOUND 步窗重试）；`executeReadOrders` 分屏化（跨屏 order_key 去重、screen 计数、ORDERS_OVERLAP_N 日志、多屏任务才发 ORDERS_READ_SCREEN_N）；`reportPendingOrders` 逐屏冲刷并携带 screen |
| `mobile/companion/.../automation/CloudCtlAccessibilityService.kt` | +32：`swipeUpWithin` 真机实现——解析定位器节点的 live bounds，`OrderSwipeGeometry` 映射出行程后单次 `dispatchStroke`（500ms + 250ms 稳定），退化 bounds 抛 `SWIPE_BOUNDS_INVALID`、手势取消抛 `SWIPE_DISPATCH_CANCELLED`；全屏 `swipeUp()` 在该路径不可达。仅追加订单路径方法，维护代码零触碰 |
| `mobile/companion/.../service/CompanionSyncService.kt` | +16/-7：`orderReporterFor` 日志行加 `screen=N`（§3 上报载荷形状不变，逐字段沿用 buildOrdersBatchPayload） |
| `mobile/companion/.../test/.../ReadOrdersExecutorTest.kt` | +1：RecordingReporter 适配新签名（slice1 用例语义零改动） |
| `mobile/companion/.../test/.../CollectOrdersSlice2Test.kt` | +514：新测试套件，10 个用例（见下） |

## 实现要点与契约对照

1. **steps v2 解析（§1）**：`ui.swipeUp` 键集 `stepId/action/timeoutMs/locatorRef`，与后端 `build_collect_orders_steps_v2` 冻结输出逐字段对齐（swipe/read 的 locatorRef 均 `xianyu_orders_container`，timeoutMs 8000/20000 映射由后端下发）。v1 五步形状与行为完全保留（既有 AutomationTaskParserTest/ReadOrdersExecutorTest 全部原样通过）。未知/非法形状解析期拒绝、零副作用。
2. **容器内滑动（§1 + anchors §3）**：执行器只调 `swipeUpWithin(locatorRef)`；真机实现从解析到的订单容器节点 `getBoundsInScreen` 推导行程（竖直中线，容器高 80%→20%，即一屏 60% 行程+滚动重叠余量），**不存在全屏坐标路径**；`waitFor` 价格定位的既有全屏 `swipeUp()` 原语未被本路径触碰。
3. **分屏即报（§3 断点续传语义）**：沿用 slice1 的「readOrders 步 SUCCEEDED 后立即冲刷」机制，天然逐屏——每屏 ≤10 行满足 batch 1..20；后屏 swipe/read 失败时前几屏已 POST `/companion/v2/orders/batch` 落库（测试固化：后屏 LOCATOR_NOT_FOUND 时 reporter 恰好收到前屏调用）。
4. **跨屏去重（§3）**：run 内 `reportedOrderKeys` 累积**前几屏**已上报键；重叠行跳过（不重复上报、不计 duplicates、不进 skipped），新行照常上报；**同屏重复键保持 slice1 语义**（都上报，服务端幂等吸收）——`runsWithoutReporterAndNeverUploadsTwice` 原样通过即证。暂停/恢复后去重集合重置，重叠行重报由服务端幂等兜底（契约允许，整任务重跑安全）。
5. **哈希红线（§1）**：screen 序号三个不可达通道——(a) 步骤模型无 screen 字段（键集精确解析，多余字段拒绝，测试注入 `,"screen":2` 验证）；(b) `OrderSwipeGeometry`/`swipeUpWithin` 只收 locatorRef；(c) 上报载荷（buildOrdersBatchPayload）未动。序号仅出现在执行器 LOG（`ORDERS_READ_SCREEN_N`，多屏任务才发，v1 日志字节级不变）与 CompanionSyncService 日志行 `screen=N`。steps[0] 头部元数据在服务端 `_task_view` 即剥离，从不抵达 companion。
6. **readOrders 行解析（§1 沿用 slice1）**：direction/maxRows 1..10/locatorRef 语义、OrderRowParser、NO_KEY 跳过、空读成功全部未动。

## 门禁（真实执行）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `cd mobile/companion && GRADLE_USER_HOME="$PWD/.gradle" ./gradlew testDebugUnitTest` | 0（BUILD SUCCESSFUL） | **61 套件 / 419 测试 / 0 失败 0 错误 0 跳过**（基线 60 套件 / 409 测试；+1 套件 +10 用例全为本批新增，XML 汇总脚本统计确认） |

环境说明：worktree 缺 `local.properties`（gitignored），从主工作区复制 `sdk.dir=/Users/wangziheng/CloudCtlExternal/android-sdk` 后首跑；首次门禁跑出 2 个**本批测试自身的用例 bug**（JSON 变异串多一个尾引号、failSwipeOnScreen 序号写错），修正后全绿——生产代码零返工。

## 新增用例清单（CollectOrdersSlice2Test，10 个）

| # | 用例 | 覆盖要求 |
| --- | --- | --- |
| 1 | parsesMultiScreenV2ShapesForTwoAndThreeScreens | ① screens=2/3 形状（类型序列、stepId、容器 locator、跨屏 direction/maxRows 一致） |
| 2 | rejectsIllegalV2StepShapesBeforeAnyExecution | ① 非法形状安全拒绝：readOrders 带 `screen` 字段、swipeUp 缺 locatorRef、locator 非法字符、重复 stepId、maxRows 越界 |
| 3 | v1ShapeAndSingleScreenBehaviorAreUnchanged | ② v1 回归：五步形状 + 单屏行为（同屏重复键不去重、日志无 SCREEN/OVERLAP 行） |
| 4 | reportsEveryScreenImmediatelyAfterItsStepSucceeds | ③ 3 屏全成功：report 紧跟每屏 SUCCEEDED、先于下一屏任何步骤 |
| 5 | keepsEarlierScreenReportsWhenALaterScreenFails | ③ 后屏 read 失败 / 后屏 swipe 失败：前屏已报、任务以 LOCATOR_NOT_FOUND 终止 |
| 6 | absorbsCrossScreenOverlapRowsByOrderKey | ④ 重叠行吸收：屏 2 只报新键、skipped 空、ORDERS_OVERLAP_2、合计 3 唯一键 |
| 7 | swipesOnlyInsideTheResolvedContainerAndNeverFullScreen | ⑤ 执行器只调 swipeUpWithin(容器 locator)，全屏 swipeUp() 调用数 = 0 |
| 8 | containerSwipeGeometryStaysInsideTheContainerBounds | ⑤ 行程严格落在容器 bounds 内（多组容器）、退化 bounds → null fail-closed |
| 9 | failsSwipeUpClosedOnUnverifiedLocatorOrForeignTarget | ⑤/§7 LOCATOR_UNVERIFIED 与非 xianyu 目标：零滑动零读取安全终止 |
| 10 | screenOrdinalReachesLogsOnlyAndNeverStepBodiesOrReports | ⑥ 序号只进日志（ORDERS_READ_SCREEN_1/2），上报行/readCalls/swipe 调用均无 screen 通道 |

## 提交记录

- 代码提交：`c1c144f` "companion: order-sync slice 2 multi-screen executor (steps v2)"（7 文件 +721/-10）
- 证据提交：本文件（`artifacts/tasks/P41-P42-orders/orders-slice2-20260915/s2-android.md`）

## 未决项 / 移交总控

1. **真机验收未做**（验收边界照旧）：容器内滑动手感（60% 行程 + 250ms 稳定）是否足够稳定地翻屏、Flutter 惯性下重叠比例、`SWIPE_BOUNDS_INVALID` 是否在真机横幅出现时误触发——需总控持 DEVICE 锁串行验收后冻结。
2. `xianyu_orders_container` 已是 verified（slice1 翻转），本批未动注册表；`xianyu_order_detail_container` 仍在未验证集，未触碰。
3. LOG 事件到服务端 `ordersReadLogs` 的透出依赖 STEP/LOG 事件通道现状（本批只保证执行器产出 `ORDERS_READ_*` 码，run 视图聚合为后端已有实现）；如真机验收发现 LOG 事件未上行，属事件管道而非本批范围。
4. 合并顺序：本分支只改订单路径，与维护线（W4）无共享文件冲突；`ReadOrdersExecutorTest.kt` 签名适配（+1 行）是唯一触碰的既有测试文件，合并时如遇维护线同文件改动需以本分支签名（含 screen 参数）为准。
