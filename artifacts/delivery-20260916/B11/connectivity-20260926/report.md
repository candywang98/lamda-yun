# B11 连接状态修复与后台掉线跟进 — 2026-09-26

## 当前结论（11:09 +08:00，取代本报告早前的“未安装”状态）

- **同包同签名的只发心跳诊断版已于 10:47:22 安装到一加；数据与授权状态保留验证通过。持续在线仍不通过，具体根因未确认。**
- 10:47:22–11:09:27 的完整 nginx 当前日志窗口内，Companion 路径只有 3 次 `POST /companion/v2/devices/heartbeat`，均 HTTP 200。没有发现其他 Companion 路径请求；这是所有 Companion 客户端的路径汇总，不能仅凭 nginx 日志独立归属设备。
- 本地同一 PID 661 的诊断日志显示：20 秒等待在 10:47:46.287–11:00:43.978 之间实际跨越 **777,691 ms**；`elapsedRealtime` 和 `uptimeMillis` 的增量均为 777,691 ms，估算深度休眠差值为 0。随后健康采集及网络请求在约 0.5 秒内完成，HTTP 200。
- 因而本次长空窗发生在心跳成功后的等待／恢复调度边界，而非一个持续阻塞的网络请求或健康采集。此证据不支持用 CPU 深度休眠解释这段空窗，但尚不能区分协程定时器／调度停滞、进程受调度限制或厂商后台机制。不能直接定性为“Android Doze”或“Oplus 冻结”，也不能推断华为是相同原因。
- **11:08:32 已恢复一加原有维护状态 false（version 3 → 4），释放 fencing 6 的本地设备锁；11:09:26 回读确认。** 诊断 APK 保留，业务执行禁用，不自动恢复旧业务 APK。
- 工作分支 `integration/goal-20260924-no-send`，基线 HEAD `092c6983e2ef85cb6f7d443b5f34a73353974d17`。未提交、未部署服务器、未重启服务器、未迁移服务端数据库。

## 授权与操作边界

用户在明确“只更新闲置一加、同签名保留数据、权限不变、不碰两台华为、不执行业务任务”的安装询问后回复“确认，继续”，并再次确认继续诊断。此次授权没有扩展为卸载、清理数据、重新绑定、重启、修改系统省电设置、拔线或真实业务操作。

实际执行：

- `adb -s b0644fb5 install -r` 安装一次诊断包；没有卸载或签名绕过。
- 安装后的本轮取证仅执行只读 ADB、只读云端查询及本地构建／测试；未再安装、未打开应用、未模拟按键、未修改权限或系统电源设置。
- 临时维护仅针对一加；锁 holder `pi-connectivity-20260926`，task B11，fencing 6，10:46:41 获得、11:08:32 释放，未过期抢占。
- 未操作两台华为，未发送、发布、删除、改价、评价、付款或上传业务内容；健康心跳是唯一获允许的诊断请求。
- 无有效云端租约、未完成任务或启用的计划任务（收尾前后均再次核验）。

## 安装与数据保留证据

| 项目 | 结果 |
|---|---|
| 手机 | OnePlus 9R / LE2100 / API 34 / `b0644fb5` |
| 包名 | `com.company.cloudctl.companion`，与原应用一致 |
| 当前安装版本 | `0.1.0-connectivity-20260926`，versionCode 1 |
| 安装时间 | 2026-09-26 10:47:22 +08:00 |
| APK | `mobile/companion/app/build/outputs/apk/heartbeatDiagnostic/app-heartbeatDiagnostic.apk` |
| APK SHA-256 | `620faa94512d80343114d0d5febc0d30a594072de7fe9e1aed0c13eb7dd011aa` |
| 同签名证书 SHA-256 | `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796` |
| 原 APK 备份 SHA-256 | `ab17a92a79ed862b31d3ca58a213abe9bcc14949e2adef2665627e08af024461` |
| 原首次安装时间 | 2026-09-20 15:47:27，安装后不变 |
| 绑定保留 | `cloudctl_binding` preferences SHA-256 与安装前一致；未重新绑定 |
| 数据库完整性 | 安装前后副本 `PRAGMA quick_check` 均 `ok` |
| 数据库内容 | 11 张表的 schema、行数、逐行规范化散列汇总均相同 |
| 本地队列 | 31 条 `task_inbox` 不变；原有 30 TERMINAL_CONFIRMED、1 TERMINAL_REJECTED |
| 其他持久化内容 | 247 条 event_outbox、277 条 run_journal 及其他表内容摘要均不变 |
| 授权状态 | 12 条可解析的 granted 状态与原包一致；请求权限列表此前已核对一致 |
| 系统设置 | enabled_accessibility_services、enabled_input_methods、default_input_method、enabled_notification_listeners 与安装前一致 |

