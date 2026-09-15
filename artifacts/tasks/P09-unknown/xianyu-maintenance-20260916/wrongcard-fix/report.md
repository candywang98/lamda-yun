# WRG-FIX-WA — 闲鱼维护 v2 删除路径「错卡」缺陷修复

- TaskID: WRG-FIX-WA（W-A 线 companion 修复子代理）
- Baseline SHA: 5c4d100；分支 agent/wrongcard-fix
- 缺陷证据: `../final-delete-v2/README.md`（2026-09-16 第二次授权删除验收，
  `CARD_TITLE_TAP title=如果历史是一群喵4 card=0,2184,1080,2565 scrolls=2 tap=540.0,2280.0`
  —— 滚动后卡片 bounds 过期，tap 打开了《你为什么解不开数学题 谈祥柏》的详情页，
  门控在错误对象上打开，被单发校验拦下，零误删）
- 契约: `contracts/phase1/xianyu-maintenance-anchors-20260915.md`（冻结锚点，未改动）

## 改动说明（5 个文件，均在维护路径区域内）

| 文件 | 改动 |
|---|---|
| `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/PublishedCardLocator.kt` | 新增纯 JVM 防线逻辑：`BoundsFreshnessArbiter`（防线2 仲裁器）、`boundsWithinTolerance`、`verifyDetailTitle`/`DetailTitleVerdict`（防线1 判定）、`visibleLines`（可见行提取，剪除不可见分支） |
| `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/CloudCtlAccessibilityService.kt` | 仅维护 v2 区域：`tapCardByTitle` 在唯一 tap 前做 bounds 新鲜度复核（150ms settle → 重定位 → 容差比对）；非 Card 失败映射提取为 `cardOutcomeFailure` 复用；新增 `visibleTextLines` 实现（喂给防线1，按目标包过滤 + 可见性剪枝）；新常量 `CARD_BOUNDS_REQUERY_SETTLE_MS=150` |
| `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/LocalAutomationExecutor.kt` | 维护分支 `executeTapCardByTitle`：手势成功后调用新增 `verifyDetailPageTitle`；`LocalAutomationUi` 新增带默认实现的 `visibleTextLines`；新常量 `DETAIL_VERIFY_POLL_MS=400`、`DETAIL_MISMATCH_CONFIRM_POLLS=2`。readOrders 区域零改动 |
| `mobile/companion/app/src/test/.../PublishedCardLocatorTest.kt` | +5 纯逻辑测试（容差/重匹配/2 轮不稳/标题判定/可见行剪枝） |
| `mobile/companion/app/src/test/.../TapCardByTitleExecutorTest.kt` | Fake 建模「tap 后世界离开列表进详情」；+3 测试（错卡 fail-closed 不开门控 / 过渡页读数不误杀 / CARD_BOUNDS_UNSTABLE 直通不重试）；既有正常路径测试补 DETAIL_TITLE_VERIFIED 断言 |

未改动：`XianyuMaintenanceLayout.kt`、`XianyuMaintenanceCommitGate.kt`（本任务无需）、
`AutomationTask.kt`、`OrderReading.kt`、`CloudTaskClient.kt`、`CompanionSyncService.kt`、
service 的 readOrderRows/订单区域（归订单线）。

## 防线设计

### 防线1（主）：详情页标题二次校验 — DETAIL_TITLE_MISMATCH fail-closed

`executeTapCardByTitle` 在 `ui.tapCardByTitle` 手势确认返回后、步骤记成功前执行：

1. 列表页识别：已发布 tab 节点（`xianyu_pub_tab_onsale`/`delisted`）仍可见 = 导航未发生，
   屏上的目标标题只是列表卡文本，不作数；继续轮询（400ms）。
2. tab 消失后读 `visibleTextLines`（活树可见行，不可见分支剪除 —— 被覆盖但仍挂载的
   列表树不会把旧标题泄漏进判定），用与卡片搜索同源的 `contains` 语义判定：
   - 某行包含 `titleContains` → `DETAIL_TITLE_VERIFIED`，步骤成功；
   - 无可读内容 → 仍在渲染，继续轮询；
   - 可读但无片段 → Mismatch；连续 2 次读数一致Mismatch 才终止（防过渡页快照误杀），
     抛 `DETAIL_TITLE_MISMATCH`，message 记 `expected='<目标>' actual='<最长可见行>'`，
     日志 ERROR `DETAIL_TITLE_MISMATCH`。
3. 步窗口耗尽仍不可判定 → `DETAIL_TITLE_UNVERIFIED`（同样 fail-closed）。

