# 闲鱼维护动作验收报告（擦亮/下架/删除）— 2026-09-15

基线链：`1661a46`（契约冻结）→ `c82e77b`（HEAD，已推送）。设备 OnePlus 9R `b0644fb5`（1080x2400，无障碍绑定正常）。服务端首尔 release `xy-maint-a8e7beb`（迁移 0019/0020 已上，DB 已备份）。

## 一、三动作终态

| 动作 | 结果 | 证据 |
|---|---|---|
| **擦亮** `xianyu.polish.steps.v1` | ✅ **SUCCEEDED** | 任务 `0e1fb98b`：导航（我的→我发布的）→ `LAYOUT_GUARD_PASSED` → 一键擦亮单击 → 截图 → 5 步全绿 |
| **下架** `xianyu.delist.steps.v1` | ✅ **完整 GATED 闭环 SUCCEEDED** | 任务 `63516d24`：intent **201** → 恰好一次确认单击 → **真实下架（在卖 1→0）** → 账本 `confirm-delist APPLIED` → 操作员核验（platformItemId `xianyu-listing-notion-voucher-299-20260915`）→ `CONFIRMED_APPLIED` → SUCCEEDED |
| **删除** `xianyu.delete_delisted.steps.v1` | ✅ **完整 GATED 闭环 SUCCEEDED**（终版，`c82e77b` 坐标重校后） | 任务 `37a665b0`：首卡删除单击命中 → 确认弹窗 → GATED 确认单击 → **真实删除（¥299/13 浏览卡从列表消失，现首卡=¥199/16 浏览）** → 账本 `confirm-delete` → 机器核验 UNKNOWN（弹窗消失信号时序未捕获，**不猜**）→ 操作员核验卡片消失 → `CONFIRMED_APPLIED`（platformItemId+证据）→ SUCCEEDED。此前两次失败尝试（`4d226249`/`6d22dd62`）均安全停 + `CONFIRMED_NOT_SUBMITTED`，零误删 |

## 二、GATED 门禁语义的真机实证（本轮核心资产）

1. **一次授权**：服务端形状校验+账本 intent 201（taskId+命令+steps 哈希+actionId 身份），跨任务身份独立。
2. **恰好一次单击**：确认击只来自账本 effect（executor 侧 return，无本地重试路径）。
3. **不确定不重试**：两次失败场景（intent 409 / 坐标漂移）均停 RECONCILING 等操作员，**真实零副作用**（弹窗原样、商品未删）。
4. **操作员解除**：`platform-tasks/{id}:reconcile` CONFIRMED_APPLIED（需 platformItemId+证据）/ CONFIRMED_NOT_SUBMITTED，审计历史完整。
5. **失败路径死锁修复**：intent 被拒后本地未决行轮询永不存在的服务端行 → claim 队列饿死 → 404 即本地 NOT_SUBMITTED 收尾（`ad74dec`）。

## 三、本轮修复清单（全部有真机证据）

| # | 缺陷 | 修复 | 提交 |
|---|---|---|---|
| 1 | 领取载荷 commandType=null → 身份构造炸 | 创建时从形状校验盖章 command_type；recipe_pin 跳过；intent 身份路径放行 | `8494a3b` |
| 2 | actionId 错位（click-confirm-delist:xxx vs confirm-delist）→ intent 全 409 | 对齐冻结值 | `61d9adb` |
| 3 | 404 死锁（claim 队列饿死） | 404=从未受理=本地 NOT_SUBMITTED | `ad74dec` |
| 4 | 确认弹窗遮蔽 tabs → BADGE_UNREADABLE | 第一击前快照基线仓（MaintenanceBadgeSnapshots） | `01b4055` |
| 5 | 已下架 tab 无数字角标 → delta 断言永不可核 | 删除核验改弹窗消失信号+截图+操作员；下架保留 delta | `9e591af` |
| 6 | 已下架首卡 y 漂移（1207→675，横幅消失） | 重校 675/460（但见待办 2） | `c82e77b` |

## 四、待办（按优先级）

1. **🟡 删除定位的稳健性**：终版验收通过，但布局漂移风险仍在（顶部横幅有无可移动首卡 y 达 532px）。缓解现状=失败安全（UNKNOWN 停+操作员核验）；长期方案：a) 商品详情页「管理」入口（详情页语义锚点丰富，勘得「管理」按钮在售详情页 (936,2245)）；b) tabs 语义 bounds 相对偏移；c) platformItemId 映射（依赖 2）。
2. **商品身份映射**：维护动作目前按 cardIndex 定位；按标题/platformItemId 定位需要列表标题读回（当前卡片无语义暴露）——与 titleContains 编排过滤同源，合并解决。
3. **批量下架**：编排 API 已支持循环；卡 0 之外需要更多行的坐标证据（同漂移问题，随 1 一起解决）。
4. **草稿 tab 坐标**：草稿卡删除/编辑按钮坐标未在当前布局下复验。
5. 订单拉取同步（055 需求）：未开始。

## 五、环境与运维

- 三端基线：后端 606/1 · Android 316/0 · OpenAPI 严格契约恢复。
- 生产：首尔 `xy-maint-a8e7beb` 运行中（146 端点含 maintenance）；DB 备份 `backups-pre-0020-*.csv`。
- 设备：搜狗输入法、无障碍绑定正常、NOTIFICATION 模式；本轮误入的转卖草稿已存草稿退出（用户可在草稿 tab 清理）。
