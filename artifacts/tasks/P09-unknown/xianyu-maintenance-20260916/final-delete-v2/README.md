# Authorized delete re-run (attempt 2) — UNKNOWN again, wrong-card defect found, zero side effects

- Run ID: 82e99aad-62f7-550f-a312-805730289817；Task: 16c9c527-b519-4561-a2c9-a7b93f08bd1a
- Idempotency-Key: authorized-delete-b0644fb5-miao4-20260916-02
- Target（用户逐件授权）: 《如果历史是一群喵4》 only, action=delete, path=v2
- APK: fc236a2（含 single-shot 加固），installed 2026-09-16 07:11:53
- 前置: 旧任务 a25549e5 已按证据结案 CONFIRMED_NOT_SUBMITTED（07:14）

## 执行时间线（companion logcat + 服务端事件）

1. 07:14:53 `CARD_TITLE_TAP title=如果历史是一群喵4 card=0,2184,1080,2565 scrolls=2 tap=540.0,2280.0`（CARD_PARTIALLY_VISIBLE，安全带钳制）
2. 详情页打开——**但打开的是错误商品《你为什么解不开数学题 谈祥柏》**（见 device-evidence/…/xianyu_delete_confirm_v2.png）
3. 07:14:56 LAYOUT_GUARD_PASSED → 07:14:57 GATED_DESTRUCTIVE_INTENT（门控在**错误商品**的删除弹窗上打开）
4. 单发校验拒绝派发确认手势（弹窗叠加在管理菜单上，窗口稳定校验不通过；无 dispatch 记录）→ 台账 UNKNOWN
5. 07:15:02 服务端 RECONCILING（step 8 无 STEP_SUCCEEDED，符合提交屏障语义）→ 07:18:40 操作员结案 CONFIRMED_NOT_SUBMITTED

## 结果核查（07:2x，ui-check-now.xml / screen-final-check.png）

- 《如果历史是一群喵4》仍在已下架列表 ×1 ✅ 未删除
- 《你为什么解不开数学题 谈祥柏》仍在 ×1 ✅ **未被误删**（门控曾在其弹窗上打开，单发校验拦下）
- 《如果历史是一群喵13》仍在 ×1 ✅
- 在卖计数 187→186（隔夜自然售出/变动，与本任务无关）

## 根因（第 2 次 UNKNOWN 与第 1 次不同）

- 第 1 次（a25549e5）：手势已派发但无取证，无法证明平台效果。
- 第 2 次（16c9c527）：**滚动后卡片节点 bounds 过期**（Flutter 无障碍树滞后/惯性），标题匹配到的 bounds [0,2184][1080,2565] 实际是另一商品；tap 打开了错误详情页。v2 路径**缺少「详情页标题==目标」的二次校验**，错误一路走到门控才被单发校验拦截。

## 建议修复（下一切片，待用户决策）

1. v2 路径卡片 tap 后校验详情页标题包含目标标题，不匹配则 fail-closed 终止（零副作用失败）。
2. tap 前对匹配节点 bounds 做新鲜度复核（tap 前 200ms 重取）。
3. 修复后需新一轮用户授权再做第 3 次删除验收。

## 本目录证据文件

- reconcile-old-response.json / run-created.json / task-latest.json（API 全文）
- companion-logcat.txt / companion-logcat-full.txt / companion-full-raw.log
- ui-after-run.xml / ui-check-now.xml / screen-after-run.png / screen-final-check.png
- device-evidence/files/automation-evidence/16c9c527…/（f3527b…-before.png、xianyu_delete_menu_v2.png、xianyu_delete_confirm_v2.png —— 错误商品弹窗铁证）
