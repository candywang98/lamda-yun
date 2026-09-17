# control-plane/v1 契约 — FROZEN 20260917.1

状态：**FROZEN（已冻结）**，版本 `control-plane/v1@20260917.1`。起草人：W0 总控（K14）。基线 `c55da0d`。消费者：A14（服务端热修+端点）、B17（Companion 控制同步客户端）、Q12 扩展用例、Q13 设备验收。

上位契约：`fleet-identity/v1@20260916.1`（§5 四态映射、§8 守卫）、`task-schedule/v1@20260916.1`（K03 状态机/控制事件 revision）。本契约把 A12 的 per-task 控制事件升级为**设备级控制面**，依据 2026-09-17 外部专家评审（scope-decisions D-7）。

## 0. 冻结不变量（本契约存在的原因）

> **工作获取（claim）可以被本地执行状态与无障碍就绪度 gate；控制面同步（control-plane synchronization）永远不能被任何本地执行状态、队列状态或无障碍就绪度 gate。**

违反场景（已发生的事故）：本地 PAUSED 镜像阻塞 claim → 控制事件只随 claim 下发 → 永远收不到取消 → 永久死锁。

## 1. 设备控制序列 deviceControlSeq（冻结）

- 每设备一个**全设备单调递增**整数 `deviceControlSeq`（独立于 per-task revision；per-task revision 保留用于任务行校验）。
- 每个控制事件（CANCEL/CANCEL_REQUESTED/RESUME/MARKED_UNKNOWN/ABANDON/TERMINAL/SET_CONFIRM_DEADLINE）落库时消耗一个 seq。
- 客户端凭证：`lastAppliedControlSeq`——与本地镜像状态变更**同事务**持久化（apply event + update mirror + update lastApplied + COMMIT）；任意时点崩溃后重放幂等。

## 2. 端点（冻结）

### 2.1 游标拉取（catch-up，权威通道）
```
GET /companion/v2/control?after=<lastAppliedControlSeq>&limit=<1..50>
→ 200 {
     "from": n+1, "through": m, "highWatermark": m,
     "events": [ {"seq": s, "taskId": t, "taskRevision": r, "type": "...", "issuedAt": iso} ]
   }
```
- 设备凭证鉴权（binding token），不依赖 claim。
- `after` 早于保留窗起点（事件已被压实）→ **不返回空列表假装无变化**，返回：
```
410 GONE { "code": "CURSOR_TOO_OLD", "snapshotRequired": true }
```

### 2.2 快照兜底（authoritative snapshot，最终收敛保证）
```
GET /companion/v2/reconcile-snapshot
→ 200 {
     "controlHighWatermark": m,
     "tasks": [ {"taskId": t, "status": serverRunnerStatus, "businessState": b,
                 "taskRevision": r, "terminal": bool, "ledgerBlocks": bool} ]
   }
```
- 返回服务器当前认为该设备涉及的全部任务（active/paused/terminal 有限集）。
- 客户端以快照为准收敛镜像；**事件是加速器，快照才是收敛保证**（错过任意历史事件后仍可收敛）。

### 2.3 heartbeat 携带水位（discovery，逃生通道）
```
POST /companion/v2/devices/heartbeat
  请求增补: { "lastAppliedControlSeq": n, "safetyBarrier": "NONE|UNKNOWN|RECONCILING" }
  响应增补: { "controlHighWatermark": m, "inlineEvents": [ …≤2 条… ] }
```
- `highWatermark > lastApplied` 且 inline 未覆盖 gap → 客户端调 2.1；410 则调 2.2。

## 3. PAUSED/UNKNOWN 收敛规则（冻结，替代已废弃的本地超时跳过）

1. **本地时钟/时长永远不是解除 PAUSED 或 UNKNOWN blocker 的依据**（D-7：本地时长与任务有效性无逻辑关系）。
2. 服务器可对 open-only 人工确认点声明 `humanConfirmDeadline`（任务级，随任务数据下发）；到期由**服务器**产生 `ABANDON`/`CANCEL` 控制事件（权威解除）。
3. 客户端本地检测「PAUSED 超过预期且控制水位落后」最多转为 `SUSPECT_ORPHANED`：上报告警 + 强制 control sync + 触发 snapshot 对账 + **禁止领取新的破坏性任务**；不得自行解除 blocker、不得跳过。
4. **task mirror 与 action safety ledger 解耦**：服务器任务终态 ⇒ 镜像可收敛；本地 UNKNOWN 台账行**不因任务终态而清除**，继续阻断相关危险操作直至显式对账（A12 语义保持）。

## 4. CANCEL 的 apply/ack 语义（冻结）

```
server desired: CANCEL
  → device 收到（经 §2 任一通道）
  → device 中性化 UI（丢弃表单/退出确认页/回退导航）
  → device: CANCEL_APPLIED {taskId, taskRevision}     ← ack 端点: POST /companion/v2/control/ack
  若设备无法安全回退（存在 UNKNOWN/不可逆已提交）:
  → CANCEL_DEFERRED_RECONCILING {taskId, reason}       ← 服务器保持 RECONCILING，转人工对账
```
- 服务器收到 ack 前，CANCEL 是 desired 而非 done；避免「服务器已终态、屏幕旧表单仍是被延迟的副作用源」。

## 5. 错误码（沿用 K02 §5 形状）

`CURSOR_TOO_OLD/410`、`CONTROL_SEQ_INVALID/422`、（既有）`RECONCILE_REQUIRED/409`、`AUTHORIZATION_ENVELOPE_STALE/409`。

## 6. fixtures（随契约冻结）

- `k14-positive-control-batch.json`：3 条事件（CANCEL+ABANDON+SET_CONFIRM_DEADLINE）+ seq 单调 + watermark。
- `k14-negative-local-timeout-unblock.json`：本地超时自动解除 PAUSED = **契约禁止**（负例钉死 D-7）。
- `k14-negative-cursor-too-old.json`：410 + snapshotRequired。
- `k14-positive-cancel-ack.json`：CANCEL→APPLIED 与 DEFERRED_RECONCILING 两分支。

## 7. 验证命令（起草时实际执行）

```
python3 contracts/control-plane/v1/tools/check_fixtures.py   # 退出码 0
python3 scripts/plan_guard.py docs/current/tasks.json        # valid
```

**消费者义务**：A14 落地 §2 端点与 §2.3 热修（heartbeat 先行携带 blocking task 权威态）；B17 落地客户端同事务应用与 SUSPECT_ORPHANED；Q12 增补「控制面永不被 gate」的联测用例。
