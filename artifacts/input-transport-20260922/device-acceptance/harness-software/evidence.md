# C7 隔离输入靶场软件门禁

- 时间：2026-09-22（Asia/Shanghai）
- 结论：通过软件门禁，可进入下一步生产空闲重检与设备锁准入。
- 边界：本检查点仅证明 debug-only 隔离靶场及固定单步入口的软件实现、构建隔离和 APK 权限边界；不是 API 34 真机输入结果，不是闲鱼 Flutter/ColorOS 聊天或描述字段验收，也不外推 API 29–32。
- 执行分工：Grok 4.7 在 scratch 中实现；主会话独立复核、修复编译与最小权限问题，并在权威仓库重跑门禁。

## 权威仓库门禁

- Companion clean `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest`：通过。
- Companion JVM：1178 tests，0 failures，0 errors，0 skipped。
- `:app:compileReleaseKotlin -x :app:verifyReleaseUpdatePublicKey`：通过；只跳过需要受控发布公钥的打包门禁，没有伪造发布密钥。
- 独立 input-harness clean `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug`：通过。
- input-harness JVM：4 tests，0 failures，0 errors，0 skipped。
- `python3 scripts/plan_guard.py docs/current/tasks.json`：valid；development 54 nodes / 68 edges；acceptance union 54 nodes / 139 edges；无 running conflict。
- `git diff --check`：通过。

## 编译期与入口边界

- debug Companion 包名：`com.company.cloudctl.companion.debug`，与生产包并存，不覆盖已绑定生产安装。
- debug 仅编译固定 package、固定 locator、固定 fixture 的 `DiagnosticInputStepRunner`；设备入口不读取 instrumentation 参数。
- 固定任务仅含一个 `AutomationStep.Input`，直接复用 `LocalAutomationExecutor` 和已连接的 `CloudCtlAccessibilityService`，共享 `DeviceArbiterHolder`。
- 不调用 `CloudCtlAccessibilityService.execute`、`rawReplaceText` 或 `UiExecutionPort`；不构造 tap/send/publish/review/delete/price/restart/back 步骤。
- cloud task parser 与 `TargetLocatorRegistry` 未加入 harness package/locator；release 使用无 setter 的 Closed policy。
- debug binding 持久化会抛出 `DEBUG_BINDING_FORBIDDEN`；debug Manifest 不声明 `CompanionSyncService`、`BootReceiver`、`MediaProjectionService`、`MainActivity` 或 `CloudCtlInputMethod`。

## APK 产物检查

- Companion debug APK SHA-256：`80a0b50c4f6eea032a341804cd5d176ffca606eb17c40b11fc12a6f01c6a762a`
- Companion androidTest APK SHA-256：`bce683169dcadb6bf0ca1b84e7b51409ead0e5ebe20691fd62104913e2036185`
- input-harness debug APK SHA-256：`5b5fc9daf51c94df9f407c76a657312867f7fd14d882578dcada63d59f377073`
- Companion debug APK 请求权限仅为 AndroidX 自动生成的本包 signature 权限；无 INTERNET、网络状态、启动、前台服务、唤醒锁或安装包权限。
- debug 无障碍配置仅接收 `com.company.cloudctl.inputharness` 事件；`canPerformGestures=false`，`canTakeScreenshot=false`，保留 `flagInputMethodEditor` 和窗口内容读取以完成 API 34 编辑器输入与字段级证明。
- input-harness APK 包名：`com.company.cloudctl.inputharness`；无请求权限；仅有一个空的多行 `EditText` Activity，无发送、发布、评价、确认或剪贴板控件；构建脚本断言无 release 产物。

## 输入证明回归

- 空字段最多一次 commit；全文已相等时 0 commit；commit 计数异常失败关闭。
- 非空且不同的用户草稿返回 `FIELD_DIRTY_BY_USER`，不覆盖。
- proof 与 live node 必须绑定同一稳定 node key；页面其他文本不能授权。
- proof slot 在新写入前清空，写入抛错或返回 null 后不会恢复旧 proof。
- 设备测试只接受 `INPUT_VERIFIED`、ACCESSIBILITY、恰好 1 commit、完整 SHA-256 proof 字段，并校验默认输入法前后不变；失败结果不能假绿。

## 未执行

本检查点没有查询新的生产占用、没有取得设备锁、没有安装 APK、没有启用无障碍服务、没有启动靶场、没有写入手机字段，也没有执行任何闲鱼发送、发布、评价、删除、收费或推广动作。
