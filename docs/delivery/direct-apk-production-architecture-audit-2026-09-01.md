# APK 直连生产架构审计与落地合同

- 审计日期：2026-09-01
- 审计范围：`services/control-api`、`apps/web`、`mobile/companion`、现有 Edge Companion API、数据库与 API contracts
- 目标模型：工作台直达 Control API；手机 APK 主动出站直连 Control API、本地独立执行并回传；生产不依赖 Edge Gateway 或 ADB
- 本文性质：实现级架构审计，不修改业务代码

## 1. 结论

当前仓库还不能按目标模型投入生产。

现有 Web 的 Operations 页面已经把 Control API 作为主要入口，但设备、任务等核心页面仍从 `apps/web/src/api/client.ts` 读取 Mock。现有 Android Companion 只会向 Edge 注册、上报健康、拉取快照、确认和紧急停止；它没有云端命令认领、本地持久任务日志、租约续期、执行事件回放、证据上传和重启恢复。Control API 的 Operations 则把执行器理解为内置执行器或服务端 URL，没有“投递到指定 APK 本地执行器”的运行模式。

`db.py` 已出现 `MobileEnrollmentRow`、`MobileBindingRow`、`MobileTaskRow`、`MobileTaskEventRow` 的原型，但目前没有对应 Alembic migration、route、service、repository、认证依赖或测试，且原型字段不足以表达安全投递、fencing、证据验证和不可逆提交恢复。因此它们只能视为未接线草稿，不能视为已实现。

生产目标应收敛为：

```text
Web/OIDC 用户 ──HTTPS──> Control API <──HTTPS 长轮询/WSS── Android Companion
                              │                           │
                              ├── PostgreSQL              ├── 本地持久 journal
                              └── S3 兼容对象存储 <──上传──┘
```

Edge Gateway 和 ADB 均不在生产依赖链中。ADB 只用于开发安装、日志与真机调试；不得成为任务投递或执行前置条件。浏览器不得直接连接手机私网端口，也不得持有设备凭据。

## 2. 当前实现与目标的差距

| 领域 | 当前实现 | 缺口/风险 | 目标处理 |
| --- | --- | --- | --- |
| 人员鉴权 | `auth.py` 验证 OIDC，并构造用户 `Actor` | 没有与人员完全隔离的设备 principal | 新增设备认证依赖和 `DevicePrincipal`；不可复用用户角色头 |
| 设备注册 | Edge `/companion/v1/enroll`；`db.py` 有未接线 mobile 表草稿 | 状态存 Edge SQLite；云端无可撤销设备凭据生命周期 | Control API 发一次性 challenge；APK 用硬件密钥完成绑定；短期 access token |
| 设备健康 | APK 向 Edge `/health`，再从 `/snapshot` 读状态 | 云端看不到可靠的 APK runner/cursor/capability 状态 | APK 直报版本化 heartbeat，服务端持久化当前快照 |
| 任务创建 | `OperationTaskRow`/`OperationItemRow` | task 与投递、执行 attempt 混在同一层；没有目标 device/command | 保留业务 task，新增 command/delivery/attempt 层 |
| 执行器 | `OperationExecutorRegistry`：内置或 HTTP executor URL | 无 APK-local executor；可能把设备动作错误地放到服务端执行 | catalog 增加 `executorKind=apk_local`，生成允许列表命令 envelope |
| 实时更新 | Web 使用 `/events` SSE 或 `/events/poll` | 只适合用户观察，不适合 APK 可靠领取 | APK 使用 durable long-poll；WSS 仅加速；Web 继续 SSE/poll |
| 租约 | `DeviceLeaseRow` 有 lease/fencing | 只有用户控制接口；APK 不能 claim/renew/校验 fence | 在 command start/renew/complete 中原子校验 lease/fence |
| 不可逆提交 | 已有 `CommitIntentRow` 与 ADR-0002 | 尚未与 APK command attempt/journal 关联 | intent 先落云端并被 APK journal 确认，commit 只尝试一次，掉线进入 `COMMIT_UNKNOWN` |
| 证据 | operation item 仅存字符串 refs；debug evidence 接受 object ref | 客户端可声称任意引用；无 upload session/对象验证 | prepare → 预签名上传 → complete → 服务端验证 hash/size 后关联 |
| Android 持久性 | SharedPreferences + Android Keystore token | 没有 Room、WorkManager、前台 runner 或事件 outbox | Room journal + WorkManager 同步 + 单 runner 前台服务 |
| Web | Operations/Studio 部分走 Control API；Devices/Tasks 仍是 Mock | 无真实设备心跳、投递、claim、执行证据页面 | 所有生产页面统一 Control API；生产构建禁止 Mock fallback |