数据库使用含 WAL 的完整副本做离线比对；原始内容不进入仓库。内容摘要相同不是对每个业务语义的额外验收，但足以证明所比较的持久化表未被此轮诊断改写。

先前构建的 acceptance APK 包名带 `.acceptance`，签名不同，**没有安装**，没有用卸载来克服冲突。当前诊断包通过 `build-external.sh` 使用原外部 Android 用户目录的匹配 debug 签名。诊断包不是正式生产发布包，不代表业务验收。

## 心跳观察时间线

所有时间为 2026-09-26 +08:00。

| 时间／窗口 | 观察事实 |
|---|---|
| 10:47:25 | 安装后服务自动启动，PID 661；第一次心跳 HTTP 200 |
| 10:47:45–46 | 第二次心跳 HTTP 200；进入 `heartbeat_delay` |
| 10:51:33–10:59:18 | 本轮先只查云端，没有 ADB；最后认证请求一直停在 10:47:45.807237 |
| 10:59:18 | 云端请求年龄约 693 秒；有效租约与未完成任务仍为 0 |
| 10:59:36.656–10:59:45.880 | 第一轮集中只读取证；日志仍结束于 10:47:46.287；屏幕 Asleep、充电、deviceIdle=false、无 suspend blocker |
| 11:00:43.978 | 同一 PID 恢复到 `network_check`；距上次 delay 777,691 ms；估算深度休眠 0 ms |
| 11:00:44.471 | 第三次心跳成功；没有服务重建、`presence_exit`、网络错误或健康采集长耗时日志 |
| 11:01:34 | 第二轮只读采集取得恢复记录；绑定摘要仍不变 |
| 11:03:54 | 云端请求又已过期约 191 秒 |
| 11:08:32 | 用 expectedVersion=3 恢复一加维护 false/version 4，回读后释放本地锁 |
| 11:09:26–27 | 最后请求仍为 11:00:43.917156，约 523 秒前；API、nginx active；窗口内只有 3 次成功心跳 |

第一轮只读取证可能影响系统调度；恢复发生在取证之后约一分钟，**无法由先后顺序证明 ADB 导致恢复**。没有通过反复打开应用人为维持“在线”。

`dumpsys activity processes` 的事后快照显示前台服务仍在、`isFrozen=false`、`isPendingFreeze=false`、`virtualFreeze=false`。这些是快照，不是整个空窗的冻结历史。定向厂商日志没有返回记录；只读 `dumpsys oplus_freeze` 与 `oplus.hans.IHansComunication` 无输出，未改变设置，也未绕过权限取得 cgroup 信息。

### 时钟解释的官方依据

- Android Developers，`android.os.SystemClock`：`elapsedRealtime()` 包括深度休眠，`uptimeMillis()` 不包括深度休眠。官方地址：`https://developer.android.com/reference/android/os/SystemClock`，2026-09-26 核对。
- Kotlin 官方 `kotlinx.coroutines.delay`：给出至少指定时长的挂起，并非严格的恢复截止保证。官方地址：`https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/delay.html`，2026-09-26 核对。
- 本次两个增量相等，支持“这段空窗不能用深度休眠解释”；**不是**证明应用线程始终获得 CPU，更不是已经定位到具体库或 OEM 缺陷。

## 最新云端状态

以下 `device.last_seen_at` 是最近认证请求，不是专用成功心跳指标。`MobileService.authenticate()` 也会为普通认证请求刷新设备和绑定时间；本次须结合只允许心跳的安装包与服务端路径日志解释。