效果：错卡链条死在 `open-card-by-title` 步骤内，后续 `open-manage-menu` /
`tap-delete-item` / `confirm-delete`（门控）零执行 —— 事故中「门控在错误商品弹窗上
打开」的路径被彻底切断（单测 ① 直接以事故四步链条断言）。

### 防线2（次）：tap 前 bounds 新鲜度复核 — CARD_BOUNDS_UNSTABLE fail-closed

`CloudCtlAccessibilityService.tapCardByTitle` 在滚动入视循环之后、计算 tap 点之前：

1. `BoundsFreshnessArbiter` 以匹配时 bounds 为基准，每轮 `delay(150ms)` 后
   **全量重定位**（新树快照 + `PublishedCardLocator.locate`，非节点句柄刷新）。
2. 新读数与基准各边 Chebyshev 距离 ≤ 40px（`BOUNDS_FRESHNESS_TOLERANCE_PX`，可调常量）
   → 稳定，用**新鲜读数**计算安全带 tap 点。
3. 漂移超容差 → 采纳新读数并重匹配，最多 2 轮（`BOUNDS_FRESHNESS_REMATCH_ROUNDS`），
   日志 WARN `CARD_BOUNDS_DRIFT`；重定位退化为 NotFound/Ambiguous/Unverified 时沿用
   原 fail-closed 错误码（CARD_TITLE_NOT_FOUND 属暂态，执行器层整体重搜）。
4. 仍漂移 → `CARD_BOUNDS_UNSTABLE`，绝不盲点；该码在执行器层不属暂态集合，直通不重试。

两道防线独立成层：bounds 新鲜度被「内容换、位置不变」的极端复用骗过时，防线1 仍在
门控前拦截；防线1 依赖的页面行读数来自与卡片搜索同一 UiNode 快照模型（同源语义）。

## 测试结果

命令（工作树 `mobile/companion`）：

```
GRADLE_USER_HOME="$PWD/.gradle" ./gradlew testDebugUnitTest
```

- 退出码：0（BUILD SUCCESSFUL）
- XML 解析 `app/build/test-results/testDebugUnitTest/TEST-*.xml`：
  **60 套件 / 417 测试 / 0 failures / 0 errors / 0 skipped**
  （基线 60 套件 409 测试；新增 8 测试 = PublishedCardLocatorTest +5、TapCardByTitleExecutorTest +3）
- 环境说明：worktree 缺未跟踪的 `local.properties`，按主工作树补
  `sdk.dir=/Users/wangziheng/CloudCtlExternal/android-sdk`（git-ignored，未入库）。

新增测试覆盖映射：

| 要求 | 测试 |
|---|---|
| ① 标题不匹配→fail-closed 且不开门控 | `wrongDetailPageFailsClosedBeforeTheManageMenuAndTheGate`（事故链条重演：DETAIL_TITLE_MISMATCH、journal 只剩首步 STARTED、locatorTaps 空、gate.semanticConfirms 空、单次手势不重试、message 含 expected/actual） |
| ② bounds 漂移→重匹配 | `driftedBoundsForceARematchAndTwoAgreeingReadingsTapTheFreshOne`（漂移→Rematch→一致→Stable 用新鲜 bounds） |
| ③ 重匹配 2 轮仍不稳→fail-closed | `persistentDriftFailsUnstableAfterTwoRematchRounds` + `unstableCardBoundsFailClosedWithoutRetry`（CARD_BOUNDS_UNSTABLE 直通执行器不重试） |
| ④ 正常路径行为不变（回归） | 既有 6 个 TapCardByTitleExecutorTest 用例全部通过（Fake 建模 tap 后进详情）；`midRenderDetailReadDoesNotKillACorrectPage`（首次读数为过渡页不误杀）+ `tapsTheUniqueCardAndCapturesTheBadgeBaselineForTheGatedConfirm` 补验 DETAIL_TITLE_VERIFIED |

## 未决项 / 合并注意

- 真机验收未做（本任务禁 adb/push）：40px 容差、150ms settle、400ms 轮询、
  MISMATCH 双读确认等参数需第 3 次授权删除验收时实证；若真机详情页标题被平台
  截断（不含目标片段）会 fail-closed（安全方向的假阳性），届时调 titleContains。
- `CloudCtlAccessibilityService.kt` 虽不在任务书点名的文件列表内，但防线2 必须
  在该文件 `tapCardByTitle`（维护 v2 区域）内接线；改动严格限制在维护 v2 区域 +
  `visibleTextLines` 覆写，未触碰 readOrderRows/订单区域 —— 集成时若与订单线
  同文件改动冲突，按 hunk 归属解。
- 修复后删除验收需新一轮用户授权（final-delete-v2 README 既定流程）。