## 3. 信任边界与身份模型

### 3.1 三类主体

1. **Human principal**：浏览器通过 OIDC 登录，由现有 RBAC/MFA 管理；可创建、审批、取消、查看任务。
2. **Device principal**：每个 APK app instance 一把不可导出的 Android Keystore 私钥，绑定 tenant、device、package name、签名证书摘要和 credential ID；只能访问 `/api/v1/apk/*`。
3. **System principal**：对象验证、reconciler、outbox publisher 等内部服务；不得借用人员或设备 token。

### 3.2 设备认证推荐

- 管理员通过 Control API 为已存在 device 创建一次性、短时 enrollment challenge。
- APK 本地生成 P-256/Ed25519 硬件支持密钥，提交 public key、challenge、app instance ID、包名、签名摘要、版本和可选 Play Integrity/企业证明。
- 服务端只保存 public key、credential 状态和证明摘要，不保存 APK 私钥。
- APK 用私钥签名服务端 nonce，换取 5–15 分钟短期 access token；refresh/rotation 仍需私钥证明。
- token 的 audience、subject、tenant、device、credential ID 和 scope 固定；撤销 credential 后立即拒绝刷新并缩短已有 token 生存窗口。
- 任何 bearer token、enrollment code、签名原文不得进入 URL、审计 metadata 或应用日志。

首版如暂时不能部署 mTLS，可采用“硬件私钥签名 challenge + 短期 JWT”。长期可升级为 mTLS 设备证书，但协议主体和权限边界不变。

## 4. REST 合同

所有请求使用 `application/json`，时间为 UTC RFC 3339，ID 为服务端生成 UUID。所有 APK 写操作必须接受 `Idempotency-Key`；事件以 `(commandId, attempt, sequence)` 唯一去重。错误统一为现有 `application/problem+json`。

### 4.1 管理员/工作台接口

| 方法与路径 | 权限 | 作用 |
| --- | --- | --- |
| `POST /api/v1/devices/{deviceId}/enrollments` | `device:operate` + MFA | 创建一次性 enrollment challenge；只返回一次明文 code |
| `GET /api/v1/devices` | 已认证用户 | 返回设备、APK last seen、runner、capability、当前 command/lease 摘要 |
| `GET /api/v1/devices/{deviceId}` | 已认证用户 | 返回设备详情、凭据状态、心跳、活动投递和近期执行摘要 |
| `DELETE /api/v1/devices/{deviceId}/credentials/{credentialId}` | `security:admin` + MFA | 撤销 APK 凭据，并取消未开始投递 |
| `POST /api/v1/operations/tasks` | 沿用 operation permission | 创建业务任务；context 中显式指定 target device/scope |
| `POST /api/v1/operations/tasks/{taskId}:cancel` | 沿用现有权限 | 写 cancel intent；APK 在安全点确认 |
| `GET /api/v1/operations/tasks/{taskId}` | 已认证用户 | 汇总业务 task、item、command、attempt、evidence |
| `GET /api/v1/events` / `events/poll` | 已认证用户 | Web 状态更新；不用于 APK 命令领取 |

### 4.2 APK 注册与 token

