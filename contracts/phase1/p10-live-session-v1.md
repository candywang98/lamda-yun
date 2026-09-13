# Remote session slice 1: p10-live/20260913.1

P10/P11 第一片：授权观看 + 远控 + 交还，**传输先走受控 JPEG 帧流**（复用既有
pinned HTTPS/WS 通道），WebRTC+TURN（D03）为后续升级，会话语义与传输无关。
Edge/LAMDA 不参与生产链路。

## 会话状态机（服务端为唯一裁决者）

```
CLOSED → VIEWING（操作员发起，Companion 确认采集授权后建立）
VIEWING → REMOTE（操作员接管；设备当前 AUTO 任务必须先暂停确认）
REMOTE → VIEWING（交还） / 任一态 → CLOSED（超时/主动停止/掉线宽限到期）
```

- 会话 = 一行 `device_lease` 扩展用途 `LIVE`（复用现有租约/epoch；**不加新表**，
  不持 DB_MIGRATION 锁；会话内状态存内存 + 审计事件 `live.session.*`）。
- 单 writer：REMOTE 期间禁止 claim 新任务、在跑任务强制进入 PAUSED_WAITING_USER
  （复用现有暂停 API 语义）；交还后恢复排队。VIEWING 不影响任务。
- 硬上限：会话总时长 30 分钟（服务端强制 CLOSED）；无帧/无心跳 30 秒 → VIEWING 掉线
  宽限 10 秒后 CLOSED。

## API

- 操作员：`POST /api/v1/devices/{id}/live`（开看）、`POST .../live/{sid}:take-control`、
  `POST .../live/{sid}:release`、`POST .../live/{sid}:stop`、`GET .../live/{sid}`（状态）。
  鉴权沿用 operator 身份；每次状态迁移写 audit_event。
- 帧/输入通道：`GET /api/v1/devices/{id}/live/{sid}/stream`（WS，服务端转发 JPEG 帧，
  JSON 信令帧 `{t:"frame"|"state"|"hello"}`）；操作员输入 `WS send {t:"input", kind:"tap"|
  "swipe"|"text", x,y,x2,y2,text, seq}` → 服务端校验 REMOTE 态 + seq 单调 + 会话归属后
  转发 Companion；seq 重复/回退丢弃并计数告警。
- Companion：`GET /companion/v2/live/{sid}`（WS 上行帧、下行 input）；`POST /companion/v2/
  live/{sid}/ack`（确认投影授权结果）。

## Android（Companion）

- `live/` 新包：LiveSessionController + MediaProjection 采集前台服务
  （`FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION`，Manifest 声明）。
- 投影授权：收到会话请求 → 本地通知引导用户点系统授权（一次会话一次授权，
  拒绝则 ack denied → 服务端 CLOSED）。不得静默获取、不得 ADB 预授。
- 采集：≤5fps、长边 ≤720、JPEG 质量 ≤60 自适应；无 REMOTE 时可降到 ≤1fps（省流）。
- 远控输入：仅 REMOTE 态执行；tap/swipe 用 dispatchGesture（无障碍手势通道，
  禁 shell input）；text 走现有 replaceText 管线（不自动提交发布类按钮）。
  每条输入带 seq，本地同样校验单调。
- 停止回调：服务端 CLOSED/超时/掉线 → 停投影、释放资源、通知 UI。

## Web（slice 1 最小）

- DeviceDetailView 增加「实时观看」区块（新组件 DeviceLivePanel）：开看/接管/交还/停止
  按钮 + 状态徽标 + 帧画布（img 重绘）+ REMOTE 时画布上转义 tap/swipe（长按拖动）。
- 不做：多设备同屏、录制、截图存档、WebRTC 播放器（后续 D03/Q04）。
- 路由不新增页面；组件接线由 worker 在 DeviceDetailView 内完成（该文件本片归 live 线独占）。

## 安全与边界

- 观看链路与写权限分离：VIEWING 无输入权；REMOTE 才开输入。
- 所有 input 落 audit（kind/seq/坐标/会话）；服务端限速 ≤10 input/秒，超限断开 REMOTE。
- 不引入新端口/新域名；WS 与 HTTPS 同源 + 证书 pinning 沿用。
- 投屏内容含个人数据：帧不落盘、不进对象存储，仅内存中继；审计只记元数据不记画面。
- 验收：后端 pytest（状态机/单 writer/超时/seq/限速）；Android 单测（seq 校验、
  帧参数、授权状态机）；Web typecheck/build。真机验收（真投屏+接管+交还+30 分钟上限）
  由 Root 持 DEVICE 锁执行，记 Q04 前置证据。