| 手机 | 云端设备 ID | 最近认证请求（+08:00） | 11:09:26 时年龄 | 维护 |
|---|---|---|---:|---|
| 一加 9R | 4aabc387-6e4b-4b59-a525-b1c119ec7f5b | 2026-09-26 11:00:43.917156 | 523 秒 | false/version 4，本轮已恢复 |
| 华为 P30 Pro | 050cdb78-c815-4989-8744-2a519d33079a | 2026-09-26 03:15:24.935918 | 28,442 秒 | false/version 0，未操作 |
| 华为 P30 | d2f2672f-ef26-4d7d-a6c2-88452c0eb2bf | 2026-09-26 03:15:37.126415 | 28,429 秒 | true/version 1，原有状态未操作 |

三台绑定均未撤销。成功短连、绑定有效、显示状态正确、执行就绪是不同事实。诊断心跳上报 `runnerState=IDLE`、`accessibilityEnabled=false`，不代表实际撤销无障碍权限。

云端共 8 条设备记录；两条 `last_seen_at` 为空的旧一加记录不代表这台真实手机，本轮未删除、合并或解绑它们。

## 代码与测试

### 已有显示修复

1. 成功心跳时间与 90 秒有效期；兼容缺失／损坏时间，不再永久沿用持久化 online=true。
2. 绑定与连接分别显示，展示最近成功心跳和分类失败原因。
3. 每 5 秒独立刷新本地状态，不被账号网络请求阻塞。
4. 账号加载传播 `CancellationException`；延迟失败不覆盖新账号状态或恢复旧绑定。
5. 未绑定时不显示旧心跳；生命周期、缺绑定、网络、认证、HTTP、未知同步失败明确落状态。

TTL 仍使用 `Instant` 墙钟，不是单调时钟。显示修复不等于后台保活修复，也未完成此显示的新真机交互验收。

### 当前诊断包安全限制

- `HEARTBEAT_DIAGNOSTIC` 仅诊断变体为 true，正常构建默认 false。
- 服务只启动 presenceLoop，不启动 claim/sync/outbox；跳过中断任务恢复、能力探测、Recipe 恢复、控制事件、预览、resume、更新回执和自动升级。
- UI 隐藏业务入口，不请求通知权限；跳过账号轮询、IM 采集和入队。
- `PinnedHttpsTransport` 只允许精确的 `POST /companion/v2/devices/heartbeat`，其他方法、路径及文件传输被拒绝。
- 诊断 trace 仅记录阶段、时钟、电源和 keyguard 元数据；不记录令牌、消息内容、请求正文或屏幕内容。既有心跳业务日志不作为可公开原始证据。
- 未加入永久唤醒锁、未修改电源设置或运行时权限。

### 本轮新增测试及结果

执行：

```bash
cd mobile/companion
./build-external.sh --offline :app:testDebugUnitTest \
  :app:testHeartbeatDiagnosticUnitTest --console=plain
```

| 验证范围 | 结果 |
|---|---|
| debug 单测 | 169 suites / 1,237 tests / 0 failures / 0 errors / 0 skipped |
| heartbeatDiagnostic 单测 | 169 suites / 1,226 tests / 0 failures / 0 errors / 0 skipped |
| 本轮命令 | exit 0 |
| 任务与差异检查 | `python3 scripts/plan_guard.py docs/current/tasks.json` 与 `git diff --check` 均 exit 0；development DAG 54 节点／68 边；证据摘要与任务状态一致 |
| 安装前诊断 lint／assemble | lint 19 Warning、0 Error/Fatal；assemble exit 0 |
| 当前 APK 哈希 | 与安装时相同；本轮只改测试与记录，没有再次打包安装 |

第一次运行诊断变体有 2 个失败，均为共享测试写死普通 debug 模式预期：BindingWritePolicy 的 debug-only 拒绝策略，以及 IM 平台开启预期。本轮修正变体预期，没有通过跳过测试或放开运行时安全门消除失败。

新增 `src/testHeartbeatDiagnostic/.../network/HeartbeatDiagnosticTransportTest.kt` 6 项：真实变体包名和 flag、业务路由拦截、错误方法／路径拦截、精确心跳通过策略但仍需 HTTPS、文件传输在创建文件前拒绝、所有 IM 平台保持关闭。测试使用无效端点在创建 socket 前停止，不发送请求。结果 XML 核对：debug 独有 `DiagnosticInputHarnessTest` 17 项，diagnostic 独有新增传输入口测试 6 项，所有共享 suite 的测试数相同；因此两者总数相差 11 项，不能相加为独立需求数量。

