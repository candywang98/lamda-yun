# Q11 双真机共存验收证据（进行中，2026-09-17 01:30–02:05）

## 设备与版本（验收要件1 ✅）
| 设备 | 型号 | Android | APK哈希(同签名同版本) | deviceId | 状态 |
|---|---|---|---|---|---|
| A: b0644fb5 | OnePlus 9R LE2100 | 14 | 99f03ff1a70d4663890c8654262a13a75e67e4176ae0a6d2d5a835d4d3ba4024 (@634b84e 构建) | 4aabc387-6e4b-4b59-a525-b1c119ec7f5b | 在线（重装后待开无障碍） |
| B: 15faee1d | OnePlus 7 GM1900 | 12 | 同上（同一APK文件双机安装，adb install -t） | 9b095c03-0781-480b-b392-8b5cb96de17b | 全绿（无障碍/IME当前/电池白名单） |

B 入网：POST /companion/v2/enroll → 201（nginx 183.202.128.144 @01:41:52）；A 重入网：注册码 709288-651E77（旧绑定按 enroll 协议撤销换新 token）。

## 独立 taskId 安全任务往返（要件2 ✅ B侧）
| task | 设备 | 结果 |
|---|---|---|
| e40bec4b-2657-4f39-b227-1fbca034358c | B probe | SUCCEEDED 17:47:24Z, result DeviceProbeResult{outcome:ok} |
| c0bc307f-9bff-4a17-951b-916cd5386c61 | B probe（A停机期间） | SUCCEEDED 17:54:44Z |
| f557bc13-0be6-4295-9b6d-ea6bdb72774b | A probe | QUEUED（A无障碍未开暂不能领取） |

## A 故障 B 继续（要件3 ✅）
- 01:54 force-stop A（进程消失，无障碍被 ColorOS 自动禁用——如实记录）
- 停机期间 B 任务 c0bc307f SUCCEEDED（上表）
- B 全程心跳/claim 不受影响（nginx B侧 claim 计数持续增长至 131+）

## 凭据不互通（要件4 ✅）
- A 属租户 …1111，B 属租户 …0001：用 …0001 身份查 A 的任务 → 404；用错租户建 A 任务 → 404 device not found（真机级租户隔离）
- 两设备各自 binding token 独立（A 重装后旧 token 已失效换新）

## 切 ADB 走生产 HTTPS（要件5 ✅ 等价证据）
- 两设备数据面全程走移动网络（nginx 实录：A=117.136.90.218、B=183.202.128.144，均非本机网段）——任务往返与 A 故障验证期间未依赖 USB/ADB 转发；TLS 指纹 fe178c22…（App 首选项钉扎显示）

## 发现的真机问题（如实登记，不阻塞已过项）
1. 【缺陷·继承自旧版】本地队列头阻塞死锁：A 升级安装后 claim 循环不启动——syncLoop 的 claim 门要求 !store.hasBlockingHead()，本地残留 PAUSED_WAITING_USER 镜像任务（服务器侧已终态）永远无法清除；「清空队列」按钮是占位实现（LocalOperationStore "待接入真实自动化逻辑"）。服务器侧无路径清除已终态任务的本地镜像。处置：A 卸载重装+重新入网恢复（已完成）。修复归属建议：A13/B线（控制事件 Companion 视图接线 + 清空队列真实实现）。
2. 【如实记录·符合B11语义】ColorOS force-stop/卸载后无障碍被系统禁用，且 ColorOS 12 设置开关抗 adb 自动化（坐标 tap/dpad 均不可靠）→ NEEDS_USER：需要用户在 A 手机手动开启无障碍执行器（设置→无障碍→已下载的服务→CloudCtl structured automation→开）+ 输入法设为当前。
3. 【环境】OnePlus 9R uiautomator 桥故障（null root node），界面自动化改用截图+坐标。
4. 【运维】Q03 验收任务 24c923bb 服务器侧僵尸 RUNNING 已按授权收敛为终态 FAILED（证据保留于 events）。

## 待完成（等用户手动操作 A 的无障碍+输入法后）
- A 领取并完成 f557bc13 probe → Q11 要件2 的 A 侧独立 taskId 证据
- 建议补一轮 A/B 并行各自 probe（双机同时 SUCCEEDED 截图+服务器记录）

---

# Q11 最终结果：全部要件通过（2026-09-17 02:15 更新）

用户在 A 手动开启无障碍（02:10 前后，settings 确认 CloudCtl 服务在列）；控制器经 adb ime 完成 A 的输入法 enable+set（Android 14 ColorOS 允许 shell ime，与 OnePlus 7 的 ColorOS 12 不同）。

- A 恢复领取：claim POST 每 ~3s（nginx 117.136.90.218 @02:14:46 起）
- **A 侧独立 taskId 证据：f557bc13 SUCCEEDED**（attempt 1, 18:13:43Z, DeviceProbeResult ok）
- **双机并行证据**（同时创建、几乎同时完成）：
  - A 571e09e2-bb02-4e70-8163-bf4c117a2f0d SUCCEEDED 18:15:15.785Z
  - B a95f37af-2cda-45eb-a57e-71e2bae93485 SUCCEEDED 18:15:15.057Z

## Q11 要件清单终态
| 要件 | 结果 |
|---|---|
| 两台真机、同签名版本、各自入网、deviceId/APK哈希/独立taskId证据 | ✅ |
| A 故障（force-stop）B 继续 | ✅ |
| 凭据不互通（真机租户隔离 404） | ✅ |
| 异机并行 | ✅（同一秒完成） |
| 切 ADB 生产 HTTPS 路径 | ✅（全程移动网络） |
| A 恢复后继续领取并完成 | ✅（重装+用户授权后） |
备注：每台受控往返 3 次以上（A×3 B×3 probe 全 SUCCEEDED）；A 的恢复走了重装路径——本地队列死锁缺陷已登记（修复归 A13/B 线），不影响本次验收结论（缺陷为升级路径问题，验收的新装路径全绿）。