| 方法与路径 | 身份 | 作用 |
| --- | --- | --- |
| `POST /api/v1/apk/v1/enroll` | 一次性 enrollment code | 校验 challenge 与 app identity，创建 credential/binding |
| `POST /api/v1/apk/v1/auth/challenges` | credential ID | 返回短时 nonce |
| `POST /api/v1/apk/v1/token` | signed nonce | 返回短期 access token |
| `POST /api/v1/apk/v1/credentials:rotate` | device token + 新旧私钥证明 | 原子创建新 credential 并废弃旧 credential |
| `POST /api/v1/apk/v1/devices/{deviceId}:unbind` | device token | 撤销自身 credential；不得删除审计历史 |

`enroll` 成功响应至少包含：`tenantId`、`tenantDisplayName`、`deviceId`、`credentialId`、`apiBaseUrl`、`serverTime`、`protocolVersion`。不要继续使用当前 `edgeUrl`/`certificateSha256` 作为业务 binding 字段。

### 4.3 心跳与能力

`PUT /api/v1/apk/v1/devices/{deviceId}/heartbeat`

```json
{
  "protocolVersion": 1,
  "appInstanceId": "...",
  "companionVersion": "1.0.0",
  "androidVersion": "13",
  "targetApps": {"com.example.target": "8.2.1"},
  "capabilities": {"uiAutomation": true, "evidenceCapture": true},
  "health": {"batteryPercent": 76, "charging": true, "network": "wifi", "freeStorageBytes": 123456789},
  "runner": {"state": "IDLE", "commandId": null, "attempt": null},
  "lastDeliverySequence": 82,
  "lastEventSequence": 14,
  "observedAt": "2026-09-01T08:00:00Z"
}
```

服务端以收到时间决定 online/offline；客户端 `observedAt` 只作诊断。heartbeat 不能直接改写业务 task 的终态。

### 4.4 长轮询命令投递（首版可靠通道）

`POST /api/v1/apk/v1/devices/{deviceId}/commands:claim`

请求：

```json
{
  "afterSequence": 82,
  "maxWaitSeconds": 25,
  "maxItems": 1,
  "runnerState": "IDLE"
}
```

响应：

```json
{
  "serverTime": "2026-09-01T08:00:25Z",
  "nextSequence": 83,
  "commands": [{
    "protocolVersion": 1,
    "deliverySequence": 83,
    "commandId": "...",
    "commandType": "RUN_OPERATION_ITEM",
    "operationTaskId": "...",
    "operationItemId": "...",
    "deviceId": "...",
    "attempt": 1,
    "leaseId": "...",
    "fencingToken": 19,
    "executionKey": "sha256:...",
    "inputSnapshotSha256": "...",
    "parameters": {},
    "requiredCapabilities": ["uiAutomation"],
    "artifacts": [{"artifactId": "...", "downloadUrl": "...", "sha256": "...", "sizeBytes": 123}],
    "deadlineAt": "2026-09-01T08:10:00Z"
  }]
}
```

规则：

- 只允许固定 `commandType` 和 schema；绝不接受 arbitrary shell、ADB、socket、Frida、MITM 或动态脚本文本。
- command envelope 一经 `READY` 不可变；任何变更生成新 command/attempt。
- claim 返回命令不等于已经执行。服务端记录 `DELIVERED`，APK 必须先落本地 journal，再 ACK。
- 同一 device 只允许一个非终态执行 lease。数据库通过 device row/fencing counter 原子递增，拒绝旧 fence。
- `afterSequence` 是投递 cursor，不是业务 task ID；重复返回同一 envelope 必须安全。

### 4.5 命令生命周期接口

