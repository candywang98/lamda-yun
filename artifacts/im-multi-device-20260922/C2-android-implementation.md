# C2 Android 入站可靠采集：pa-im-m3/20260922.1

日期：2026-09-22（Asia/Shanghai）

最新结论以 `C4-controller-verification.md` 为准。本文件保留 C2 阶段记录；C4 主会话进一步发现并修复解除暂停布尔返回值误用、旧绑定待发串线、task-lease 409被误当IM确认的问题，并恢复接收器重启恢复测试与共享跨端SHA夹具。最新 acceptance 87 项、debug全量1204项、lint/构建通过；旧测试数、旧APK哈希和早期debug入口描述不可作为当前验收依据。未安装APK、未修改生产配置、未发送闲鱼消息；C5仅做只读检查且两台华为超时。

## 设计

canonical 文本在 `ImCanonicalText`。长度按 Unicode 码点。先保留前 4000 个码点，不超过 2000 则原样；超过 2000 则变成 `TRUNCATED ` 加前 2000 个码点。已经是「恰好一个前缀加 2000 个码点」的正文不再加前缀，所以 `canonical(canonical(x)) = canonical(x)`。补充平面字符算 1，截断不会切开代理对。

入队、dedupe、上报 JSON 的 `text` 都用这一份。dedupe 原材料是 `bindingDeviceId|platform|peerKey|occurredAtEpochSecond|canonicalText` 的 SHA-256。`deviceId` 不进 JSON。本轮上报 `platform` 只允许 `xianyu`，客户端在 `CloudTaskClient.sendImMessages` 里拒绝缺省。

持久 outbox 是单独的 SQLite `cloudctl-im-outbox.sqlite3`，不写入任务用的 `event_outbox`，也不提升 `AutomationStore` 的 schema 版本。容量 200。满了拒绝新事件，打 `IM_OUTBOX_OVERFLOW`，不删除最旧行。确认只发生在响应同时带有 `accepted` 与 `duplicates`，且两者之和等于本批条数时。空对象、缺字段、部分计数都整批保持未确认，错误码 `IM_OUTBOX_UNACCOUNTED`，按 `OutboxRetryPolicy` 退避。响应没有逐条 id，所以不能只确认其中一部分。5xx/408/425/429 和 `IOException` 走同一退避。其它 4xx 记 `permanent_failure_at` 与 `HTTP_<status>`，可查询，不再重试。`ACCEPT_AS_DELIVERED` 仍只来自既有策略里「409 且正文含 mobile task lease」这一支，IM 入站响应不会走到它。

内存 `ImMonitor` 只留 LRU 提示。可靠性以 outbox 为准。通知到达时如果读不到 binding，行以空 `device_id` 落盘，不进入待发；发送时用当时 binding 的 `device_id` 重算键（`sealUnbound`）。空 id 不是另一台设备的 id，也不会用 ADB serial。

暂停上送是 outbox meta `upload_hold`，默认 0。置位后真实通知仍入队，`ImOutboxDelivery.deliverOnce` 自己打 `IM_OUTBOX_HOLD`，不调用 sender，也不确认。标志在库里，进程重启后还在。

操作者开关不走 `CompanionSyncService`。隔离 debug 包继续删除生产同步服务和网络权限，不能用于 C6 上传恢复。为避免“两种 APK 各完成一半”，主会话接手后新增独立 `acceptance` build type：它继承 release 的真实绑定、网络和 `CompanionSyncService`，使用独立包名 `com.company.cloudctl.companion.acceptance` 与调试签名，不替换生产包。

受控入口只存在于 acceptance source set：

- 组件：`com.company.cloudctl.companion.im.ImUploadHoldReceiver`。
- 声明：`src/acceptance/AndroidManifest.xml`；`android:exported="true"`，但要求系统签名级 `android.permission.DUMP`，普通应用无权调用，ADB shell 可调用。
- `src/main`、`src/debug` 与 `src/release` 都没有该接收器；正式 release 的 `IM_UPLOAD_HOLD_ALLOWED=false`。
- action `com.company.cloudctl.companion.action.IM_OUTBOX_HOLD`，boolean extra `held`。
- 接收器只更新持久 `upload_hold`，不插入消息、不伪造通知、不打开网络；上传仍由同一 acceptance APK 的 `CompanionSyncService` 执行。

acceptance 安装上的显式命令（本检查点未执行 ADB）：

```
adb shell am broadcast -n com.company.cloudctl.companion.acceptance/com.company.cloudctl.companion.im.ImUploadHoldReceiver -a com.company.cloudctl.companion.action.IM_OUTBOX_HOLD --ez held true
```

解除暂停把 `held` 改成 false。这样同一个 acceptance APK 可执行“真实通知落盘 → 暂停 → 杀进程/重启 → 解除暂停 → 恢复上送”；正式 release 不暴露该入口。

`mode=NOTIFICATION` 时 `ImMonitorConfig.dutyActive` 仍返回 false，本轮没有改 `DutyController` 的启动和点击。

## 实际修改

