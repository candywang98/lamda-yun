# ORDERS-SLICE1-W2 交付报告（Companion Android）

- TaskID: ORDERS-SLICE1-W2
- BaselineSHA: d942bd3
- BranchSHA: 125cd11（代码 commit，契约版本见 commit message；本报告所在为其后的证据 commit）
- OwnedPaths: `mobile/companion/**`（新增单测在 `mobile/companion/app/src/test/`）、`artifacts/tasks/P41-P42-orders/orders-slice1-20260915/w2-android/`（新增）
- ContractVersion: order-sync/20260915.1（冻结版）+ 解析补遗 order-sync/20260915.2（总控真机勘察裁决，仅扩 W2 解析语义）+ W1 对接事实两条（complete 无 resultType、五步形状）

## 交付内容

1. **`ui.readOrders` 步骤**（`AutomationTask.kt`）：参数 direction（SOLD/BOUGHT）、maxRows（1..10）、locatorRef，非法值与未知字段一律解析拒绝；W1 冻结五步形状（ui.tap(profile) → ui.tap(方向入口) → readOrders → screenshot → run.log）解析测试覆盖。
2. **订单行解析 `OrderRowParser`**（新文件 `automation/OrderReading.kt`）：按 20260915.2 裁决实现——
   - order_key = 复合自然键 `{direction}|{对手昵称}|{商品标题}|{amount_cents}`；段内去 \u200b 与首尾空白，标题段截 64，整键截 128；
   - 价格：U+200B 碎片（'¥\u200b'+'1\u200b0\u200b'+'.\u200b8\u200b0\u200b'）按行序拼接去空白、去 ¥ 前缀、十进制转分（"10.80"→1080）；拼接结果不是合法价格则为空，绝不猜值；
   - dump 实测结构处理：行首「订单信息」结构行过滤、「X, X」镜像 desc 折叠、「…，按钮」操作按钮与问卷提示（满意度/满意吗/值不值/表态/评价让）过滤、SOLD 页横幅不依赖（行按容器子节点圈定，天然排除）；
   - NO_KEY：昵称+标题+价格三段全缺才记 skipped_rows（不算失败）；部分缺失空串占位；行数不足 maxRows 读到多少算多少；空列表成功 0 行。
3. **定位器 fail-closed（红线）**（`TargetLocatorRegistry.kt`）：`xianyu_order_list_sold` / `xianyu_order_list_bought` / `xianyu_orders_container` 三个注册条目一律 verified=false——`resolveVerified()` 对它们返回 null，`resolve()` 不认它们（不在已验证表）。两道闸门：
   - `CloudCtlAccessibilityService.resolveUniqueNode` 统一走 `resolveVerified` → ui.find/ui.tap/ui.wait/ui.readOrders 全部 LOCATOR_UNVERIFIED 安全终止（导航 ui.tap(xianyu_order_list_sold) 同样 fail-closed）；
   - `LocalAutomationExecutor.executeReadOrders` 读屏前再查 `isUnverifiedLocator` → LOCATOR_UNVERIFIED、零副作用。
   - 实测锚点规格（20260915.2）已写入注册表注释：入口=我的页 text/content-desc 精确匹配「我卖出的」/「我买到的」（bounds/中心已记录）；容器=「订单信息」行节点集合的实际父节点（行节点**不可点击**，价格 Button 在行内可点击——与契约 §5 原文"可点击子节点"不符处以裁决 dump 为准）。**未预填任何坐标，翻转权在总控。**
4. **节点读取**（`CloudCtlAccessibilityService.readOrderRows`）：行=容器直接子节点中 desc 以「订单信息」开头的可见节点；行数据=子树 text/content-desc 有序行（同节点 text==desc 去重；跨节点不去重以保留重复价格碎片）。
5. **上报接线**：`CloudTaskClient.sendOrders` → POST `/companion/v2/orders/batch`；纯函数 `buildOrdersBatchPayload`（1..20 行守卫、可空字段省略键、raw={lines:[…]}、collected_at ISO）与 `parseOrdersBatchResponse`（accepted/duplicates 必填）在 `network/OrdersBatch.kt`。`CompanionSyncService`：readOrders 步成功（journal SUCCEEDED 之后）立即调 `OrderReporter` → 批量端点；空列表只记 0 行不 POST；上传失败仅日志（含 422 响应体截断），不使任务失败；runNext/runResume 双路径接线。
6. **W1 对接事实①**（`AutomationStore.kt`）：commandType 存在但不在后端 RESULT_TYPES 注册表（一切 `*.steps.v1`，含 `xianyu.collect_orders.steps.v1`）→ complete 事件**整个省略 resultType 字段**；四个已注册 command 型映射与无 commandType 的 legacy 兜底保持不变。

## ChangedFiles（git diff --stat d942bd3..125cd11）

