# live-capabilities/v1 — 投屏能力分级与交还契约（K13）

- 契约版本：`live-capabilities/v1@20260917.1`，**FROZEN**（创建即冻结；实现不得反向改写本契约，只能新增独立版本目录）。
- 结构化定义：[live-capabilities-v1.schema.json](./live-capabilities-v1.schema.json)（根节点校验单份 live 文档：`session` / `input_rejection` / `handover` / `terminal` 四型，oneOf 判别）。
- 示例与自检：[fixtures/](./fixtures/)（8 例）+ [tools/check_fixtures.py](./tools/check_fixtures.py)，见 §11。
- 本契约在 `contracts/phase1/p10-live-session-v1.md`（K04/P10 slice1，已实现）之上冻结能力分级与交还语义，**沿用不推翻** slice1；「会话语义与传输无关」原则继续成立。下游：实现任务 L10（投屏会话授权与传输分层）、真机验收 Q14（旧 Q04）。

## Provenance（前置口径，如实记录）

K13 任务卡声明 `must:["R02"]`（R02 = 单一任务源与调度校验落地，GOVERNANCE）。截至本契约冻结时，R02 尚未执行（dev_state=NOT_STARTED）。但 `docs/current/tasks.json` 自 2026-09-16 起已是事实上的唯一活动计划：W0–W3 及 DEVICE_GATE 四波派发均以该文件为准，revision_log 在案。本轮按「R02 前置 de-facto 满足」口径执行 K13。本注记**不声称 R02 已完成**；R02 正式落地后本契约效力不变，无需回溯改写。

## 1. 三档能力分级

| 档位 | 能力边界 | 传输 | input 通道 | UI 标识（uiLabel） | TURN 依赖 |
|---|---|---|---|---|---|
| `JPEG_PREVIEW` | 只读观察 | `JPEG_WS`（slice1 既有） | **禁止** | `preview` | 无 |
| `INTERACTIVE_REMOTE` | 控制（接管） | `JPEG_WS` | 允许 | `interactive` | 无 |
| `WEBRTC` | 控制（生产档） | `WEBRTC`（SRTP/DTLS，可经 TURN） | 允许 | `interactive-hd` | **必须** |

正交与闭集原则：

- 档位 = 能力（观察 / 控制）× 传输（JPEG / WebRTC）的闭集组合，合法组合**仅上表三种**；`tier × transport` 其他组合一律 `422 LIVE_TIER_UNSUPPORTED`。
- `allowsInput` / `uiLabel` / `turnRequired` 是**档位的派生常量**（schema 以 const 钉死），不是可自由声明的字段：`JPEG_PREVIEW` 恒为只读，input 通道仅 `INTERACTIVE_REMOTE` / `WEBRTC` 开放。
- 会话语义（状态机、租约、审计、超时）对三档一致；换传输档不换语义。
- 能力标识是档位的一字段：会话建立响应必须携带档位派生的能力标识，旧 JPEG 帧流会话仅帧下行时 UI **不得**标「完整远控 / 远控中」或渲染输入控件（见 §7）。

## 2. 会话绑定与状态机（沿用 slice1，冻结）

- 会话 = 一行 `device_lease` 扩展用途 `LIVE`（复用既有租约/epoch，不加新表）。会话绑定四元组 `(tenantId, deviceId, operatorId, sessionId)` + `lease {deviceLeaseId, epoch, purpose:"LIVE"}`；**epoch 单调递增**，新会话 epoch 必须大于同线旧值，旧 epoch 上的一切输入与操作拒绝。
- 服务端为唯一裁决者：`CLOSED → VIEWING`（Companion ack 投影授权后建立）`→ REMOTE`（take-control）`→ VIEWING`（release 交还）；任一态 `→ CLOSED`（§6 终态原因）。跨进程不得以某进程内 `has_remote` 作为唯一事实（L10 双进程争抢同设备 remote 仅一个成功）。
- 单 writer：`REMOTE` 期间设备禁止 claim 新任务、在跑任务强制 `PAUSED_WAITING_USER`；交还后恢复排队（§5）。`VIEWING` 不影响任务。
- 硬上限：会话总时长 30 分钟（`maxDurationMinutes` const 30，服务端强制 CLOSED）；无帧/无心跳 30 秒 → 强制 `REMOTE→VIEWING`，再 10 秒宽限无恢复 → CLOSED（slice1 原语义）。
- seq/epoch 单调全链路双侧校验（服务端 + Companion）：事件 seq 与 input seq 会话内严格递增，重复/回退丢弃、计数、告警。
- input 归属校验：必须命中 `(sessionId, tenantId, deviceId, operatorId)` 且当前态为 `REMOTE` 且档位 `allowsInput=true`，否则按 §4 拒收并审计。

