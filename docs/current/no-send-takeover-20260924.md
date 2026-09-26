# 2026-09-24 控制者接管与只收不发边界

本记录保存本轮接管事实和复核结论；机器任务状态仍只来自 `tasks.json`。用户已批准原一期全范围推进、停止原会话写入，并授权有备份和回退的部署、数据库迁移、兼容 APK 安装和非发送真机测试。

## 执行边界

- 禁止真实发送，包括聊天按钮、键盘提交、接口、任务、定时器、重试或其他账号代发。真实发送流程仅分析按钮、定位条件、目标校验和提交前停止位置，实际发送待用户补充测试数据并另行授权。
- 本轮不做真实发布、删除、改价、评价、支付、收费、推广和可能触发发布的在线草稿/上传。允许隔离 fixture、mock 和本地测试库验证。
- 系统权限由用户在系统界面授予；不绕过权限、不清手机数据、不覆盖未知签名包。保持单控制者、单设备写入者、租约与 fencing、提交防重和 UNKNOWN 停止核验。
- 五台/十台真机验收不能以现有三台替代；缺账号、测试数据或授权的项如实待验，不阻塞独立软件工作。

## 可恢复代码基线

- 原集成 HEAD：`571ce32a4a4df8720be8c022fcd133baf8be437c`。
- 当前接管分支：`integration/goal-20260924-no-send`。
- 本地检查点：`092c6983e2ef85cb6f7d443b5f34a73353974d17`，保存 111 份现有源码/配置变更。是未验收的保存点，不是发布版本。未推送、未部署。
- 原 IM/输入验收目录及运行证据留在原位；没有清理或覆盖。临时源码归档、逐文件摘要及命令日志保存在当前会话 scratch 的 `goal-20260924/`，不包含生产密钥。

## 本轮实际复核

| 项目 | 结果与证据 |
|---|---|
| Android 软件门 | `./gradlew --offline testDebugUnitTest lint assembleDebug` exit 0；XML 共 163 份、1204 项、0 失败/错误/跳过。日志 `goal-20260924/android-baseline/`。没有安装或运行 instrumentation。 |
| 全仓质量门 | 使用 `PATH="$PWD/.venv/bin:$PATH" make verify` 后 exit 0：Ruff、pnpm lint/typecheck/test、Pyright、mypy、全仓 pytest 全部通过；前端保留 220 条非阻断 warning。 |
| 生产只读核查 | 服务仍为 `p34-571ce32`，数据库 `20260920_0032`；无未取消且未过期的 device_lease、无非终态 mobile_task、无 task_schedule。历史 OUT=23 是存量，不是本轮发送。仅是当时快照，写操作前必须重查。 |
| 手机只读核查 | 三台 USB 在线；OnePlus API34，VOG/ELE API29。OnePlus 生产无障碍已配置，VOG 未启用，ELE 未安装 Companion。没有本轮安装、触屏、发送或授权写入。 |
| 本地设备锁 | OnePlus 留有 `input-verification-20260923` 的 STALE 锁，fencing=3；未抢占、未清除。写操作前须按锁 SOP 复核并处理。 |

## 更正上轮误判

上一轮把“不在 enabled_notification_listeners 中”判定成三台手机都缺少消息接收权限，这个结论不成立。现有 `CloudCtlAccessibilityService` 通过 `AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED` 接收通知，`onServiceConnected` 注册事件类型，`onAccessibilityEvent` 将合法通知写入持久 outbox，并未使用 `NotificationListenerService`。

因此接收准入应验证生产/验收包身份、无障碍服务实际 Bound、目标 App 能产生可见通知、IM 的 NOTIFICATION 配置、绑定及端到端入站证据。不得要求与当前实现无关的通知读取授权，也不得因为 OnePlus 无障碍已配置就断言三机 C6 已通过。

## 下一检查点

1. 修复可复现的软件质量门失败，保留完整命令结果，不删测试、不放宽安全断言。
2. 在禁止真实提交的条件下完成消息/发送链审查与隔离测试；生产/手机写入前核实签名、占用、备份与兼容回退。
3. 完成一期逐任务和逐包验收索引，更新当前入口，缺硬件/外部条件保持待验。

本轮授权范围完成与一期全量验收完成分开记录；任何未实际执行的真机验收不得写成通过。

## 2026-09-24 后续软件推进

- 六类实际子智能体定义（`~/.agents/subagents/*.md`）及 `~/.pi/agent/pi-subagents.json` 逐项读回为 `deepspace/gpt-5.6-sol / high`。应用只读模型登记也确认 deepspace 下存在并启用了 `gpt-5.6-sol`；但本会话实际 Task 启动仍被拒绝为型号不可委派。没有启动成功的子智能体，没有替换为其他供应商的 `custom/gpt-5.6-sol`。待宿主刷新可委派清单后重新验证，不能仅凭配置存在声称运行成功。
- 主控制者完成 F16 一轮追加复核：根据官方文档纠正数字发布状态，增加发布身份校验和并发对账终态保护。最终隔离回归 58 项通过，局部 Ruff/类型检查通过；反向验证确认旧字符串判断漏掉 6 类终态。详见 [F16 证据](../../artifacts/delivery-20260916/F16/summary-20260924.md)。
- F16 仅提升为 `IN_PROGRESS`，整体验收保留 `NOT_RUN`；实际写域、命令和剩余门槛已登记。`plan_guard.py` exit 0，其他任务状态未修改。
- 全仓 `make verify` 已在 `.venv/bin` 工具置于 PATH 后通过：Ruff 619 files、全仓 pytest 1151 passed/11 skipped、Studio 16 passed、Web 311 passed；未关闭 warning 或安全规则。
- 本轮无真实发送/发布、在线草稿或素材上传，无生产部署、迁移、APK 安装或手机触屏。