**仍未覆盖：** 完整 `CompanionSyncService` 生命周期／任务恢复的诊断变体端到端测试、长期真实屏幕锁定场景、脱离电脑运行、所有业务执行入口的动态攻击式验证。主会话静态检查与传输入口测试不等于独立安全审查。

独立审查此前两次派发均返回 403，没有审查结果；本轮不将其标为通过。保留此审查缺口，不自动提交或恢复业务版。

### 涉及文件

原显示修复：`CompanionViewModel.kt`、`MainActivity.kt`、`data/CompanionRepository.kt`、`data/RuntimeStatusStore.kt`、`data/AccountStatusRefresh.kt`、`model/Models.kt`、`model/PresenceIssue.kt`、`service/CompanionSyncService.kt` 及 presence/account-refresh 测试。

诊断新增／调整：`app/build.gradle.kts`、`im/ImMonitor.kt`、`network/PinnedHttpsTransport.kt`、`network/HeartbeatDiagnosticPolicy.kt`、`service/ConnectivityDiagnosticTrace.kt`、上述 MainActivity/Repository/Service，以及 policy/clock 测试。

本轮只修改 `data/BindingWritePolicyTest.kt`、`im/ImMonitorTest.kt`，新增诊断变体传输入口测试，并更新本报告、脱敏证据摘要和 B11 的当前元数据。其他未提交工作保持不动。

## 后续最小诊断与验收

1. **分离调度原因，而非先加保活机制：** 下一轮增加独立定时源与实际恢复时刻对照，或在明确授权的只读诊断范围获取应用线程栈／厂商冻结历史，区分定时器、dispatcher、全进程调度暂停。不能从单一 `delay` 空窗决定换库或加永久唤醒锁。
2. 若需要另一个安装包，继续保持同包同签名、保留数据、只发心跳和 no-send 边界，先确认授权范围并重新检查设备锁、任务、租约；当前锁已经结束，不能沿用旧 ownership。
3. 验证有界修复后再做前台 ≥5 分钟、后台 ≥15 分钟、实际 keyguard 锁定且脱离电脑 ≥30 分钟的稳定性窗口。当前日志 `interactive=false`、`locked=false` 且 USB/充电，不得称为锁屏或电脑独立验收。
4. 恢复正常业务 APK、拔线／网络切换／系统配置修改及只读云端任务闭环，须有对应授权；不自动执行。
5. 最后再验证固定 APK 的 Recipe V1 → V2 → V1 回滚。云端可热更新的范围取决于已支持的动作及定位器配置，硬编码能力仍需 APK 升级。

B11 继续为 `IN_PROGRESS` / `DEVICE_WAIT`；历史 activation 记录保留，不覆盖当前连接回归。

## 历史记录与证据位置

- 03:39:21 的旧只读调查：三台认证请求都已过期；此前一加重开仅短暂恢复。03:16:14 的维护恢复和 fencing 5 释放仅属于更早实验，不能替代本轮 11:08:32 的收尾证据。
- 旧 acceptance 构建：167 suites / 1,232 tests，APK SHA-256 `26ec13f1e5446e971067c4ba2c5836e7c154d632c5b6a4938f5e94038306bc26`；该包始终未安装。它不是当前诊断包。
- 脱敏机器摘要：同目录 `diagnostic-evidence.json`。
- 本会话 protected scratch 的 `connectivity-20260926-install/` 保存安装前后包与数据库、settings、binding hash、阶段日志、passive-cloud.jsonl、preservation-summary.json、software-final-summary.json、nginx-paths-final.json、maintenance-cleanup.jsonl、device-lock-released-current.json。
- 早前证据仍保留于 `connectivity-20260926/`、`connectivity-20260926-followup/`。

不将原始数据库、消息内容、认证凭据、锁所有权令牌或带敏感信息的系统日志写入仓库。唯一机器任务 authority 仍是 `docs/current/tasks.json`。
