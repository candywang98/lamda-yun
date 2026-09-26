# C6 API34 真机输入验收：安全入口缺失，未执行字段写入

日期：2026-09-22（Asia/Shanghai）
目标：OnePlus 9R `b0644fb5`，Android 14 / API34 / ColorOS。C5 权威生产占用和本地锁已通过；本检查点不等于真机输入验收。

## 安装前验证

- 当前手机安装的 `com.company.cloudctl.companion` 包签名 SHA-256 为 `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`。
- 原先软件验收 APK SHA-256 `c5c2331d573c973163805a2caaf94b17bf4a34ad6e3388727bb15c9eae9d12f7` 的证书为 `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`，不能直接无损更新，未尝试卸载。
- 项目既有外置构建环境的 debug keystore 证书与当前手机一致。使用 `mobile/companion/build-external.sh :app:assembleDebug :app:assembleDebugAndroidTest --offline` 重建成功；新 APK SHA-256 `0a5e2f13f98e0ee798ca8c119fd054e41ef24dc5b06d48d3678388672f677944`，证书与手机一致。重建仅在本机，**没有安装到设备**。

## 安全入口阻断

代码只从 `CompanionSyncService` 的生产 `CloudTaskClient.claim()` 将任务加入本地队列；没有本地 debug 输入任务注入器，现有 androidTest 不调用正在运行的 `CloudCtlAccessibilityService` 输入路径。API34 的真实聊天/描述定位器在闲鱼字段内，完整任务下一步可能触发发送或发布。不能用只看 UI 目标文字、直接 `adb input text` 或单次连接读出来代替 Companion 的字段级 proof。现有 acceptance-target app 不是 allowlist 中的生产输入 locator，也不是安全的多行空字段靶场。

因此本轮不安装 APK、不创建生产任务、不打开闲鱼聊天、不输入字段、不发送/发布/评价。API34 真机输入与闲鱼 Flutter/ColorOS 兼容仍未验收，API29–32 也未验。可执行的下一检查点是构建严格 debug-only、无网络/发送/发布控件的隔离输入靶场及本地单步入口，独立软件复核安全边界后重新核验外部空闲并持锁，由 Grok 4.7 在主会话监督下验证；靶场通过也不能冒充闲鱼真实场景通过。

## 收尾

控制者于 2026-09-22 20:35:29 Asia/Shanghai 释放 `DEVICE:b0644fb5` fencing=1；随后 `status` 为 `FREE`，owner token 临时文件已删除。设备当前输入法仍为 `com.sohu.inputmethod.sogouoem/.SogouIME`；现有 Companion 的 `lastUpdateTime` 仍为 2026-09-21 02:16:12；前台仍为 ColorOS Launcher。没有改动生产 lease 或服务。