新增：

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImCanonicalText.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImDedupe.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImInboundEvent.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImNotificationIntake.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImOutboxDelivery.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImUploadHold.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/ImOutboxStore.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/im/ImCanonicalTextTest.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/im/ImOutboxStoreTest.kt`

修改（只限 C2 接线）：

- `im/ImMonitor.kt`：dedupe 改走 canonical；去掉内存 `ArrayDeque` 和满队列 `removeFirst`；`accept` 写入持久 outbox。
- `service/CompanionSyncService.kt`：`onCreate` 安装 `ImOutboxStore`；`onStartCommand` 把上述 Intent 交给 `ImUploadHold`；`deliverImEvents` 改走 `ImOutboxDelivery`。原有 `SyncForeground.start` 未改。
- `automation/CloudCtlAccessibilityService.kt`：通知入站改为 `ImNotificationIntake`，不再 `text.take(4000)`；缺 `when` 记 `OCCURRED_AT_SYNTHESIZED`；缺 binding 仍入队。
- `network/CloudTaskClient.kt`：`sendImMessages` 要求每条有 `platform=xianyu`，并拒绝 JSON 里的 device id。
- `test/.../im/ImMonitorTest.kt`：内存队列断言改成内存提示断言。

未改 `app/build.gradle.kts`。Robolectric 与 `org.json` 已在测试依赖里。

## 保留的 B14 / P13 交叠

动手前 `git status` 已有这些未提交改动，本轮没有 reset、checkout、restore，也没有改它们的输入、IME、发送或诊断靶场：

- `mobile/companion/app/build.gradle.kts` 的 `applicationIdSuffix = ".debug"`。
- `CompanionSyncService.kt` 里原有的 `SyncForeground.start` 替换 `startForeground`。本轮只在该文件追加 IM outbox 安装和 `deliverImEvents`。
- `CloudCtlAccessibilityService.kt` 里原有的编辑器、输入、发送证明改动。本轮只替换 `onAccessibilityEvent` 的通知入站段。
- `CompanionRepository.kt` 的 `BindingWritePolicy.beforeSave()`。
- 未跟踪的 `ime/**`、`automation/DiagnosticInput*`、`src/debug/**`、`src/release/**`、`mobile/input-harness/**`、`artifacts/input-transport-20260922/**`。

`git diff --stat` 里 `CloudCtlAccessibilityService.kt` 的大数字主要来自这些既有改动，不是本轮重写该文件。

## 测试

在 `mobile/companion` 实际执行：

```
./gradlew :app:testDebugUnitTest --tests 'com.company.cloudctl.companion.im.*' --offline
```

最终确定性门全部退出码 0：

```
./gradlew :app:testAcceptanceUnitTest --tests 'com.company.cloudctl.companion.im.*' :app:testDebugUnitTest --tests 'com.company.cloudctl.companion.im.*' :app:assembleAcceptance --offline --rerun-tasks
./gradlew :app:testDebugUnitTest --offline
./gradlew :app:processReleaseMainManifest -x :app:verifyReleaseUpdatePublicKey --offline --rerun-tasks
git diff --check
```

结果：acceptance 单元测试 84 tests / 0 failures；全量 debug JVM 1201 tests / 0 failures；`assembleAcceptance` 成功。APK 为 `app/build/outputs/apk/acceptance/app-acceptance.apk`，大小约 48 MiB，SHA-256 `fafe5527bfd510e389dd737c4ff2b69e18d29d019580c526a90b115109b357bd`。

重新生成的 acceptance merged manifest 同时包含 `android.permission.INTERNET`、未导出的 `CompanionSyncService`、以及 `android.permission.DUMP` 保护的 `ImUploadHoldReceiver`。重新生成 release manifest 时按仓库既有口径只跳过必须提供受控发布公钥的 `verifyReleaseUpdatePublicKey`；release manifest 保留 `CompanionSyncService`，不含 `ImUploadHoldReceiver`。未使用旧缓存冒充结果。

覆盖：平台透传且拒绝非 xianyu、canonical 超长与重投同一键、重复通知、持久入队与成功确认、空对象和部分 `accepted` 不确认、`IOException` 与 408/425/429/503 退避、422 永久保留且第二次不再发送、关闭 store 再打开仍在、容量 200 拒绝新行且日志含 `IM_OUTBOX_OVERFLOW`、`m0` 仍是队首、暂停日志、正式 release 不能开启暂停、acceptance 受控广播只改 flag 且不增加消息行、暂停后重启仍未确认、同一 acceptance 构建保留真实上传循环、未绑定行不发给其它设备、dedupe 使用 binding device id 而不是 serial `b0644fb5`。

## 输入旗标与 C2 增量

`git show HEAD` 计数：`CloudCtlAccessibilityService.kt` 与 `src/main/res/xml/accessibility_service_config.xml` 的 `FLAG_INPUT_METHOD_EDITOR` / `flagInputMethodEditor` 都是 0。

C2 之前的 B14 基线 `artifacts/input-transport-20260922/current-protected-combined.diff` 第 41–68 行已经加入 `inputMethodEditorFlag()`，并在 `onServiceConnected` 里 OR 进 flags。该文件不包含 `accessibility_service_config.xml`。运行时旗标由这段既有代码设置。本轮没有改这个函数，也没有改 `src/debug/res/xml/accessibility_service_config.xml`。

主清单 `src/main/res/xml/accessibility_service_config.xml` 一度被写成带 `flagInputMethodEditor`。该行不在上述基线里，不能算作受保护的 B14 差异。本轮把它改回与 HEAD 相同：`git diff` 对该文件为空。debug 资源清单仍保留基线里的 `flagInputMethodEditor`，本轮未改。

因此 C2 增量不包含无障碍 IME 旗标。工作区相对 HEAD 的 Kotlin diff 仍看得到这段旗标，那是未提交的 B14，不是本轮新增。

## 尚未覆盖

以下检查本检查点没有跑，不能写成通过：

- `./gradlew :app:lintDebug`
- `./gradlew :app:assembleDebug`（已构建专用 `assembleAcceptance`）
- 后端 pytest、ruff、pyright、mypy
- Web vitest、typecheck、build
- 真机安装与实际 ADB 广播

服务端 `_dedupe_key` 仍不含 platform，入站 schema 仍没有 platform 字段。本轮客户端已经带上 `platform`，但当前服务端会 422。那是 C3 的契约差额，本轮按停止条件没有改后端。C4 的跨端 SHA-256 夹具和 C6 真机重投都还没做。