| 方法与路径 | 语义 |
| --- | --- |
| `POST /api/v1/apk/v1/commands/{commandId}:ack` | APK 已把 envelope 持久化；`RECEIVED` 或带 reason 的 `REJECTED` |
| `POST /api/v1/apk/v1/commands/{commandId}:start` | 原子校验 device、attempt、lease、fence、deadline、capability 后进入 RUNNING |
| `POST /api/v1/apk/v1/commands/{commandId}:renew` | 续租；旧 fence、已取消或非当前 attempt 返回 409 |
| `POST /api/v1/apk/v1/commands/{commandId}/events` | 批量上传严格递增、可重复提交的结构化事件 |
| `POST /api/v1/apk/v1/commands/{commandId}:complete` | 提交终态摘要；只有证据验证完成后才可形成最终业务成功 |
| `POST /api/v1/apk/v1/commands/{commandId}:cancel-ack` | 报告已在安全点停止、未开始，或已越过不可逆边界 |
| `GET /api/v1/apk/v1/commands/{commandId}` | APK 重启后读取服务端权威状态用于恢复/对账 |

`events` 每条至少含：`attempt`、`sequence`、`eventType`、`stepKey`、`occurredAt`、`payload`、`localJournalSha256`。服务端只允许声明过的 event type；payload 有大小和字段白名单，不接受秘密、cookie、token 或任意日志块。

### 4.6 取消和不可逆提交

APK 仅在定义好的 safe point 响应取消。进入不可逆提交前：

1. Control API 持久化 commit intent，绑定 command、attempt、lease、fence 和 before-commit evidence。
2. APK 拉取/确认 intent，并在本地 journal 写入 `COMMIT_INTENT_CONFIRMED`。
3. APK 执行一次 `commit_once`，记录开始时间；无论 HTTP 超时、进程崩溃还是网络断开，都不得自动再次提交。
4. 无法确定结果时上传 `COMMIT_UNKNOWN`。服务端进入 reconciliation，观察目标状态但不重发 commit。
5. reconciler 可将 UNKNOWN 解析为成功/失败；无法确认则保留 UNKNOWN 并交人工处理。

## 5. WebSocket 合同（可选加速，不是首版可靠性基础）

路径：`WSS /api/v1/apk/v1/connect`。

- token 通过 `Authorization` header 或 TLS client cert 提交，不能放 query string。
- 首帧 `HELLO` 包含 protocol version、device/app instance、cursor 和 runner state。
- 服务端发送的 `COMMAND_AVAILABLE` 只提示 APK 立即调用 durable claim，或携带与 REST 完全相同且已持久化的 envelope。
- APK 事件帧必须与 REST 的 idempotency key、attempt、sequence 语义相同；断线后通过 REST 补传。
- ping/pong 只证明 socket 活着，不能替代 heartbeat、lease renew 或 terminal completion。
- Web 浏览器不接入此设备 socket；浏览器继续通过 Control API SSE/poll 观察状态。

这样 WSS 故障只降低延迟，不会丢命令或破坏恢复。

## 6. 持久状态机

业务 task、命令投递和本地执行必须分层，不能用一个 `status` 字段承担全部语义。

### 6.1 业务 task/item

保留现有 task 状态：`PENDING_APPROVAL`、`REJECTED`、`QUEUED`、`RUNNING`、`SUCCEEDED`、`PARTIAL`、`FAILED`、`CANCELED`，新增可见汇总态 `COMMIT_UNKNOWN`。item 终态由其 command 最终结果汇总，禁止 APK 直接任意改写 task 计数。

### 6.2 command/delivery/attempt 状态

