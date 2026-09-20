# Q14 真机投屏与自动化交还——会话执行清单（2026-09-20 备妥）

## 就绪状态（本轮实测）

- 首尔后端：`cloudctl-mobile-api.service` + `cloudctl-edge-hub.service` active（3 天），postgres `cloudctl` 库正常。
- 设备心跳（首尔库 `device.last_seen_at`，06:52:48Z 实测）：A机/华为C机/vivo D机/B机 **四台全部秒级在线**；小米 E 机 09-17 后无心跳（严禁业务机，不纳入）。
- A机 b0644fb5（Q14 主机）：companion pid 6027（SyncService+IME 运行中）、无障碍 on、闲鱼 7.27.90、投屏走已选最小传输档（JPEG 帧流，L10/L11/L12 线已合入）。
- 绑定：五机 account_device_binding 全部 BOUND（Q13 遗留，binding_version=1）。

## 会话步骤（每步先说再做；新投屏会话需用户授权）

1. **用户授权点 ①**：手机上将弹出 MediaProjection 系统同意框——需要用户在 A 机上手动点「立即开始」。
2. Web 工作台打开 A 机详情 → 发起 live 会话（记录 sessionId）。
3. **S1 最小传输档验收**：JPEG 帧流可达、帧序单调、延迟可解释；WebRTC 直连失败/TURN 转发为附加项（不属最小档）。
4. **S2 auto→remote→交还**（自有测试 App 或伴生安全场景）：auto 态暂停 → 请求 remote → 交还 → **人工确认恢复**（用户在手机上确认画面恢复受控）。
5. **S3 注入矩阵**（逐项、单变量）：掉帧、旋转、断线重连、锁屏、另一操作者抢占——每项记录可解释行为；**禁止在 UNKNOWN 破坏性确认窗口做自由远控试验**。
6. 证据：每步截图（手机端 `A_q14_*.png`）+ Web 端截图 + journal 时间戳对齐。

## 边界

- 不 force-stop companion；发布/删除类副作用一概不做（本验收纯投屏/交还）。
- 任一步失败：登记 BLK → 跳过该子项 → 继续其余子项。

## 触发方式

说「开始 Q14」即从步骤 1 起执行；步骤 1/2/4 需要你在手机/网页边配合。
