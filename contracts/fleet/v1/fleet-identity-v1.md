# fleet-identity/v1 契约 — FROZEN 20260916.1

状态：**FROZEN（已冻结）**，版本 `fleet-identity/v1@20260916.1`。起草人：W0 总控（fleet-first K10）。基线 `781b2d0`。消费者：A10（fleet_identity 差额实现）、A11（领取/重领/固定 steps 修复）、A12、B10（Companion 单写者仲裁）、B11、C10/C11（设备工作台）、A13、Q10/Q12、I10、U10/U11、L10/L11、D11、X10、F12/F13。

上位契约（已冻结，本契约只补差额，不重复定义）：
- `contracts/phase1/command-v1.schema.json`（deviceId/accountId/bindingVersion/snapshot/recipe/lease）
- `contracts/parallel/K03/task-schedule-v1.md`（双状态机、每设备单 CLAIMED/RUNNING、fencing、幂等键）
- `contracts/phase1/p09-controlled-action-ledger.md` + `p09-action-identity-golden.json`（动作台账与 actionKey 公式）
- P09-19 释放协议（2026-09-16 冻结：仅 CLAIMED/PREFLIGHT 且首次 heartbeat 前可释放回 QUEUED）

## 1. 范围与边界

- 冻结多机身份、会话、能力表、稳定动作身份、四态映射、单写者与账户互斥、固定 steps 任务身份、领取守卫的**差额**。
- 不新建第二套认证（A10 复用 Enrollment/MobileBinding）；不改 command-v1 已冻结字段含义。

## 2. 舰队身份字段（冻结）

信封层 `FleetEnvelope`（调度/台账/API 一致）：

| 字段 | 语义 | 冻结规则 |
|---|---|---|
| `tenantId` | 租户 | 一切读写按租户隔离（同 K02 §2）；信封必填 |
| `deviceId` | 设备 | Enrollment 产出的稳定 ID；`online` 与 `executable` 分开判定 |
| `accountId` | 平台账号 | **现状债务**：steps 家族现在以 device_id 冒充 account_id（mobile_actions.py `_steps_action_row`）；A10 落地真实账号字段时保持 actionKey 公式不变、只替换输入值，并在台账新增列区分 |
| `bindingVersion` | 绑定版本 | 沿用 command-v1；参与 parameterHash |
| `sessionId` | Companion 进程会话 | 每次进程注册生成；只入遥测与授权信封，**不入 actionKey** |
| `bootId` | OS 启动会话 | 判定 lease 跨启动失效；只入授权信封，**不入 actionKey** |

`online` = 传输心跳存在；`executable` = online ∧ 无障碍 enabled∧active ∧ IME 就绪 ∧ 屏幕解锁 ∧ 版本 profile ≥ 所需 minEngine。**两者不得混用**：调度资格看 executable，列表在线状态只看 online。

## 3. 能力表与兼容策略（冻结）

`capabilities` 为封闭键集（V1：`accessibility`、`ime`、`screen_capture`、`media_projection`、`flutter_anchors`、`im_listen`），每键 `{supported: bool, engineMin?: int}`。
- 任务侧 `requiredCapabilities`（command-v1 已有字段）与之求交：缺必备能力 → 设备 `INELIGIBLE_CAPABILITY`，任务不派发，**不是失败**。
- 协议向后兼容：新增能力键只增不改；不具备新能力的设备按 `supported=false` 拒绝对应任务，不影响既有任务族。

## 4. 稳定动作身份 vs 动态授权信封（冻结，⚠ P09 事故核心）

- `actionKey = sha256("cloudctl.action/v1\n{taskId}\n{recipeSha256}\n{actionId}")`
- `parameterHash = sha256("cloudctl.action-parameters/v1\n{taskId}\n{commandType}\n{accountId}\n{bindingVersion}\n{snapshotSha256}\n{recipeSha256}")`
- **禁止**把 controlEpoch/fencingToken/leaseExpiresAt/sessionId/bootId 混入两哈希的输入——它们属于**动态授权信封** `AuthorizationEnvelope{controlEpoch, fencingToken, leaseExpiresAt, sessionId, bootId}`，仅在 dispatch 时独立校验。
- 提交前恢复（pre-commit）：信封不匹配 → 拒绝执行，actionKey 不变。
- 提交后恢复（post-commit）：台账行已存在 UNKNOWN → 只允许对账路径（RECONCILING）收敛，**重领/取消/新信封都不能使该动作重新可提交**。

## 5. 四态映射（冻结，记录义务）