| 状态 | 含义 | 允许后继 |
| --- | --- | --- |
| `CREATED` | command 已生成，尚未满足审批/调度 | `APPROVAL_PENDING`、`READY`、`REJECTED` |
| `APPROVAL_PENDING` | 等待职责分离审批 | `READY`、`REJECTED`、`CANCELED` |
| `READY` | 可被目标 APK 领取 | `DELIVERED`、`CANCELED`、`EXPIRED` |
| `DELIVERED` | 已在 claim 响应中返回 | `RECEIVED`、`READY`、`EXPIRED` |
| `RECEIVED` | APK 已持久化 ACK | `CLAIMED`、`REJECTED`、`CANCELED` |
| `CLAIMED` | start 原子验证成功、持有当前 fence | `RUNNING`、`CANCEL_REQUESTED` |
| `RUNNING` | 本地 executor 执行中 | `WAITING_CONFIRMATION`、`CANCEL_REQUESTED`、终态、`COMMIT_UNKNOWN` |
| `WAITING_CONFIRMATION` | 等待明确的人工确认 | `RUNNING`、`CANCEL_REQUESTED`、`EXPIRED` |
| `CANCEL_REQUESTED` | 云端已写取消意图 | `STOPPING`、`CANCELED`、`COMMIT_UNKNOWN` |
| `STOPPING` | APK 正在安全点停止 | `CANCELED`、`FAILED`、`COMMIT_UNKNOWN` |
| `SUCCEEDED` | 已完成且必需证据已验证 | 终态 |
| `FAILED` | 明确失败 | 终态；新 attempt 必须新建 |
| `CANCELED` | 在安全点停止/未开始 | 终态 |
| `COMMIT_UNKNOWN` | commit 尝试后结果不确定 | reconciliation → `SUCCEEDED`/`FAILED`，或保持 |
| `EXPIRED` | deadline 前未安全开始 | 终态 |
| `REJECTED` | 能力、schema、身份或策略拒绝 | 终态 |

任何重试都创建新的 attempt，旧 attempt 不覆盖。stale fencing token、旧 attempt completion、倒退 sequence 一律拒绝并写安全审计。

### 6.3 APK 本地 journal

APK 必须至少持久化：

- command envelope 原文的 canonical SHA256、delivery sequence/cursor；
- command ID、attempt、lease ID、fencing token、deadline；
- 本地状态与每次状态变更时间；
- 待上传事件及 last acknowledged event sequence；
- artifact 的预期/实际 SHA256、下载状态；
- commit intent receipt、commit 是否已开始/已返回；
- 待上传 evidence manifest/object 状态；
- terminal result 是否已被服务端确认。

重启后先恢复 journal，再向 Control API 对账；不得因为进程重启把 RUNNING 命令当成新命令执行。单设备只有一个 foreground runner，可并行做网络上传，但不能并行执行两个 UI automation command。

## 7. 证据与结果上传

### 7.1 合同

1. `POST /api/v1/apk/v1/commands/{commandId}/evidence:prepare`
   - 请求 manifest：kind、sha256、sizeBytes、contentType、attempt、eventSequence、captureTime、redaction profile。
   - 服务端创建 evidence row 和限定 object key，返回短期预签名 PUT。
2. APK 直接上传对象存储；上传 URL 不写日志。
3. `POST /api/v1/apk/v1/commands/{commandId}/evidence/{evidenceId}:complete`
   - 服务端执行 HEAD/metadata 校验，必要时后台流式计算 SHA256。
4. 只有 `VERIFIED` evidence 才能关联 operation item 并满足完成条件。

### 7.2 evidence 字段

`tenant_id`、`device_id`、`operation_task_id`、`operation_item_id`、`command_id`、`attempt`、`kind`、`sha256`、`size_bytes`、`content_type`、`object_key`、`capture_sequence`、`captured_at`、`redaction_state`、`verification_state`、`verified_at`、`retention_until`。

禁止接受客户端自造 `s3://...`/URL 字符串作为证据。截图、UI tree、结构化 result 和日志均要有大小限制、敏感字段脱敏与保留策略。

## 8. 数据库落地

建议在现有 operation 表之外增加/重构以下表：

