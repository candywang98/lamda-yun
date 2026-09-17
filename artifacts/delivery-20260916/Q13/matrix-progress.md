
## 发布草稿（A 机，open-only 到确认点）— 2026-09-17 12:13 本地

- 任务 `6cbb24a7-dc04-4aff-b966-84d82d168aad`（xianyu.publish_listing.v1，租户 1111，复用 Q03 资产：product 01a0a83d / media [01a0a839,01a0a83c] / account 01a07a1c，价格 ¥19.90）
- 结果：**PAUSED_WAITING_USER @ 2026-09-17T04:13:39Z**（CHECKPOINT_1），服务端 business_state=PAUSED_WAITING_USER
- 确认点表单：2 张媒体图已挂、描述「Q13五机验收草稿对象…」已填、价格 ¥19.90、发布按钮高亮未点（截图 A_confirm_point_20260917.png）
- 证据：`publish-draft/A_confirm_point_20260917.png`、`A_run_journal_6cbb24a7.txt`（27 行：wait-home→…→CHECKPOINT_1→PAUSED_WAITING_USER）

### 过程事故与缺陷记录（FLEET-20）
1. **wait-home 无超时挂起**：前一订单采集任务把 App 留在「卖出的宝贝」页，发布 recipe 首步 wait-home 等「卖闲置」contentDescription 9 分钟不通过；graph maxDurationMs=600000 未被本地 runner 强制执行 → 任务 RUNNING 挂死、lease 被心跳无限续期。人工 adb BACK×5 导航回首页后 5 秒走完全程。整改建议：B 线补 wait 类步骤本地 watchdog（maxDurationMs 强制）+ wait-home 失败自动回首页恢复。已记 tasks.json 缺陷清单。
2. **取证纪律**：「表单已填充」的早期判断来自过期截图（draft_A.png 为 Q03 时代文件），本地 run_journal 证明该任务当时根本未开表单。教训：结论只认当次截屏+journal 时间戳。

## 真实商品发布（A 机）— 2026-09-17 12:43 起（进行中）

用户决策：不发布测试文案，改用云控平台内真实商品「Notion Business 一年免费兑换」¥199（product 01a07a78，媒体图 01a07ace JPEG 67KB 已核验），并授权**真发布**。

- 测试任务 6cbb24a7 收尾：服务器侧 UPDATE 为 CANCELED（旧行备份 /home/ubuntu/task_6cbba7_backup…txt）；设备侧本地库因手术推送截断触发应用自愈重建（凭据在 shared_prefs/Keystore 未受影响，心跳全程正常）；探针 ab7e1241 25 秒 SUCCEEDED 证明队列解堵。
- 真实任务 7bee743a（Idempotency-Key q13-real-A-1）12:43:16 领取，媒体 12:43:17.9 入图库。
- **FLEET-21 异常（待根因）**：屏幕表单已被完整填好（1 图+真实文案+¥199，两次独立截屏确认），但执行器 journal/runtime/事件流均停在 wait-home STARTED（12:43:18 起）且 logcat 无任何 tap/input 动作。任务将因 maxDurationMs=600s 于 12:53:18 超时终态化。疑点：存在 journal 之外的 UI 填充路径（旧 steps VM？），或 journal 写入路径与实际执行不一致。整改归 B 线，发布后专项根因。
- 修正 FLEET-20 表述：maxDurationMs 由 withTimeout 强制执行（600s），此前「未强制」判断有误；实际缺陷降级为「wait-home 被动等待可耗尽全部预算、无主动回首页恢复」。

## 真实商品发布结果 — 2026-09-17 13:02 完成

**「Notion Business 一年免费兑换 ¥199」已在闲鱼上架（在售）**，A 机账号，图片为平台媒体资产 01a07ace（JPEG 已核验）。证据：`publish-draft/A_real_product_live_20260917.png`（我发布的列表页，1 件在售）+ `A_real_product_confirm_20260917.png`（发布前确认点表单全分辨率）。