| 云端 runner status | business_state（操作员视角） | Companion 本地执行态 | 动作台账 |
|---|---|---|---|
| QUEUED | PENDING_* / PAUSED_WAITING_USER 等 | 无本地态 | 无行 |
| CLAIMED/PREFLIGHT | 同上（未开始） | claimed 预检 | 无行（首次 dispatch 才建） |
| RUNNING | RUNNING_* | step 执行中 | 行按动作逐条落 |
| SUCCEEDED/FAILED | SUCCEEDED/FAILED_* | settled | 终态行（APPLIED/UNKNOWN） |
| RECONCILING | RECONCILING | 对账中 | UNKNOWN 行待收敛 |

- `dev_state`/`acceptance_state` 是**计划层字段**（docs/current/tasks.json），永远不由运行态自动推导。
- 状态迁移断言由 A04/A11 测试落地；本契约只钉映射表。

## 6. 单写者与账户互斥（冻结）

1. 每设备至多一条 CLAIMED/RUNNING（K03 已冻结，重申）。
2. **新增**：每 `(tenantId, accountId)` 至多一条 RUNNING 写任务，跨设备生效；违反 → `409 ACCOUNT_BUSY`（code 见 §9）。读任务（采集/IM 监听）不受此条限制，但须在任务定义显式声明 `writeEffect: false`。
3. Companion 侧一切写路径（Recipe、固定 steps、IME、IM 值班动作、remote 手势、Edge 写）经同一 DeviceArbiter（B10）申请；被动监听不导航。

## 7. 固定 steps 任务身份（家族 B，冻结）

- 无 Recipe 的 UNPINNED_STEPS_COMMANDS 任务：`payloadIdentity = sha256(canonical_steps(steps))`（公式已跨语言冻结：按步、按 key 排序、`k=v` 行、`\n` 连接、bool 小写）。
- 首次领取冻结 `{payloadIdentity, commandRegistryVersion}`（commandRegistryVersion = STEPS_SHAPES 注册表版本字符串，A11 落地常量）；重领校验两者不变，且账号绑定与提交台账无未收敛 UNKNOWN 行——**不允许为通过重领而删除版本守卫**。
- 合法固定 steps ≠ 损坏 legacy：区分判据 = commandType 在 STEPS_SHAPES 注册表内（合法）与否（legacy 弃用路径）。

## 8. 领取/释放/重领守卫（冻结）

- 释放：仅 CLAIMED/PREFLIGHT 且首次 heartbeat 前，按当前 lease 释放回 QUEUED（P09-19 协议原文，重申）。
- 重领前置：无 open UNKNOWN 台账行；有 → 409 先对账（KEEP_WAITING 语义）。
- UNKNOWN 不因取消而消失：CANCELLED 任务若含 UNKNOWN 行，台账保留并挂 RECONCILING 跟踪。

## 9. 错误码（冻结，problem+json 沿用 K02 §5 形状）

新增：`ACCOUNT_BUSY/409`、`INELIGIBLE_CAPABILITY/422`（派发前校验）、`RECONCILE_REQUIRED/409`（open UNKNOWN 重领）、`AUTHORIZATION_ENVELOPE_STALE/409`（信封过期/不匹配）。

## 10. fixtures 与跨语言验证

- `fixtures/k10-positive-fleet-claim.json`：合法领取信封 + 期望 actionKey/parameterHash（由本契约公式计算、脚本复核）。
- 负例：`k10-negative-actionkey-contains-epoch.json`（哈希输入混入动态字段 → 校验拒绝）、`k10-negative-account-busy.json`（同账号第二写任务 409）、`k10-negative-reclaim-open-unknown.json`（open UNKNOWN 重领 409）。
- **跨语言同等性**：`tools/check_fixtures.py` 用上述冻结公式重算既有跨语言金样 `mobile/companion/app/src/test/resources/steps-identity-golden.json` 的 actionKey/parameterHash 并断言相等（该金样已由 `ControlledStepsIdentityTest` 在 Kotlin 侧验证）——证明算法实现与跨语言已验证版本一致；新 fixtures 期望值由同一算法产出。
- **消费者义务**：A10/A11 必须新增读取本目录 fixtures 的镜像测试（Python + Kotlin），B10 仲裁器测试引用 §6 规则；未落地前不得宣称 K10 验收范围完成。

## 11. 验证命令（起草时实际执行）

```
python3 contracts/fleet/v1/tools/check_fixtures.py   # 退出码 0
python scripts/plan_guard.py docs/current/tasks.json # valid
```