## 2026-09-24 PostgreSQL 与质量门收口

- 宿主中文 locale 是临时 PostgreSQL 启动失败的根因；五个隔离 fixture 现在对 `initdb`、`pg_ctl`、`createdb` 和清理进程显式使用 `LC_ALL=C`、`LANG=C`、`LANGUAGE=C`。
- A11/A12/Q10/Q12/P14 定向回归真实通过：`99 passed, 7 skipped`。7 个 skip 是真实硬件项，不能以软件模拟替代，也没有把 SQLite 结果冒充 PostgreSQL 行锁证明。
- `PATH="$PWD/.venv/bin:$PATH" make verify` exit 0：Pyright 0、mypy 158 source files no issues、全仓 pytest `1151 passed, 11 skipped`、Studio `16 passed`、Web `311 passed`；前端仅保留既有 220 条 warning。
- 这只收口软件门，不改变 F16/Q13/Q15/Q16/Z10 的设备、账号、部署和外部授权状态；本轮仍未真实发送、发布、上传在线草稿/素材、部署、迁移、安装 APK 或触屏。

## 2026-09-25 Companion 链路增量复核

- 三台物理设备的四个 ADB transport 均在线；OnePlus 的 `b0644fb5` USB 与 `192.168.5.6:5555` Wi-Fi transport 已确认是同一设备。
- OnePlus Companion `0.1.0` 已从 `stopped=true` 恢复，`CompanionSyncService` 前台运行，heartbeat 成功，`runnerState=IDLE`，无平台任务。
- VOG Companion `0.1.0` 已追加开启无障碍服务，并保留既有 `com.sand.remotesupportaddon/.SmartService`；在 `network=Cellular` 上连续两次 heartbeat 成功，`accessibilityEnabled=true`、`safetyBarrier=NONE`。
- ELE 仍未安装 Companion。其 ADB transport 显示 `device`，但远程 shell 连 `echo`、`df` 和包查询均不返回；常规安装、`--no-streaming` 安装、`adb reconnect device` 和 USB 模式重连均未恢复。未重启、清数据或做破坏性恢复。
- 生产只读重查：`active_leases=0`、`expired_uncanceled_leases=0`、`enabled_schedules=0`、`active_previews=0`；`mobile_task` 仅有历史终态。OnePlus fencing `3` 的过期本地锁已按 SOP 解除，以 fencing `4` 建立短期诊断锁并在结束后释放，最终为 `FREE`。
- 本轮仅做 APK 启动、无障碍设置、日志和 heartbeat 诊断；F15/F16 仍为软件/外部验收未完成，未创建、claim、执行或提交任何平台任务。详细证据见 [Companion 链路诊断](../../artifacts/delivery-20260916/F15/companion-link-diagnostics-20260925.md)。

### ELE 恢复后的增量

- 用户侧处理后，主机重启 ADB server，ELE 的无输入 shell 探针已恢复，三台设备仍在线。
- `adb install`、`adb push` 和最小 shell stdin 文件传输仍超时；ELE 仍未安装 Companion，未修改其无障碍设置。ELE 诊断锁已释放为 `FREE`。

### ELE APK 变体确认

- ELE 是华为 `ELE-AL00`。已安装的包名为 `com.company.cloudctl.companion.debug`，版本 `0.1.0`。
- 该 debug manifest 按设计移除了网络、入网界面和 `CompanionSyncService`，只保留本地无障碍执行器；正确服务已绑定。
- 因此它可以用于本地输入/执行器验证，但不能用来证明云端 heartbeat。云链路需要 release/acceptance 变体，不能把 debug 结果提升为生产验收。

### ELE API 29 隔离输入验证结果

- 华为 `ELE-AL00` 已通过系统正常安装 `com.company.cloudctl.inputharness` 和 `com.company.cloudctl.companion.debug.test`；harness 前台只显示空的 `isolated field`。
- `DiagnosticInputDeviceTest` 的包边界测试通过；固定输入测试多次进入但未返回，未产生 `INPUT_VERIFIED`、`DIAG_INPUT` 或字段哈希证明，不能记为通过。
- 已确认兼容性缺口：API 29 使用 `MANUAL_IME`，而 debug manifest 移除了 `CloudCtlInputMethod`；API 30–32 的临时 IME 路径也需要该组件。此缺口尚不能解释进程 D 状态或测试卡死，根因未取得栈证据。不能改 debug 包或用直接 ADB 输入冒充字段级证明。
- 输入诊断 ELE fencing `4` 已释放；测试 APK 和 harness 保留。该轮结束时 UI 开关关闭，但 secure settings/Binding services 仍有残留，不能写成已干净解绑。后续联网预检才观察到启用列表为空。详细记录见 [华为 API29 输入验证](../../artifacts/input-transport-20260922/device-acceptance/huawei-ele-api29-20260925.md)。