## 3. 帧坐标变换规范

**坐标空间**：

- 帧空间：投屏帧像素坐标 `(fx ∈ [0, frameWidth), fy ∈ [0, frameHeight))`，原点左上。**input 坐标一律以帧空间为准**。
- 设备空间：当前方向下显示平面像素 `(dx ∈ [0, deviceWidth), dy ∈ [0, deviceHeight))`。
- 帧描述符 `frameGeometry = {frameWidth, frameHeight, deviceWidth, deviceHeight, rotation ∈ {0,90,180,270}, safeArea?}` 随会话能力下发；几何变化（旋转/分辨率变更）必须重新下发，自新 frameSeq 起生效。`safeArea` 以**设备空间**像素表达（挖孔/刘海/系统栏排除区）。

**产帧变换（正向，编码器执行）**：设备空间 --按 `rotation` 图像坐标顺时针旋转--> 中间空间 --缩放至帧尺寸--> 帧空间。中间空间维度 `(uw,uh) = rotation∈{0,180} ? (deviceWidth,deviceHeight) : (deviceHeight,deviceWidth)`。

**input 执行（逆向，Companion 执行，产帧变换的严格逆）**：

1. 先逆缩放：`u = fx · uw / frameWidth`，`v = fy · uh / frameHeight`（连续坐标，0 起）。
2. 再逆旋转（查表）：
   - `rotation=0`：`dx = u`，`dy = v`
   - `rotation=180`：`dx = (uw−1) − u`，`dy = (uh−1) − v`
   - `rotation=90`：`dx = v`，`dy = (uw−1) − u`
   - `rotation=270`：`dx = (uh−1) − v`，`dy = u`
3. 末端四舍五入到设备像素。
4. **越界与安全区**：逆映射结果落在设备平面外或 `safeArea` 排除区内 → **丢弃该 input、计数、审计**；禁止静默钳到屏幕边缘（防误触错误 UI 元素）。几何变化前的旧坐标由 §4 frameSeq 过期规则兜底。

**职责切分**：服务端**不变换坐标**，仅透传并校验归属/档位/seq/TTL；Web 端只产生帧空间坐标；Companion 持有产帧变换核并执行其严格逆（与产帧共用同一变换实现，防两套公式漂移）。禁止 Web/服务端预变换坐标。

## 4. 手势过期（input TTL 与水位）

服务端按会话维护 `inputWatermark`（已接受最大 input seq）与 `latestFrameSeq`（已下发最大帧 seq）；每个 input 携带 `seq` 与 `frameSeq`（操作者所见帧）。拒收规则（拒收即不执行，一律审计，拒收响应回带 `{code, inputWatermark, latestFrameSeq}` 供客户端对齐）：

1. `seq <= inputWatermark` → `INPUT_SEQ_REGRESSION`（重复/回退丢弃计数；短窗多次 → 断开 REMOTE）。
2. `latestFrameSeq − frameSeq > staleFrameThreshold`（默认 10，闭集 [1,30]）→ `INPUT_EXPIRED`。
3. `frameSeq` 对应帧下发距今超过 `ttlExpiryMs`（默认 2000ms，闭集 [500,5000]）→ `INPUT_EXPIRED`。
4. 档位 `allowsInput=false`（或非 REMOTE 态）收到任何 input → `LIVE_INPUT_FORBIDDEN`。
5. 速率 > `maxInputRatePerSecond`（上限 10/秒，slice1 值）→ `LIVE_RATE_LIMITED` 并断开 REMOTE。

