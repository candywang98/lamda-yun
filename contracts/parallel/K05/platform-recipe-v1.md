# platform-recipe/v1 契约 — FROZEN 20260916.1

状态：**FROZEN（已冻结）**，版本 `platform-recipe/v1@20260916.1`。起草人：W0 总控；裁决人：用户（2026-09-16，4 项全按建议）。基线 `ce074df`。消费者：A05（闲鱼/小红书发布命令与冻结目标）、B05（最小闲鱼签名 Recipe）、B06（小红书 Recipe）、B07（闲鱼完整字段+水印）、A09（operation 目录逐动作）。上位契约：`contracts/phase1/p14-recipe-version-contract.md`（签名/版本/分发已冻结，本契约不重复、只补平台语义）。

## 1. 范围与边界

- 从**已签名 Recipe 能力**出发定义：平台目标（4 平台）、任务家族归属、发布语义三档、允许定位器引用、MediaDelivery 引用义务、结果身份与版本兼容。
- **不要求定位器全集才能开发**（任务卡口径）：recipe 图可引用已 verified 定位器；未 verified 允许注册但运行时 fail-closed（LOCATOR_UNVERIFIED 零副作用终止）。
- 不做：抖音 CommandType（仅保留 13 个已 verified 定位器与 steps 形状占位）、公众号（纯服务端 API，无 recipe）。

## 2. 平台目标模型（冻结现状）

| 平台 | targetPackage | CommandType | 现状 |
|---|---|---|---|
| 闲鱼商品 | com.taobao.idlefish | xianyu.publish_listing.v1 | builtin open-only + dispatch-xianyu(steps) 双轨 |
| 小红书图文 | com.xingin.xhs | xiaohongshu.publish_note.v1 | builtin open-only；参数 title≤64/body≤4000/tags≤20/mediaAssetIds≤18 |
| 抖音视频 | com.ss.android.ugc.aweme | —（未开） | 13 定位器 verified@39.6.0 占位 |
| 公众号文章 | —（服务端 API） | — | wechat publisher 独立链路，不进本契约 |

CommandType 是封闭枚举、双端冻结（command_v1.py + companion CommandV1.kt + BuiltinRecipes.kt hash 字面镜像）；新增平台必须五处同步（command_v1/command_factory.PRODUCTION_ALIASES/builtin_recipes/companion 双端），缺一即 fail-closed。

## 3. 任务家族与 pin 规则（⚠ 坑1，显式声明）

- **家族 A（CommandV1+签名 recipe）**：首次 claim 同事务冻结 recipe_pin（published 或 builtin fallback）；attempt>0 无 pin → 409。B05/B06 交付物属于此家族。
- **家族 B（legacy steps+受控台账）**：dispatch-xianyu/维护/订单采集；`UNPINNED_STEPS_COMMANDS` 显式 pin=None，由 controlled-action ledger 把守。闲鱼发布现状在此家族。
- 同一 commandType **不得跨家族**；注册 recipe 包时 manifest.commandTypes 必须落在家族 A 枚举内。

## 4. 发布语义三档（⚠ 坑4，本契约核心新增）

| 档 | 语义 | 图形约束 | 允许平台（V1） |
|---|---|---|---|
| open-only | 打开表单填好内容，**停在确认点**，人工点发布 | terminal=checkpoint→WAITING_USER，禁止 commit 动作 | 闲鱼/小红书 |
| 需确认 | 图内含确认步，但确认击必须走既有 GATED/commit_once 机制 | commitActionId 必须指向已注册受控动作 | 仅 Temporal publish-target 既有链路 |
| 自动提交 | 无人工介入完成发布 | **V1 不放开**，未来需单独裁决+G3 授权 | — |

- dispatch-xianyu 现状 `tapsPublish:false` 即 open-only，行为冻结不变。
- **状态机映射表（V1 以记录义务代替自动同步）**：publish_target.state（Temporal 相位机）× mobile business_state 的映射在 B05 验收时以断言表落地；两条状态机不自动同步的现状维持。

