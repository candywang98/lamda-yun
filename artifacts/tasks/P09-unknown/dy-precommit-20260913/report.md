# P09 抖音图文提交前验证与发布路径确立 — 2026-09-13

Contract: `p09-steps-commit/20260913.1` 扩展到 `douyin.publish_note.steps.v1`（`df335c3`…`2d27ea4` 共 7 个提交）。
**范围：抖音只做提交前验证，不真实发布**（用户指示，同小红书口径）。不主张 DY G3。

## 验证结果

任务 `91d7d91b`（14 步）全部 SUCCEEDED：主页 + → 相机 → 相册 → 默认网格选第 1 格（任务素材）→
下一步 → 图片编辑页 → 下一步 → 笔记编辑器 → 填标题 → 填正文 → 截图取证 → 结束（**未点击「发作品」**）。

读回核验（屏幕逐字）：标题「Notion兑换券199元」✓、正文冻结文案全文（含「发送兑换方式」「支持当面交易」）✓、「发作品」按钮在场=停在发布前 ✓。
设备 OnePlus 9R `b0644fb5`，com.ss.android.ugc.aweme **39.6.0**。首次进入授予了相册权限（人工一次）。

## 定位器（39.6.0 实测验证，升级需重验）

| ref | 锚点 | 类型 |
|---|---|---|
| dy_home_publish | content-desc「拍摄，按钮」（主页 +） | ContentDescription |
| dy_camera_ready | 文本「开直播」（相机页就绪锚点，冷启动 >8s 的判据） | Text |
| dy_camera_album | 文本「相册」 | Text |
| dy_picker_cancel | content-desc「取消」（相册选择页锚点） | ContentDescription |
| dy_gallery_cell_N | 「, 未选中」标记的第 N 个**父容器**（格子覆盖层全 enabled=false/clickable=false，只有父容器可见可手势点击） | IndexedContentDescriptionPrefixParent |
| dy_pick_next / dy_edit_next | 文本「下一步」 | Text |
| dy_edit_page | 文本「贴纸」（编辑页锚点） | Text |
| dy_note_title / dy_note_body | 「添加标题」/「添加作品描述」前缀（原生 EditText） | Text / TextPrefix |
| dy_publish_button | 文本「发作品」（已入发布门禁路由） | Text |
| dy_publish_success | 「发布成功」前缀（未实测，真实发布时首验） | TextPrefix |

## 本次踩坑与修复（平台特性记录）

1. **格子定位**：抖音相册格子的 resource-id 搜索不可用（与 XHS 不同）；选中标记 desc 带尾缀（精确匹配失败）且自身 enabled=false；最终方案=按「, 未选中」前缀索引取父容器。
2. **被动覆盖层点击**：格子覆盖层 enabled=false → Tap 预检放宽为「可见 && !(clickable&&!enabled)」——禁用的可点控件仍拒绝，被动覆盖层放行（b40c16d）。
3. **标题输入过滤器**：抖音标题字段过滤 ¥ 且异步截断（~20 字符，比小红书短）；SET_TEXT 返回 true 但尾部丢失。验证标题用 ≤20 字符且不含 ¥；生产用需按平台约束校验内容。
4. **正文输入**：原生 EditText SET_TEXT 直写（2a6a84b，与小红书同路径），全文落盘成功。
5. **相机冷启动**：点 + 后相机初始化偶发 >8s；用「开直播」锚点 + 15s 超时解决（2d27ea4）。
6. **MediaStore 副本累积**诱发 insert 失败（MEDIA_DOWNLOAD_FAILED/IllegalStateException）：清理相册 CloudCtl 副本后恢复；待办=导出改为按内容寻址 upsert。
7. 相册权限首启弹窗需人工一次（全部照片和视频）。

## 发布门禁（已就绪、未触发）

- `dy_publish_button` 已在 `GATED_PUBLISH_LOCATORS`；服务端 `STEPS_SHAPES["com.ss.android.ugc.aweme"]`（命令类型 `douyin.publish_note.steps.v1`，要求恰好一次发布 tap + `dy_publish_success` 后置 + `dy_note_body` 输入）；后端集成测试（intent 一次授权）通过。
- 真实发布前需：用户逐件内容授权 + 平台风控/实名约束评估（抖音对自动化发布的风控比闲鱼/小红书严格）。

## 证据

| 证据 | 位置 |
|---|---|
| 任务定义（14 步） | `task-request.json` |
| 云端终态 SUCCEEDED | `task-final.json` |
| 编辑器读回 | 屏幕逐字命中（标题/正文全文/发作品在场） |
| 编辑器截图（设备侧，未入公开仓库） | sha256 `4bb0000ddb40a39eb8de5d12f964b3c160b44f33…`，手机 `files/automation-evidence/91d7d91b…/dy_note_composer.png` |
| 相册最新=任务素材 | MediaStore 导出后默认网格第 1 格 |

## 软件门禁

- 后端：`test_p09_action_ledger.py` 40 passed / 1 skipped（含抖音形状授权用例）。
- Android 单测：190 passed / 0 failed（含 DouyinLocatorRegistryTest）。
- 服务端首尔 release `p09-steps-569fed1` 已部署抖音形状；APK 含全部抖音改动。

## 未主张

- 抖音真实发布（G3）、视频类内容（本验证为图文）、话题/地点/标签自动填写、其他平台、删除/扣费。