| 表 | 关键约束 |
| --- | --- |
| `device_enrollment` | code digest 唯一、短时有效、单次消费、绑定 tenant/device/creator |
| `device_credential` | public key、app instance、package/signing digest、status、rotated/revoked timestamps；无明文 token |
| `device_heartbeat` 或 device current snapshot | device 唯一当前快照；可选历史分区表 |
| `apk_command` | immutable envelope/hash、task/item/device、delivery sequence、command type、deadline |
| `apk_command_attempt` | `(command_id, attempt)` 唯一；lease/fence/state/result/timestamps |
| `apk_command_event` | `(command_id, attempt, sequence)` 唯一 |
| `apk_evidence` | `(command_id, attempt, sha256, kind)` 唯一；object verification 状态 |
| `apk_upload_session` | evidence、object key、过期时间、completed/verified 状态 |
| `apk_delivery_cursor` | 每 device 单调 sequence 与 ack cursor |

现有 `Mobile*Row` 草稿不应原样迁移：`MobileTaskRow.lease_id` 没有 fencing token，task 与 attempt 未分离，`steps` 可接收任意 JSON，event 缺少 attempt，binding 使用长期 token digest 且没有 key/rotation/revocation provenance，也没有 evidence/upload 表。可保留命名并扩展，也可改为上述更明确的 `Apk*` 命名，但 migration 必须一次性确定约束。

## 9. 精确实现文件清单

### 9.1 Control API 新增

- `services/control-api/src/cloudctl_api/device_auth_routes.py`
- `services/control-api/src/cloudctl_api/device_auth_schemas.py`
- `services/control-api/src/cloudctl_api/device_auth_service.py`
- `services/control-api/src/cloudctl_api/device_auth_repository.py`
- `services/control-api/src/cloudctl_api/apk_command_routes.py`
- `services/control-api/src/cloudctl_api/apk_command_schemas.py`
- `services/control-api/src/cloudctl_api/apk_command_service.py`
- `services/control-api/src/cloudctl_api/apk_command_repository.py`
- `services/control-api/src/cloudctl_api/apk_evidence_service.py`
- `services/control-api/src/cloudctl_api/apk_websocket.py`（阶段 6，可选）
- `services/control-api/migrations/versions/20260901_0007_add_direct_apk_identity_and_delivery.py`

### 9.2 Control API 修改

- `services/control-api/src/cloudctl_api/app.py`：注册 device auth/command router、service 和可选 WSS。
- `services/control-api/src/cloudctl_api/auth.py`：新增独立 `DevicePrincipal`/device token verifier；保持 `current_actor` 仅供人员接口。
- `services/control-api/src/cloudctl_api/db.py`：替换/扩展未接线 `Mobile*Row` 草稿，增加 command attempt/evidence/cursor 约束。
- `services/control-api/src/cloudctl_api/settings.py`：设备 token issuer/audience/TTL、challenge TTL、poll 限制、lease TTL、object verify、WSS 开关。
- `services/control-api/src/cloudctl_api/operation_catalog.py`：为可下发操作声明 `executor_kind=apk_local`、command schema、capabilities 和 completion evidence policy。
- `services/control-api/src/cloudctl_api/operation_runtime.py`：把 `apk_local` 从服务端 URL executor 分离为 durable command dispatch。
- `services/control-api/src/cloudctl_api/operation_service.py`：审批/创建后生成 immutable command；由 command 汇总 item/task 状态。
- `services/control-api/src/cloudctl_api/operation_repository.py`：command/task/item 原子关联和状态聚合。
- `services/control-api/src/cloudctl_api/operation_routes.py`、`operation_schemas.py`：暴露 delivery/attempt/evidence 视图。
- `services/control-api/src/cloudctl_api/routes.py`、`schemas.py`、`services.py`、`repository.py`：设备详情、enrollment 管理和 heartbeat 视图；可逐步拆出 device 模块。
- `services/control-api/src/cloudctl_api/media_store.py`：限定 evidence object key、预签名上传和服务端验证。

### 9.3 API contracts