## 5. 允许定位器引用（冻结纪律）

- recipe 图引用的 locatorRef 必须来自 TargetLocatorRegistry 既有 namespace（xianyu_*/xhs_*/dy_* + 动态 xianyu_gallery_select_0..49 / xhs_gallery_cell_N / dy_gallery_cell_N）。
- 未 verified（UNVERIFIED 集）允许引用：注册通过、运行时 resolveVerified=null → LOCATOR_UNVERIFIED 零副作用终止。
- **verified 翻转仅 Root/总控**（xianyu-anchors §4）；子代理/recipe 作者不得翻转。
- V1 定位器最小集（可开发门槛）：xianyu 发布链核心（发闲置入口/价格/发布成功/图库选择）+ xhs 10 个全 verified 集；其余允许缺省。

## 6. MediaDelivery 引用义务（⚠ 坑5）

- manifest 遵循 `cloudctl.media/v1`（mobile_service.py:101 形状），items **顺序=下载导出相册顺序=选图 tile 顺序**，禁止重排。
- 平台上限：闲鱼 50（第 0 格快门，tile 从 xianyu_gallery_select_1 起）、小红书 18；超限注册时 422。
- deliveryId 命名规范：`delivery-{platform}-{content_id}-{revision_no}`（沿用现状）；下载端 X-Content-SHA256 三方校验义务（manifest=响应头=落盘重算）不变。

## 7. 结果身份与版本兼容（冻结）

- 结果身份链：`publishTargetId`（盖章进 command_payload）+ `taskId` + `recipe.versionId/sha256`（pin）+ `batch_id`；open-only 档的终态结果=「到达确认点+截图证据」，**不得**报告为「已发布」。
- 版本兼容：recipe 包 manifest.minEngineVersion 与设备 engine 版本不满足 → 任务 fail-closed；canonical hash 三方实现（python builtin/automation-sdk/companion）逐字节一致义务不变；builtin `digest:"hash-pinned-builtin"` 永远进不了签名目录（register_recipe 拒收维持）。

## 8. 裁决记录（用户 2026-09-16 拍板，全按建议）

| # | 事项 | 裁决 |
|---|---|---|---|
| D1 | 闲鱼发布迁移路径 | ✅ dispatch-xianyu(steps) 保留为兼容主路；B05 签名 Recipe 平行实现+验收后切换，切换需单独裁决 |
| D2 | 小红书首发走哪族 | ✅ 家族 A（CommandV1+签名 recipe，open-only） |
| D3 | 自动提交档 | ✅ V1 不放开（open-only/需确认两档足够覆盖 31 目录需求） |
| D4 | 状态机同步 | ✅ 记录义务（映射断言表），不自动同步 |

## 9. 正/负 fixture：`contracts/parallel/K05/fixtures/`（4 个，随本契约冻结）

- `k05-positive-recipe-register.json`：合法签名包注册 201→active 目录下发→companion 三方 hash 校验安装成功。
- `k05-negative-bad-signature.json`：错签/改 hash → 服务端 409 或设备端安装失败 fail-closed。
- `k05-positive-openonly-publish.json`：xhs 发布到 WAITING_USER checkpoint，结果=到达确认点+截图，无「已发布」字样。
- `k05-negative-unverified-locator.json`：引用 UNVERIFIED locatorRef → 注册过、运行时 LOCATOR_UNVERIFIED 零副作用终止。

## 10. 消费者验证命令

- 契约层：`uv run pytest -q tests/contracts/`（recipe 版本契约已有测试归属，见 p14-recipe-version-contract.md §Ownership）
- A05/B05/B06/B07/A09：各实现线交付时按任务卡补（B05 含设备端 RecipePackageManager 安装测试；A09 落 K03 operation_id 后可全链断言）。