## 5. 所有权交还（REMOTE → VIEWING）

- 交还后**恢复排队语义**：`PAUSED_WAITING_USER` 任务回到排队资格——普通暂停任务 `REQUEUE_AUTO`（走既有 pause/resume API 恢复执行）；处于破坏性确认窗口（UNKNOWN 等）的任务 `CONFIRM_REQUIRED`，**必须人工确认后才恢复**，禁止交还即自动恢复 RUNNING（Q14 场景：auto 暂停 → remote → 交还 → 人工确认恢复）。
- 帧下行不中断（VIEWING 仍可看）；单 writer 立即恢复（设备可重新 claim）。
- 异常交还：REMOTE 期间掉线/无帧无心跳 → 服务端强制 `REMOTE→VIEWING`（10 秒宽限）→ CLOSED；同样恢复排队，不自动恢复授权。
- 抢占互斥：已有 REMOTE 时另一操作者 take-control → 409 失败，先到先得；须交还或 CLOSED 后方可再接管。
- 手势通道状态：交还即关闭 input 通道（回落 §4 规则 4）。

## 6. 系统授权与会话生命周期（MediaProjection）

- **每次新会话必须现场用户确认**（MediaProjection 系统授权）：不得静默获取、不得 ADB 预授、一次会话一次授权；用户拒绝 → 服务端 CLOSED。
- **重启即终态**：设备重启 / Companion 进程重启 / 投影服务崩溃 / 用户撤销授权 → 会话终态 `CLOSED`（schema：`resumable` const false、`reauthorizationRequired` const true、`tokenInvalidated` const true、`authorization.persistsAcrossReboot` const false）。**禁止承诺重启后静默恢复**：重新使用 = 重新发起会话 + 重新系统授权 + 新 epoch；旧 sessionId/token/通道上的任何操作 → `410 LIVE_SESSION_TERMINAL`。此约束**档位无关**，WEBRTC 档同样适用。
- 授权记录与画面分离：input 审计只记元数据（kind/seq/frameSeq/坐标/会话），不记画面；帧不落盘、不进对象存储（slice1 原则）。

## 7. slice1 JPEG 协议兼容声明

- 旧 JPEG 帧流（p10-live-session-v1 的 WS JSON 信令 `{t:"frame"|"state"|"hello"|"input"}`）**继续可用**：作为 `JPEG_PREVIEW`（默认，仅看）与 `INTERACTIVE_REMOTE`（take-control 后）两档的传输层，端点与信令不变。
- 会话建立响应必须携带档位派生能力字段（`tier`、`allowsInput`、`uiLabel`）。仅 `JPEG_PREVIEW` 时 UI 不得展示「完整远控」类标识或启用输入控件；旧客户端不识别 `tier` 字段时，帧下行照常可用，输入以服务端档位校验为准（仍会被 `LIVE_INPUT_FORBIDDEN` 拒收）。
- **Q14（旧 Q04）门禁依赖声明**：真机验收（投屏 + 接管 + 交还 + 30 分钟上限 + 抢占/掉线/旋转/锁屏）只依赖 `JPEG_PREVIEW` 与 `INTERACTIVE_REMOTE` 档成立 + MediaProjection 授权链路；**WEBRTC/TURN 不是其前置**——未选 WebRTC 传输档不得作为 Q14 阻塞理由。

## 8. 档位门禁矩阵（分层依赖）

| 门禁 | JPEG_PREVIEW | INTERACTIVE_REMOTE | WEBRTC |
|---|---|---|---|
| `GATE_LIVE_LEASE`（device_lease LIVE + epoch） | 必须 | 必须 | 必须 |
| `GATE_MEDIAPROJECTION_AUTH`（现场系统授权） | 必须 | 必须 | 必须 |
| `GATE_JPEG_TRANSPORT`（pinned HTTPS/WS 同源；≤5fps、长边≤720、JPEG 质量≤60，纯观看可降 ≤1fps） | 必须 | 必须 | —（可选回退通道） |
| `GATE_OPERATOR_WRITE`（操作员写权限 + 在跑任务暂停确认） | — | 必须 | 必须 |
| `GATE_INPUT_RATELIMIT`（≤10 input/秒，超限断开 REMOTE） | —（无输入） | 必须 | 必须 |
| `GATE_TURN_DEPLOY`（短时 TURN 凭据，TTL ≤ 1h） | — | — | 必须 |
| `GATE_BANDWIDTH_BUDGET`（带宽预算 + 连接限额） | — | — | 必须 |
| `GATE_SECURITY_REVIEW`（WebRTC 安全审） | — | — | 必须 |

