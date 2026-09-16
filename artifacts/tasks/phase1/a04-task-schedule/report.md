# A04-WD 任务事实/冻结快照/调度服务 — 执行报告

- TaskID: A04-WD（K03 契约 A04 范围）
- Baseline SHA: `ce074df`
- 分支: `agent/a04-task-schedule`（worktree `p14-worktrees/a04-schedule`）
- 契约版本: `task-schedule/v1@20260916.1`（FROZEN，`contracts/parallel/K03/task-schedule-v1.md` + fixtures 4 个，未改动）
- 独占锁: DB_MIGRATION（本线为该迁移唯一 owner，迁移 `20260916_0022`）
- 时间: 2026-09-16（Asia/Shanghai）

## ChangedFiles

| 文件 | 变更 |
|---|---|
| `services/control-api/migrations/versions/20260916_0022_add_mobile_task_operation_id.py` | 新迁移：mobile_task 加 operation_id（独立提交） |
| `services/control-api/src/cloudctl_api/db.py` | MobileTaskRow 加 `operation_id String(64) nullable + index` |
| `services/control-api/src/cloudctl_api/platform_tasks.py` | D1 落库链路；templateRevision 冻结；retry 保留身份；resume 缺 pageVerified 改 422；operationId 进视图 |
| `services/control-api/src/cloudctl_api/schedules.py` | rrule 校验带 `fields.rrule`；fire 返回 (views, created)；fire 铸命令带 templateRevision |
| `services/control-api/src/cloudctl_api/schedule_routes.py` | fire 首次 201 / 重放 200 + `Idempotency-Replayed` 头 + `taskIds` |
| `tests/integration/test_task_schedules.py` | 场景①④ + 参数冻结测试；现有 fire 断言 200→201 |
| `tests/integration/test_platform_tasks.py` | 场景②③ + operationId 可见断言；resume 缺 pageVerified 断言 409→422 |
| `tests/integration/test_control_api_migrations.py` | mobile_task 列集合加 operation_id；新增 20260916_0022 up/down 对称性测试 |
| `packages/api-contracts/openapi.json` | 用 `scripts/export_openapi.py` 机械再生成（+13 行 templateRevision schema，沿 712fb5f 先例；controller 集成时可统一再生成一次） |

## 一、契约符合性核对表

| K03 条款 | 状态 | 证据 |
|---|---|---|
| §2/D1 MobileTaskRow 加 `operation_id`（一次迁移，DB_MIGRATION 锁） | ✅ | 迁移 `20260916_0022`，`String(64)`（对齐 field-map operationId 形态 `xy-tasks-01`/`red-tasks-01`/`device-probe` 与 API 层 64 上限），nullable + `ix_mobile_task_operation_id` |
| §2 身份链 operationId→commandType→MobileTaskRow→taskId→事件→batch_id | ✅ | mint（已有）→ `create()` 写 `row.operation_id` + `command_payload["operationId"]` 进 snapshotSha256；retry 传递 `source.operation_id`，不重新推导 |
| §2 操作员任务查询与事件反查可见 operationId | ✅ | `_business_view` 加 `operationId`（list/get 共用）；GET `{id}` 返回体 + events 同体可见；`test_operation_id_mints_command_v1...` 断言 list/detail/commandPayload 三处 |
| §3 business_state 全集 / 终态 / 双 L CANCELLED | ✅ 未动 | `BUSINESS_STATES`/`TERMINAL_BUSINESS` 原样；`_business_view` 单 L 容错保留（D4 清理归下一切片）；新代码无双 L |
| §4 暂停不是取消：pause→PAUSE_REQUESTED→:ack-paused(lease)→PAUSED_WAITING_USER（commitIntent→RECONCILING） | ✅ | 场景②测试逐步断言；wrong lease 409 |
| §4 resume 要求 pageVerified=true 且绑定版本未变，重建 lease/controlEpoch → RESUME_CHECK | ✅（1 处修正） | 缺 pageVerified 原实现 409 → **修正为 422 VALIDATION_ERROR**（fixture 钉死 422）；绑定版本校验、epoch/fencing 同时+1、60s 新 lease 由测试断言 |
| §4 cancel：终态幂等；RECONCILING→409；未启动→立即 CANCELLED；RUNNING→CANCEL_REQUESTED | ✅ | 场景③测试四分支全覆盖（RUNNING 经 claim+heartbeat 真实置位） |
| §5 rrule 受限子集，MONTHLY 等 → 422 带 fields | ✅（1 处修正） | 原 `next_occurrences` 抛错无 `fields` → 修正为 `fields={"rrule": "仅支持 FREQ=HOURLY/DAILY/WEEKLY + INTERVAL"}`；另修复 INTERVAL 非整数原会 500 → 422 |
| §5 missPolicy / startDeadlineMinutes 1..10080 默认 30 / ONCE 超 deadline EXPIRED 不补 / RECURRING 落后 SKIPPED | ✅ 未动 | schedules.py 原逻辑保留，未改 |
| §5 fire 契约：POST `:fire`，幂等键 sha256(schedule_id:utc_time:device_id)[:64]，Unique 兜底，重复不建任务 | ✅ | 幂等键算法未改；场景①：同 body 二连发仅 1 条任务、fire 记录 1 条 |
| §5 首次 fire 201 / 重放 200 可辨 | ✅（1 处修正） | 原实现恒 200 → 修正为首次 201（created_any）+ 重放 200 + `Idempotency-Replayed` 头 + 响应 `taskIds`；现有测试 2 处断言同步 200→201 |
| §5 参数冻结：fire 铸命令记录 template_revision；编辑模板不影响已触发任务 | ✅（补强） | fire 传 `templateRevision` → 落 `command_payload.templateRevision`（进 snapshotSha256）；`test_k03_fired_task_parameters_frozen_against_template_edits`：fire 后改模板参数+revision=2，旧任务 parameters/templateRevision/snapshotSha256 不变，新任务用新值 |
| §6 幂等键命名空间三分不重叠 | ✅ 未动 | 任务创建 Unique(tenant_id,idempotency_key)、fire hex 键、`retry:{task_id}:{attempt+1}:{reason[:24]}` 原样 |
| D2/D3 裁决 | ✅ 遵守 | 未实现任何 Temporal worker/轮询循环；rrule 维持受限子集 |

