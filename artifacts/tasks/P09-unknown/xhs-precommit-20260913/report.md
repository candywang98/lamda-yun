# P09 小红书图文提交前验证与发布路径确立 — 2026-09-13

Contract: `p09-steps-commit/20260913.1` 扩展到 `xhs.publish_note.steps.v1`（`635e634` + `ecfc186`）。
**范围声明（用户 2026-09-13 指示）：小红书不执行真实发布；本切片止于提交前验证与完整可复用的发布路径。** 不主张 XHS G3。

## 已验证的完整路径（怎么做）

设备 OnePlus 9R `b0644fb5`，com.xingin.xhs **8.50.1**（定位器与版本绑定，升级需重验）。
APK SHA-256 `165006980b251db997ee4e602adb8ac1b83e3d0afae656349583fa4fc3336eb2`。

### 步骤流（任务 9ffe20fc，12 步全部 SUCCEEDED，62 秒）

1. `ui.find`/`ui.tap` `xhs_home_publish`（主页 + 号，content-desc「发布」）→ 后置 `xhs_publish_sheet`
2. 选图 `xhs_gallery_cell_0`（`IndexedResourceId com.xingin.xhs:id/ixd` 第 0 格；任务素材经 MediaGalleryExporter 导出后即相册最新 → 第 0 格，已用 MediaStore 查询证实）
3. `xhs_pick_next`（文本「下一步」，选图页）→ 编辑页锚点 `xhs_edit_page`（文本「贴纸」）→ `xhs_edit_next`
4. 编辑器 `xhs_note_title`/`xhs_note_body`（原生 EditText，**无障碍 SET_TEXT 直接写入**，无需 IME——与闲鱼 Flutter 路径不同）
5. 标题「Notion Business 兑换券 ¥199」、正文冻结文案全文；读回逐字命中（含正文尾部「支持当面交易」）
6. 截图证据 + `XHS_PREPARE_VERIFIED` 结束；**未点击「发布笔记」**（屏幕读回确认存草稿/发布笔记均在，任务停在提交前）

### 若未来要做真实发布（G3），接上已就绪的门禁

- 发布步 `xhs_publish_button`（文本「发布笔记」）已被门禁路由覆盖（`GATED_PUBLISH_LOCATORS`）；
  服务端形状校验（`STEPS_SHAPES["com.xingin.xhs"]`）要求：恰好一次发布 tap + `xhs_publish_success` 后置步 + `xhs_note_body` 输入步；身份命令类型 `xhs.publish_note.steps.v1`；后端集成测试（intent 一次授权、无发布形状拒绝）已过。
- Android 侧 `StepsPublishCommitGate` 已参数化（闲鱼/小红书各自的后置定位器）；身份、INTENT、一次单击、UNKNOWN 不重放、云端解除同步全部复用已验证机制。
- **尚未验证**：`xhs_publish_success`（TextPrefix「发布成功」）是按平台惯例的预置定位器，真实发布时才第一次命中；若不出现则按设计进 UNKNOWN→人工核对，安全。
- 发布前仍需：用户对具体笔记内容/图片的逐件授权（项目规则，不能从笼统授权推断）。

## 本次修复的接入问题

1. `AutomationTaskParser` 目标包白名单缺 `com.xingin.xhs`（TASK_CONTRACT_REJECTED）→ `ecfc186`。
2. ColorOS 在重装/强停后会自动关闭 Companion 无障碍（本轮发生 1 次，用户手动恢复）；生产版 adb 无法写该设置。**运维要求：避免 force-stop；重装后检查无障碍。**
3. 已知待办：每次任务导出素材会在 MediaStore 累积副本（(26)(25)…），长期应改为 upsert/清理；相册「第 0 格=最新」依赖该导出时序。

## 证据

| 证据 | 位置 |
|---|---|
| 任务定义（12 步） | `task-request.json` |
| 云端终态 SUCCEEDED + 事件流 | `task-final.json`、mobile_task_event |
| 编辑器读回 | 屏幕逐字命中（标题/正文全文/存草稿/发布笔记均在） |
| 编辑器截图（设备侧，未入公开仓库） | sha256 `7c284229cedb75478b2c190723ea4d2569728795…`，手机 `files/automation-evidence/9ffe20fc…/xhs_note_composer.png` |
| 相册最新=任务素材 | MediaStore date_added 排序首行即 `01a07ace…` |

## 软件门禁

- 后端：`test_p09_action_ledger.py` 38 passed / 1 skipped（新增小红书形状授权与拒绝用例）。
- Android 单测：188 passed / 0 failed（新增 XhsLocatorRegistryTest 等）。

## 未主张

- 小红书真实发布（用户明确本轮不做）；其他平台；删除/扣费。
- 话题/地点/可见性等可选字段的自动化（本流程用默认值）。