- 首片仅有 JPEG 预览/交互时，`TURN/WebRTC` 不是硬依赖；Q14 按上表前两列验收。
- `WEBRTC` 为独立生产门：`GATE_TURN_DEPLOY` / `GATE_BANDWIDTH_BUDGET` / `GATE_SECURITY_REVIEW` 未全过前不得对生产租户开放（放行记 `live.tier.granted` 审计）；档内 TURN 不可用可降级拒绝（`503 LIVE_TURN_UNAVAILABLE`），不静默降档冒充。

## 9. 错误码（共享 problem+json envelope，`urn:cloudctl:problem:<code.lower()>`）

| 码 | HTTP | 语义 |
|---|---|---|
| `LIVE_INPUT_FORBIDDEN` | 403 | 只读档/非 REMOTE 态的 input（会话保持） |
| `INPUT_EXPIRED` | 422 | 手势过期（frameSeq 过旧或超 TTL；会话保持） |
| `INPUT_SEQ_REGRESSION` | 422 | input seq 重复/回退（会话保持；多次触发断 REMOTE） |
| `LIVE_RATE_LIMITED` | 429 | input 超速，断开 REMOTE |
| `LIVE_TIER_UNSUPPORTED` | 422 | 非法 tier×transport 组合或租户未开放该档 |
| `LIVE_SESSION_TERMINAL` | 410 | 终态会话上的任何操作（含重启后旧会话恢复尝试） |
| `LIVE_AUTH_REQUIRED` | 428 | 缺现场 MediaProjection 系统授权 |
| `LIVE_TURN_UNAVAILABLE` | 503 | 仅 WEBRTC 档：TURN 不可用，拒绝建档而非静默降档 |

租户越权复用 `NOT_FOUND`（404）。

## 10. 审计事件

沿用 slice1 `live.session.*`（established / take-control / release / closed / input 元数据）；新增 `live.tier.granted`（档位对租户/会话生效记录，WEBRTC 生产门放行必须留痕）。

## 11. 校验与证据

示例文档（fixtures/，8 例）覆盖验收用例全集：

| 验收用例 | fixture |
|---|---|
| 三档会话建立 | `k13-positive-session-jpeg-preview` / `-interactive-remote` / `-webrtc` |
| 交还（REMOTE→VIEWING 恢复排队） | `k13-positive-handover-remote-to-viewing` |
| 手势过期拒绝 | `k13-negative-gesture-expired` |
| 只读档 input 拒绝（能力边界） | `k13-negative-input-in-preview` |
| input seq 回退拒收 | `k13-negative-input-seq-regression` |
| 重启后会话终态（禁静默恢复） | `k13-negative-resume-after-reboot` |

自检命令与记录（2026-09-17，本 worktree 内实测）：

```
cd contracts/live-capabilities/v1
PYTHONPATH=/tmp/k13-jsonschema-pkg <主仓>/.venv/bin/python tools/check_fixtures.py   # mode=jsonschema（临时目录安装 jsonschema 4.26.0，未改主仓 .venv）
<主仓>/.venv/bin/python tools/check_fixtures.py                                      # mode=structural（退化路径）
```

两种模式各跑一遍均 8/8 OK、exit 0；另做 7 项负向变异探针（预览档带 inputPolicy/allowsInput=true、tier×transport 非法组合、persistsAcrossReboot=true、WEBRTC 缺 turn、terminal.resumable=true、rate=50）全部被 schema 拒绝。实际采用：**jsonschema 真校验**（主仓 .venv 缺 jsonschema，经 `uv pip install --target /tmp` 零污染补装）；脚本自身保留结构断言退化路径并打印实际模式。