任务台账：
- 7bee743a 服务器侧终态 FAILED/STEP_TIMEOUT（600s 兜底），与业务结果不一致——表单实际已被完整填充并在 12:56 第一次 tap(540,2280) 时成功提交发布；后续 6 次 tap「无效」实为屏幕已离开表单、分析误读。终态 FAILED 自然解除队列阻塞，无需再次手术；postop 探针 9d8b60b1 SUCCEEDED 证明队列健康。
- 6cbb24a7（测试草稿）CANCELED（服务器操作员取消，行备份 /home/ubuntu/task_6cbb24a7_backup_20260917.txt），未发布。

**FLEET-21 待根因**：12:43:17.9 媒体入图库后、12:43:20 前表单被完整填充（含 graph 不含的 ¥199 价格字段），但 journal/runtime/事件流/logcat 均无任何执行记录（执行器显示停在 wait-home）。唯一可疑填充路径：旧 steps VM 或引擎内不落 journal 的分支。整改归 B 线：执行路径必须全程可审计（每步 journal+事件），并补 wait-home 主动回首页恢复（FLEET-20 合并整改）。

**取证纪律 v2**：低分辨率缩略图的 analyze_image 结论会顺着提问预期幻觉（本案 6 次「仍在表单页」误读导致无效 tap 循环）；页面状态必须以 uiautomator dump（无障碍树，机械）为准，图像分析只做辅助。

## FLEET-22 死锁 E2E（A 机）— 2026-09-17 14:15 CST 通过

RUNNING wait-home → `:pause` 4s 内 PAUSED_WAITING_USER → `:cancel` 立即 CANCELLED → 本地 ~1s SERVER_TERMINAL 退役 → 探针 `0ebe2805` 4s SUCCEEDED。任务 `dbaf3763`。证据：`deadlock-e2e-20260917.md` + `publish-draft/A_run_journal_dbaf3763.txt`。

下一棒：B 机（15faee1d / 9b095c03，租户 0001）open-only 草稿到确认点（不点发布）。阻塞：租户 0001 无 product/media；B 心跳 `accessibilityEnabled=false`，控制台「无障碍执行器未开启」。

## B 机草稿第一次尝试 — 2026-09-17 14:32 CST **未到确认点**

前置已做完（无需用户再授权资产）：
- 租户 `00000000-0000-0000-0000-000000000001` 克隆真品：media `01a0ae0e-404e-7e83-bb3b-132461dbbb62`（JPEG sha256=`61ac64612dceadbe…` 与 A 图 01a07ace 相同）、product `01a0ae0e-7ed4-7653-b539-6e6e011ebb3e` 标题/正文/¥199 与 01a07a78 一致。
- B 无障碍经设置页打开：Enabled+Bound `CloudCtl structured automation`（adb `settings put` 因无 WRITE_SECURE_SETTINGS 失败，走了控制台「去开启」）。

任务 `b9eef839-b76d-47c6-b010-768a4605fcb8`（Idempotency-Key `q13-draft-B-openonly-1`）06:32:53Z QUEUED → 06:32:55Z RUNNING → wait-home ~66s STEP_FAILED → 06:34:04Z FAILED。本地 journal：TASK_CLAIMED_LOCAL → wait-home STARTED → STEP_FAILED → TASK_FAILED；inbox TERMINAL_CONFIRMED/FAILED。**未点发布。**

阻塞：**闲鱼首页出现「马上登录」遮罩**，树中无 `卖闲置`。证据：`publish-draft/B_xianyu_login_prompt_20260917.png` + `B_run_journal_b9eef839.txt`。Q11 账号占位 `q11-device-b-placeholder` 仍是 BOUND，但设备侧闲鱼未登录（或会话掉了）。需要你在 B 机闲鱼登录后才能重派 open-only。
