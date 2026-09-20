# F14 evidence summary

- Task: 小红书图文闭环与草稿策略（软件层）
- Audited: 2026-09-20 (Asia/Shanghai)
- Software status: `SOFTWARE_DONE`
- Acceptance status: `SOFTWARE_ACCEPTED`（真机图文发布与草稿弹窗实测待授权窗口；见下）
- Device acceptance: 授权测试内容逐条确认——真机段未执行

## Delivered (software layer)

- **companion `features/xhs/publish/`**（4 文件 + 11 项 kotlin.test 单测全绿，gradle BUILD SUCCESSFUL）：
  - `XhsDraftPolicy.kt`：草稿对话框显式策略 SAVE_DRAFT/DISCARD_DRAFT/WAITING_USER（默认交人）；DISCARD 仅限"身份已知且本次运行创建"的草稿，未知旧草稿一律不自动删除并升级 WAITING_USER（可解释 reason）。
  - `BoundedBackNav.kt`：有界返回——预算内允许、每次返回需 locator 证据、耗尽即 NAV_BOUNDED_EXIT，杜绝无界 back。
  - `XhsNotePublishSteps.kt`：图文 V1 步骤原语（首页 settle→发布面板→B15 顺序选图→编辑页续行→B14 标题/正文回读证明→草稿检查点→必填检查→最终人工检查点→成功观察），复用 TargetLocatorRegistry 的 8.50.1 实测定位 id；`XhsMediaSupport.VIDEO_PENDING_R00` 显式待定。
  - `XhsNotePublishPlanner.kt`：校验（空图/超18/重复/空标题正文拒绝；视频请求显式拒绝非静默丢弃）；mediaAssetIds 顺序原样冻结为选图顺序契约。
- **后端**：`XiaohongshuPublishNoteParams` 增加图文 V1 最少一图校验（命令构建层生效）；`tests/integration/test_xhs_publish_delta.py` 7 项通过——命令层空图/19图/videoAssetIds/draftPolicy 均 422 且报字段名、顺序冻结；铸造层 mediaAssetIds 顺序透传不变。

## Registered decisions (not silently dropped)

- **BLK-012**：draftPolicy 参数面（SAVE_DRAFT/DISCARD_DRAFT/WAITING_USER 透传）需 params 模型/command factory/PlatformTaskCreate 三层同步放开——单侧加字段会被冻结的铸造严格校验拒绝（实测 422 unknown operation fields 后已回退）。companion 侧默认 WAITING_USER 已满足安全底线；显式策略选择待契约裁决。
- 视频笔记保持 VIDEO_PENDING_R00（R00 裁决待定，BLK-004 关联）。

## Device-line notes (this round, ADB 已恢复)

- A机 b0644fb5 就绪：companion 0.1.0 + 无障碍 on + XHS 8.50.1（与定位器采样一致）+ 抖音 39.6.0。
- 华为 P30Pro：无障碍服务**已绑定**（dumpsys Bound services 在列）但 companion 自检"无障碍执行器未开启"；adb input tap 通道正常（对照诊断：点击"去开启"成功跳系统设置）。BLK-006 修订：病灶=EMUI10 无障碍服务生效链路而非注入通道；该机已有授权账号 Q13-DeviceC-Account（xianyu 已授权）。
- vivo V1962A / 小米 5934418a0821：companion 已装、无障碍未开（5934418a0821 按规严禁作业务机）。

## Verification

- `./gradlew :app:testDebugUnitTest --tests 'com.company.cloudctl.companion.features.xhs.*'` BUILD SUCCESSFUL，11 tests / 0 failures（test-results XML 核对）。
- `pytest tests/integration/test_xhs_publish_delta.py tests/integration/test_publish_commands.py tests/unit/test_command_factory.py` 全绿；ruff 通过。
- 未做任何真机业务操作（无发布/无草稿写入/无自动填单）。

## Remaining acceptance gap

真机上的草稿弹窗实测、图文完整输入与图片顺序回读、发布成功观察——需授权窗口与测试内容逐条确认（Q14/Q16 线）。软件验收不声明真机业务验收。
