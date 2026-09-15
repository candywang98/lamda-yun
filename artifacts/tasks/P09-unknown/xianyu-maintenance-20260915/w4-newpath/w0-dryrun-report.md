# W4 新路径无意图安全干跑 + gate 降级修复 — W0 总控 2026-09-15

设备 OnePlus 9R `b0644fb5`，生产首尔 `maint-v2-c13aad8`（后续 gate 修复在 `876e4a7`）。生产 APK 链：`8deb5dd`（定位器翻转）→ `876e4a7`（gate 降级）。

## 干跑结果（task 68437f3f，v2 delist「海底两万里」，零 GATED intent）

| 环节 | 结果 |
|---|---|
| 步骤 0-6（导航→tapCardByTitle 标题定位→详情→管理按钮→菜单「下架」） | **全部 SUCCEEDED**——新路径机构真机验证通过，语义定位器（管理按钮 desc/菜单文本/标题卡片）全部命中 |
| 第 7 步（GATED 确认） | 确认弹窗「确定要下架这个宝贝吗？」出现；**确认单击从未发生**（无 intent） |
| 副作用核验 | 在卖 tab 187 不变；弹窗由操作员点取消关闭——**零副作用** |
| 任务终态 | FAILED/BADGE_UNREADABLE（终态，账本无 intent 无需裁决） |

## 发现并修复的集成缝

**BADGE_UNREADABLE 硬失败**：v2 确认发生在详情页，tabs 结构性不可见 → 角标基线（tapCardByTitle 时 best-effort 采集）缺失时 gate 硬失败。若不修，授权真机验收会「动作成功但任务报失败」。

修复（`876e4a7`，XianyuMaintenanceCommitGate）：
- payload `commandType` 以 `.steps.v2` 结尾且基线缺失 → `GATED_BADGE_UNKNOWN` 日志 + baseline=null，**不再抛 BADGE_UNREADABLE**
- postcondition 在 baseline=null 时仅采集操作员凭证截图并返回 null → `requireEvidence` 失败 → **持久化 UNKNOWN → 停 RECONCILING → 操作员核验**（P09 删除先例语义）
- v1 路径行为不变（仍硬失败保安全）；effect 闭包/账本恰好一次语义零改动——本修复只能把硬失败弱化为安全停，不可能引入误击

验证：Android 全量 BUILD SUCCESSFUL（356+）；权威验证=授权真机验收（届时若机器核验 UNKNOWN，操作员按 platformItemId+截图 CONFIRMED_APPLIED）。

## 状态

- 新路径已具备授权验收条件（等用户逐件授权对象）
- 建议授权：下架=「海底两万里」（在卖 ¥8.88，可逆）；删除=已下架 tab「如果历史是一群喵4」或「13」（已下架，删除无在售影响）