15 files changed, 1145 insertions(+), 13 deletions(-)（main 7 改 + 2 新增；test 4 改 + 3 新增；明细见 `git diff --stat d942bd3..HEAD`）

## 测试（门禁）

- 命令：`cd mobile/companion && GRADLE_USER_HOME="$HOME/.gradle-order-android" ./gradlew testDebugUnitTest`
- 退出码：**0**（BUILD SUCCESSFUL）
- 数量：**337 tests / 0 failures / 0 errors / 0 skipped**（49 个测试类；基线 316 + 新增 21，无新失败）
- 新增 21 例分布：OrderRowParserTest 9（含裁决样本 '1'+'0'+'.8 0'→1080、复合键构造、三段全缺 NO_KEY、镜像折叠、垃圾拼接拒绝）、ReadOrdersExecutorTest 5（LOCATOR_UNVERIFIED 零副作用、NO_KEY 不算失败、空列表 0 行成功、步成功后上报时序、非闲鱼包拒绝）、OrdersBatchTest 3（§3 请求体形状/1..20 守卫/201-200 响应解析）、AutomationTaskParserTest +1（五步形状与 readOrders 参数合法性/非法性）、TargetLocatorRegistryTest +2（fail-closed 与已验证路径不受扰）、AutomationStoreTest +1（steps 型 complete 不带 resultType）。
- 证据文件：`testDebugUnitTest-run.log`（完整控制台输出）、`test-suites.txt`（逐测试类计数）。仓库 .gitignore 约定 `/artifacts/tasks/**` 只留 `*.md`、原始证据本地留存——两文件现留存于本 worktree 同目录；正式归档路径为主仓 `artifacts/tasks/P41-P42-orders/orders-slice1-20260915/w2-android/`（W2 不碰主仓，由总控归档），勘察 dump 依据为主仓 `artifacts/tasks/P09-unknown/xianyu-maintenance-20260915/recon-20260915-2/`。
- 环境备注：独立 GRADLE_USER_HOME=~/.gradle-order-android（未触碰主仓 ~/.gradle）；因本机对 repo.maven.apache.org / dl.google.com 的 TLS 握手反复中断，在该独立目录放 `init.gradle` 用阿里云聚合镜像前置、官方仓库兜底；Gradle 8.10.2 发行包经 curl 下载并核对官方 sha256（31c55713…）；`local.properties`（gitignored）指向本机既有 SDK /Users/wangziheng/CloudCtlExternal/android-sdk。**镜像只影响依赖下载来源，不改变任何代码与测试语义。**

## 未决项

1. **定位器未真机验证，verified=false 待总控翻转**（红线保持）：三个定位器 resolveVerified()=null，任何采集任务在真机上会 LOCATOR_UNVERIFIED 安全终止、零副作用；翻转=按注释中的实测锚点规格把条目移入 xianyuLocators 并移出未验证集合（一个小 diff），由总控装机勘测后执行。
2. 复合 order_key 已知局限（20260915.2 裁决确认接受）：同对手+同商品+同价的两笔订单碰撞去重；slice 2 用订单详情页真实订单号升级。
3. 行字段启发式以两个 dump 为准：标题=剩余候选最长行、昵称=首候选、状态=冻结词表精确匹配；页面改版（新按钮文案/新问卷话术/新状态原文）可能漏滤或漏配，需随真机验收校准。occurred_at 仅识别 yyyy-MM-dd[ HH:mm] 行（两个 dump 中行内无日期，实际恒为空），时区按 +08:00 假设。
4. 批量上报为尽力而为：失败仅日志、无 outbox 重试（slice 1 无订单 outbox；服务端幂等，重采安全）。空列表不 POST（batch 1..20 限制），"0 行"经任务 complete 摘要与日志体现。
5. 单测为 JVM/Robolectric 级：`readOrderRows` 的无障碍树遍历与 LOCATOR_UNVERIFIED 的真机闸门（resolveUniqueNode 路径）无法在单测中实例化真 AccessibilityNodeInfo，由注册表 null 语义 + 执行器闸门测试等效覆盖；**软件测试通过 ≠ 真机采集验收**。
6. 契约 §5 原文"行=列表容器内可点击子节点"与实测（行不可点击、价格 Button 行内可点击）冲突，已按 20260915.2 裁决与 dump 实现，请总控知悉契约文字层面的差异。

## 下一步

- 总控持 DEVICE:b0644fb5 锁装机：装 debug APK → 真机确认五步任务在 fail-closed 下 LOCATOR_UNVERIFIED 安全终止 → 按注释锚点规格翻转 verified → 跑真实采集验收（SOLD/BOUGHT 各一轮）→ 核对 /companion/v2/orders/batch 落库与幂等重放。
- 若真机行结构与两个 dump 有出入（例如问卷/按钮新文案），回给我校准过滤词表与解析规则。

## 需要的锁

- DEVICE:b0644fb5（真机验收串行，由总控持有；本轮 W2 未做任何真机/adb 操作）
