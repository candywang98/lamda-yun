# task-schedule/v1 契约 — FROZEN 20260916.1

状态：**FROZEN（已冻结）**，版本 `task-schedule/v1@20260916.1`。起草人：W0 总控；裁决人：用户（2026-09-16，7 项全按建议）。基线 `5c4d100`。消费者：A04（任务事实/冻结快照/调度服务）、A09（operation 目录逐动作登记）、D02（Temporal 桥接）。

## 1. 范围与边界

- 冻结**现有事实**：CommandV1 协议、MobileTask 双状态机、事件 schema、TaskSchedule（ONCE/RECURRING）、取消/暂停语义。
- 新增冻结：operationId 持久化与追踪（裁决 D1）、fire 触发契约（Temporal 桥接锚点，裁决 D2）。
- 不做（已裁决 D3）：rrule 扩展为 RFC5545 全集；不建 control-api 常驻轮询循环（已裁决 D2）。

## 2. 身份链（冻结）

`operationId`（field-map.json 目录身份）—`PRODUCTION_ALIASES`→ `commandType` → `MobileTaskRow(id, command_type, operation_id)` → `taskId`（CommandV1）→ 事件（`Unique(task_id, sequence)`）→ `batch_id`。
**已裁决 D1：MobileTaskRow 新增 `operation_id` 列（一次迁移，W1 持 DB_MIGRATION 锁）**；A09 逐动作追踪与审计反查以此为实证。

## 3. 状态机（冻结）

- 权威分工：操作员视角 `business_state` 为准；runner 视角 `status` 为准（QUEUED/CLAIMED/RUNNING/SUCCEEDED/FAILED，每设备仅一条 CLAIMED/RUNNING）。
- `business_state` 全集沿用 platform_tasks.py:37-50；终态 = SUCCEEDED/FAILED/CANCELLED/EXPIRED。
- **拼写钉死双 L：`CANCELLED`**（已裁决 D4：单 L 查询容错保留，新代码禁止单 L，清理归下一切片）。
- 旧路径 `steps` JSON + `legacyStepsEnabled`：冻结为弃用；新 commandType 一律 CommandV1 路径。

## 4. 取消/暂停语义（冻结，A04 验收口径）

- **暂停不是取消**：pause → `PAUSE_REQUESTED` → Companion `:ack-paused`（校验 lease）→ `PAUSED_WAITING_USER`（已写 commitIntent 则转 `RECONCILING`）；resume 要求 `pageVerified=true` 且绑定版本未变，重建 lease/controlEpoch 后 `RESUME_CHECK`。
- cancel：终态幂等返回；RECONCILING→409（先对账）；未启动→立即 CANCELLED；RUNNING→`CANCEL_REQUESTED` 延迟到安全点。
- fencing：`control_epoch` + `device_lease.fencing_token` 单调递增，resume 同时递增两者。

## 5. 调度与触发（冻结，含 Temporal 桥接锚点）

- 形状沿用：kind ONCE|RECURRING；rrule 受限子集（FREQ=HOURLY/DAILY/WEEKLY + INTERVAL，DST `#fold`）——**不承诺 RFC5545**（已裁决 D3）；missPolicy QUEUE_ONE|SKIP；startDeadlineMinutes 1..10080 默认 30；ONCE 超 deadline→EXPIRED 不补；RECURRING 落后→SKIPPED。
- **fire 契约**：触发统一走 `POST /api/v1/task-schedules/{id}:fire`；幂等键 = `sha256(schedule_id:utc_time:device_id)[:64]`（TaskScheduleFireRow Unique 兜底）；重复触发不重复建任务。
- **触发归属（已裁决 D2）**：v1 = 操作员手动 fire；D02 交付后 = Temporal Workflow 定时调 fire（同一幂等键语义），生产 Worker 不接编码智能体。
- 参数冻结：fire 时从模板铸命令并记录 `template_revision`；创建后编辑模板不影响已触发任务。

## 6. 幂等键命名空间（冻结）

任务创建 `Unique(tenant_id, idempotency_key)`；调度触发 fire 键；重试 `retry:{task_id}:{attempt+1}:{reason[:24]}`。三者前缀不重叠，禁止复用。

## 7. 裁决记录（用户 2026-09-16 拍板，全按建议）

| # | 事项 | 裁决 |
|---|---|---|
| D1 | operationId 落库 | ✅ MobileTaskRow 加 `operation_id` 列（一次迁移） |
| D2 | 自动触发归属 | ✅ v1 手动 fire + D02 Temporal 桥接 |
| D3 | rrule 范围 | ✅ 维持受限子集 |
| D4 | 单 L CANCELED | ✅ 钉死双 L，容错下一切片清理 |

## 8. 正/负 fixture：`contracts/parallel/K03/fixtures/`（4 个，随本契约冻结）

## 9. 消费者验证命令

- A04：`uv run pytest -q tests/integration/test_task_schedules.py tests/integration/test_platform_tasks.py`
- A09：operation_catalog 测试（实现线交付时定）
- D02：`services/temporal-worker` 独立 namespace fixture（定时触发/取消/重复幂等）
