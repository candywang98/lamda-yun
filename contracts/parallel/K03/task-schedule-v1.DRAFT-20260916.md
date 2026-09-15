# task-schedule/v1 契约（草案）— DRAFT 20260916

状态：**DRAFT（未冻结）**。起草人：W0 总控。基线 `5c4d100`。消费者：A04（任务事实/冻结快照/调度服务）、A09（operation 目录逐动作登记）、D02（Temporal 桥接）。冻结需用户拍板 §7 裁决项并登记 01 合同状态。

## 1. 范围与边界

- 冻结**现有事实**而非新设计：CommandV1 协议（command-v1.schema.json）、MobileTask 双状态机、事件 schema、TaskSchedule（ONCE/RECURRING）、取消/暂停语义。
- 本切片新增冻结：operationId 的持久化与追踪、fire 触发契约（Temporal 桥接锚点）。
- 不做：rrule 扩展为 RFC5545 全集、后台自动触发循环的实现（D02 用 Temporal 走 §5 fire 契约）。

## 2. 身份链（钉死）

`operationId`（field-map.json 目录身份）—`PRODUCTION_ALIASES`→ `commandType` → `MobileTaskRow(id, command_type)` → `taskId`（CommandV1）→ 事件（`Unique(task_id, sequence)`）→ `batch_id`。
⚠ 现状：mint_operation_command 产出 operationId 但**不落库**（MobileTaskRow 只存 command_type，command_factory.py:143 / db.py:738）→ 见裁决项 D1。

## 3. 状态机（钉死）

- **权威分工**：操作员视角以 `business_state` 为准；runner 视角以 `status` 为准（QUEUED/CLAIMED/RUNNING/SUCCEEDED/FAILED，每设备仅一条 CLAIMED/RUNNING）。
- `business_state` 全集沿用 platform_tasks.py:37-50；终态 = SUCCEEDED/FAILED/CANCELLED/EXPIRED。
- **拼写钉死双 L：`CANCELLED`**；mobile_service.py:192 的单 L 兼容查询仅作遗留容错，新代码/新事件禁止单 L（裁决项 D4：何时删除容错）。
- 旧路径 `steps` JSON + `legacyStepsEnabled`：**冻结为弃用**，新 commandType 一律 CommandV1 路径；claim 写 steps 元数据仅为兼容（mobile_actions.py:142）。

## 4. 取消/暂停语义（钉死，A04 验收口径）

- **暂停不是取消**：pause → `PAUSE_REQUESTED` → Companion `:ack-paused`（校验 lease）→ `PAUSED_WAITING_USER`（若已写 commitIntent 则转 `RECONCILING`）；resume 要求 `pageVerified=true` 且绑定版本未变，重建 lease/controlEpoch 后 `RESUME_CHECK`。
- cancel：终态幂等返回；RECONCILING→409（须先对账）；未启动（QUEUED/WAITING_MATERIALS/PREFLIGHT/PAUSE_*）→ 立即 CANCELLED；RUNNING→`CANCEL_REQUESTED` 延迟到安全点。
- fencing：`control_epoch` + `device_lease.fencing_token` 单调递增，resume 同时递增两者（platform_tasks.py:524）。

## 5. 调度与触发（含 Temporal 桥接锚点）

- 现有形状沿用：kind ONCE|RECURRING；rrule **受限子集**（仅 FREQ=HOURLY/DAILY/WEEKLY + INTERVAL，DST 用 `#fold`）；missPolicy QUEUE_ONE|SKIP；startDeadlineMinutes 1..10080 默认 30；过期：ONCE 超 deadline→EXPIRED 不补，RECURRING 落后→SKIPPED。
- **fire 契约（冻结，D02 桥接点）**：触发统一走 `POST /api/v1/task-schedules/{id}:fire`；幂等键 = 现有 `sha256(schedule_id:utc_time:device_id)[:64]`（TaskScheduleFireRow Unique 兜底）；重复触发**不重复建任务**（A04 验收）。**谁来调 fire**：v1 阶段=操作员手动；D02 交付后=Temporal Workflow 定时调 fire（同一幂等键语义），生产 Worker 不接编码智能体。
- 参数冻结：fire 时从 schedule 模板铸命令，记录 `template_revision`；创建后编辑模板不影响已触发任务（快照不漂移）。

## 6. 幂等键命名空间（钉死）

- 任务创建：`Unique(tenant_id, idempotency_key)`（操作员侧 Idempotency-Key）。
- 调度触发：fire 键（§5）。
- 重试：`retry:{task_id}:{attempt+1}:{reason[:24]}`。
- 三者前缀不重叠，禁止复用。

## 7. 裁决项（冻结前需用户拍板）

| # | 事项 | 草案建议 | 备选 |
|---|---|---|---|
| D1 | operationId 是否落库 | MobileTaskRow 加 `operation_id` 列（一次迁移），A09 逐动作可追踪、审计可反查目录 | 不落库，仅从 commandType+parameters 反推（A09 验收「逐动作登记」会缺实证） |
| D2 | 自动触发归属 | v1 手动 fire + D02 Temporal 桥接（推荐，仓库已有 temporalio 但只接了 publish） | control-api 内自建轮询循环（新增常驻组件，偏离现有架构） |
| D3 | rrule 范围 | 维持受限子集并写明（不承诺 RFC5545） | 扩展 MONTHLY/BYDAY 等（需求未到，先不扩） |
| D4 | 单 L CANCELED 容错 | 保留查询容错，契约钉死双 L，下一切片清理 | 立即删除容错（需先全库扫描确认无单 L 数据） |

## 8. 正/负 fixture（见 fixtures/ 目录）

- `k03-positive-schedule-once.json`：ONCE + fire 幂等（同 fire 键二连发 → 一条任务 + Idempotency-Replayed）。
- `k03-positive-pause-resume.json`：pause→ack→resume 全链事件序列（business_state 迁移序列断言）。
- `k03-negative-cancel-reconciling.json`：RECONCILING 下 cancel → 409 CONFLICT。
- `k03-negative-rrule-monthly.json`：FREQ=MONTHLY → 422 VALIDATION_ERROR（受限子集）。

## 9. 消费者验证命令

- A04：`uv run pytest -q tests/integration/test_task_schedules.py tests/integration/test_platform_tasks.py`
- A09：operation_catalog 相关测试（实现线交付时定）
- D02：`services/temporal-worker` 独立 namespace fixture 测试（定时触发/取消/重复幂等三件套，任务卡口径）。