- `packages/api-contracts/openapi.json`
- `packages/api-contracts/typescript/src/types.ts`
- `packages/api-contracts/typescript/src/client.ts`
- `packages/api-contracts/typescript/src/index.ts`
- 重新生成 `packages/api-contracts/typescript/dist/*`，不要手工只改 dist。

### 9.4 Android Companion 修改

- `mobile/companion/app/build.gradle.kts`：加入 Room、WorkManager、serialization/HTTP client；把 `EDGE_API_PATH` 改为 Control API APK path；release 配置 API origin/pinning policy。
- `mobile/companion/app/src/main/AndroidManifest.xml`：声明 foreground service、boot completed receiver、network constraints 和必要的最小权限。
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/model/Models.kt`：替换 Edge binding/snapshot 为 cloud credential、command envelope、attempt/event/evidence 模型。
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/CompanionRepository.kt`：协调 enrollment、journal、sync 和 UI state，不直接用 refresh 拉 Edge snapshot。
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/EdgeClient.kt`：删除生产使用；新建下述 `ControlApiClient.kt`。
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/security/SecretStore.kt`：保存 credential metadata；私钥只在 Android Keystore，不保存长期明文 bearer。
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/device/LocalHealthCollector.kt`：增加 runner/capability/app identity 信息。
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/CompanionViewModel.kt`、`MainActivity.kt`：显示云端绑定、runner、当前 command、离线队列、取消/确认和上传状态。

Android 新增：

- `.../network/ControlApiClient.kt`
- `.../security/DeviceKeyManager.kt`
- `.../data/journal/CommandDatabase.kt`
- `.../data/journal/CommandDao.kt`
- `.../data/journal/CommandEntities.kt`
- `.../sync/CommandPollWorker.kt`
- `.../sync/HeartbeatWorker.kt`
- `.../sync/ResultUploadWorker.kt`
- `.../runner/CommandRunnerService.kt`
- `.../runner/LocalExecutorRegistry.kt`
- `.../runner/LeaseGuard.kt`
- `.../runner/CommitOnceGuard.kt`
- `.../runner/RebootRecovery.kt`
- `.../evidence/EvidenceCapture.kt`
- `.../evidence/EvidenceUploader.kt`

若本地自动化底座已有独立 SDK，应由 `LocalExecutorRegistry` 通过类型化接口调用；不得从 command payload 直接反射执行类名或脚本文本。

### 9.5 Web 修改

- `apps/web/src/api/control.ts`：补充真实 device/task/command/evidence client；生产 token 由 OIDC session 提供。
- `apps/web/src/types.ts`：加入 APK heartbeat、runner、delivery、attempt、evidence 状态。
- `apps/web/src/views/OperationsView.vue`：选择目标设备；显示 READY/DELIVERED/RECEIVED/RUNNING/UNKNOWN，而不只显示业务 task。
- `apps/web/src/views/DevicesView.vue`、`DashboardView.vue`：改为 Control API 数据。
- `apps/web/src/views/DeviceDetailView.vue`：显示 credential、last seen、capability、runner、lease、current command 和安全撤销。
- `apps/web/src/views/TasksView.vue`、`TaskDetailView.vue`：改为真实 operation/command 聚合和证据。
- `apps/web/src/views/StudioView.vue`：改为浏览器↔Control API↔APK 的云中继会话；不连接私网手机端口。
- `apps/web/src/api/client.ts` 与 `apps/web/src/data/mock.ts`：仅允许显式 demo/test import；生产构建路径不得 fallback。
- 可新增 `apps/web/src/api/events.ts`、`apps/web/src/stores/devices.ts`、`apps/web/src/stores/tasks.ts` 管理 SSE 重连和 cache。

### 9.6 测试新增/修改

后端新增：

- `tests/control_api_device_auth_test.py`
- `tests/control_api_apk_command_delivery_test.py`
- `tests/control_api_apk_lease_fencing_test.py`
- `tests/control_api_apk_event_idempotency_test.py`
- `tests/control_api_apk_cancel_recovery_test.py`
- `tests/control_api_apk_commit_unknown_test.py`
- `tests/control_api_apk_evidence_test.py`
- `tests/control_api_apk_websocket_test.py`（启用 WSS 时）