## 二、迁移 up/down 证据

命令（测试库 sqlite+aiosqlite，工作目录 `services/control-api`）：

```bash
export CLOUDCTL_DATABASE_URL="sqlite+aiosqlite:////tmp/a04_mig_test.db"
uv run --extra dev alembic upgrade head
# → Running upgrade 20260915_0021 -> 20260916_0022, mobile_task.operation_id ...
# alembic current → 20260916_0022 (head)
# PRAGMA table_info(mobile_task) → 21|operation_id|VARCHAR(64)|0||0
# sqlite_master → ix_mobile_task_operation_id 存在

uv run --extra dev alembic downgrade 20260915_0021
# → Running downgrade 20260916_0022 -> 20260915_0021
# alembic current → 20260915_0021；PRAGMA 无 operation_id（grep 计数 0）

uv run --extra dev alembic upgrade head   # 再升回，20260916_0022 (head)
```

pytest 侧：`tests/integration/test_control_api_migrations.py::test_mobile_task_operation_id_updown_is_symmetric`（legacy 行保留 NULL 不回填、行数不丢、索引随列增删）+ `test_upgrade_and_downgrade_preserve_legacy_operation_rows`（mobile_task 精确列集合已含 operation_id，head↔base 全链 down/up 仍通过）。

## 三、测试结果

| 门禁 | 基线（ce074df） | 之后 | 判定 |
|---|---|---|---|
| 聚焦 `tests/integration/test_task_schedules.py tests/integration/test_platform_tasks.py` | 26 passed | **31 passed**（+5：场景①④、参数冻结、场景②③） | 绿 |
| 全量 `uv run --extra dev python -m pytest -q` | 669 passed / 1 failed / 1 skipped* | **676 passed / 0 failed / 1 skipped** | 绿，无新失败 |

\* 基线说明：全量基线跑动时工作树已含本切片部分改动，唯一失败是 `test_control_api_migrations.py` 的 mobile_task 精确列集合断言（由本切片新增列直接引起，随后已更新该断言）。干净树上另跑过聚焦基线 26 passed。最终全量含新增测试 676 全绿。

被更新的既有断言（均为契约要求的语义修正，非削弱）：
- `test_task_schedules.py`：fire 首次 200→201（2 处，fixture ① 钉死 201/200 区分）
- `test_platform_tasks.py`：resume 缺 pageVerified 409→422（fixture ② 钉死 422）

## 四、契约疑议记录（未改契约，提请 W0/用户裁决）

1. **fixture ①/④ 的 commandType `xianyu.polish.steps.v1`** 不在冻结 CommandType 4 成员集（`command_v1.py` Literal：xianyu.publish_listing/collect_orders/xiaohongshu.publish_note/device.probe_capabilities）内，按字面创建会因 commandType 422 而非目标断言。测试以 `device.probe_capabilities.v1`/`xianyu.collect_orders.v1` 等价承载用例意图。
2. **fixture ② "事件序列 business_state 迁移完整可断言"**：若解读为"操作员状态转换（pause/:ack-paused/:resume/:cancel）也必须写 MobileTaskEventRow 事件"，与两条既有冻结事实冲突：(a) P09 hardening 测试明确断言 mark-unknown 不消费 companion sequence（事件 seq 从 companion 计数连续）；(b) companion 事件协议要求 sequence == last_sequence+1，操作员事件占用 Unique(task_id, sequence) 空间会使 companion 后续上报 gap 409。曾实现操作员写事件，全量回归 2 项红（P09），验证冲突后已回滚；现按既有事件通道落地：操作员转换以状态视图断言、companion 上报（PAUSED_WAITING_USER seq1）进事件流断言。若契约本意是操作员事件入流，需要 D02/companion 侧同步 sequence 协议后再启用。
3. **fixture ③ detail 文案**「须先完成对账裁决」为中文意译；实现保持英文 `uncertain result must be reconciled before cancellation`，测试断言 409 + code=CONFLICT + reconcile 关键字，不逐字断言。
4. **fire 响应形状**：fixture 期望 `taskIds`；实现为在既有 `{items, count}` 上新增 `taskIds`（超集，不破坏既有消费者），并以 201/200 + `Idempotency-Replayed` 头区分重放。`packages/api-contracts/openapi.json` 已用仓库脚本 `scripts/export_openapi.py` 机械再生成（先例：712fb5f 等切片均随片更新）；按 AGENTS.md 集成流程，controller 集成后仍会统一再生成一次，届时可复核。

## 五、未决项

- 契约疑议 2 的事件归属裁决（影响 D02 桥接时是否给操作员转换补事件通道）。
- 单 L `CANCELED` 历史数据清理按 D4 归下一切片，本切片未动。
- `GET /api/v1/mobile/tasks/{id}`（runner 视图）未加 operationId 字段（任务书只要求 platform-tasks 返回体）；如 runner 侧需要可后续补。
