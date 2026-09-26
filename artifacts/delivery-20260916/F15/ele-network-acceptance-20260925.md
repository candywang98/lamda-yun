# ELE联网验收结果（2026-09-25）

- 设备：华为 ELE-AL00，ADB serial `GBGDU19830002425`，Android 10 / API 29。
- 云端设备记录：`Q14-Bisect-HuaweiP30-GBGDU19830002425`，device ID `d2f2672f-ef26-4d7d-a6c2-88452c0eb2bf`。
- 范围：联网 Companion 安装、专属入网、移动网络 HTTPS heartbeat、断开 ADB 后独立在线观察；不执行平台任务，不发送、不发布、不上传业务素材。

## 安装与绑定

- 构建任务：`:app:assembleAcceptance`，构建成功。
- APK：`com.company.cloudctl.companion.acceptance`，version `0.1.0` / code `1`，minSdk `29`，targetSdk `35`。
- APK SHA-256：`70d345a7a5b5a7c130b5b996618d1af9326d90d85d0d332ca98bf507755b54bb`。
- 签名为当前 acceptance 构建使用的 Android Debug 证书；证书 SHA-256 为 `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`。
- 华为安装器的两层风险确认和帐号密码确认均通过手机系统界面完成；没有关闭系统验证，也没有清除数据或覆盖未知签名包。
- 应用内置 Base URL 为 HTTPS `43.133.243.154.sslip.io`；运行时证书 SHA-256 与 APK 内置 pin 一致：`fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1`。
- ELE 专属一次性入网码通过正常 enrollment API 创建并在英文输入模式下提交，绑定成功。云端 binding ID 为 `b5623adb-2c17-47c5-8a7a-19c4a446d13a`。入网码和 bearer token 未写入本文件。

## 绑定后的心跳

- 云端在 `2026-09-24 18:15:32Z` 收到首个有效心跳，设备状态为 `CELLULAR`、`runnerState=IDLE`、`accessibilityEnabled=false`、`safetyBarrier=NONE`。
- 后台省电白名单通过系统设置确认，CompanionSyncService 为前台服务。
- 为防止任何历史或未来任务领取，云端设备维护模式保持为 `true`；断开前设备 task count 为 `0`、有效生产 lease 为 `0`。

## ADB断开观察

- 关闭 USB 调试通过华为系统“开发人员选项”界面完成。系统开关读取从 `1` 变为空，随后 `adb devices -l` 不再列出 `GBGDU19830002425`。
- 关闭操作记录时间：`2026-09-24 18:20:00Z`。
- 断开前最后一次 binding、device 和 fleet session 时间均为 `2026-09-24 18:16:48Z`（fleet session `last_seen_at` 为 `18:16:45Z`）。
- 断开后云端观察至 `18:28:18Z`，binding、device 和 fleet session 的时间戳都没有继续前进；没有新的移动网络 HTTPS heartbeat。

## 结论

- `INSTALL`: PASS。
- `ENROLLMENT`: PASS，绑定到 ELE 自己的设备记录，未复用其他手机身份。
- `PRE_DISCONNECT_CELLULAR_HEARTBEAT`: PASS，收到移动网络 heartbeat，设备空闲且维护模式有效。
- `ADB_DISCONNECT`: PASS，USB 调试关闭，ELE 从 ADB 列表消失。
- `POST_DISCONNECT_INDEPENDENT_ONLINE`: **FAIL / NOT_ACCEPTED**。断开后没有新的云端 heartbeat，不能把安装、绑定或断开 ADB 本身当作独立在线证明。

本轮未领取任务、未打开平台应用、未发送、未发布、未上传业务素材、未改价、未删除、未评价、未支付，也未进行真实账号业务操作。云端维护模式应在后续恢复心跳前继续保持；本地设备锁 fencing `5` 已释放，最终状态为 `FREE`。