Android 新增 unit/instrumented tests，覆盖 Room journal、重复 envelope、旧 fence、进程/手机重启、离线事件补传、commit once、证据断点续传。现有 `tests/edge_companion_api_test.py` 可保留为 legacy/dev 验证，但不得成为生产直连验收标准。

Web 扩展：

- `apps/web/tests/operations-live.spec.ts`
- 新增 `apps/web/tests/devices-live.spec.ts`
- 新增 `apps/web/tests/task-delivery.spec.ts`
- 新增 `apps/web/tests/task-evidence.spec.ts`
- 新增构建测试，证明 production mode 不会导入 `api/client.ts` Mock。

## 10. 分阶段实施顺序

1. **云端设备身份与 heartbeat**：补 migration、device principal、enrollment/rotation/revocation、真实设备列表；先不下发任务。
2. **durable long-poll command delivery**：operation 生成 `apk_local` command，完成 claim/ack/start/renew/event/complete 和 fencing。
3. **APK 本地 executor 与 journal**：Room、WorkManager、foreground single runner、重启/离线恢复；先用无副作用测试 command 验证。
4. **证据与结果闭环**：预签名上传、hash/size 验证、task/item 聚合、commit intent/unknown/reconcile。
5. **Web 全量真实化**：Devices/Tasks/Details 去 Mock，展示 delivery/attempt/evidence/cancel/credential。
6. **可选 WSS 加速和 Studio 云中继**：保持 REST long-poll 为恢复通道。
7. **移除生产 Edge 依赖**：部署配置、runbook、监控和验收不再要求 Edge；ADB 明确标记为 development-only。

每阶段均应可独立回滚，先在测试 operation 上验证，再进入具备不可逆动作的业务。

## 11. 生产验收门槛

- 手机关闭 ADB、与 Web 不同局域网、无 Edge 进程时，仍能注册、心跳、领命令、独立执行和回传。
- Control API/网络中断 10 分钟后恢复，事件和证据无丢失、无重复业务动作。
- APK 进程被杀、手机重启后，不会把已开始 command 当作新 command；旧 fence 无法更新状态。
- 同一设备同时提交两个任务，只能有一个 runner 获得当前 lease。
- claim/ack/event/complete 重复发送均幂等；乱序和旧 attempt 被拒绝。
- commit 请求发出后立即断网，状态进入 `COMMIT_UNKNOWN`，系统不会自动再次 commit。
- 客户端伪造 object ref、hash、size 或跨 tenant evidence 时被拒绝。
- credential 撤销后不能换新 token；日志、审计、problem response 不含 token/code/私钥材料。
- 生产 Web 未配置 Control API 时明确失败，不显示 Mock 在线设备或虚假成功。
- ADB/scrcpy 可用于开发验收，但移除二者后生产闭环仍完整。

## 12. 不应实施的捷径

- 不把现有 Edge `/companion/v1` 原封不动搬到公网；它缺少 command attempt、fencing、journal 和证据闭环。
- 不让 APK 轮询整个 task 列表并自行挑任务；必须由服务端按 tenant/device/lease 分配 immutable command。
- 不用 WebSocket 内存队列作为唯一投递源。
- 不把 `operation_executor_urls` 指向手机地址，也不暴露手机私网 HTTP/ADB 端口。
- 不用 SharedPreferences 保存执行状态或 commit 标记。
- 不让 APK 上传任意 shell/script/selector 代码；执行能力来自版本化、签名、允许列表 executor。
- 不因“客户端说成功”就把 task 标为成功；结果和必需证据必须通过服务端策略验证。

完成上述改造后，系统才能真正满足“工作台直达 APK、手机 APK 本地独立执行与回传、生产不依赖 Edge/ADB”的最终生产模型。
