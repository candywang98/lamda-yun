# Q02 受控账本验收套件（W-H 线）

- TaskID: Q02-WH
- Baseline: 29f19dd0160c9f309ebf86c1cf3c118174a2fc9f（分支 agent/q02-ledger-acceptance）
- 套件路径: `tests/parallel_acceptance/q02/`
- 红线重申: 本套件只写测试与夹具，不执行真机场景；mock 测试不满足硬件验收（repo 不变量 6）。本套件只释放受控平台验收的前置检查，不把 P09/G3 整包标通过。

## 场景覆盖表（8 场景）

| # | 场景 | 类 | 用例（tests/parallel_acceptance/q02/…） | 结果 |
|---|------|----|----------------------------------------|------|
| 1 | intent 顺序（GATED 恰好一次、乱序拒/幂等） | A | `test_s01_intent_order.py`：s01a 恰好一次；s01b outcome 先于 intent 404；s01c 事件 gap/重放/篡改；s01d 非 RUNNING 409 + 冻结重放差异 409；s01e 伪造 actionKey/parameterHash 409；s01f RECONCILING 不再派发第二 runner | PASS |
| 2 | 读回确认（mock 服务端桩） | A | `test_s02_readback_confirmation.py` + `mock_platform.py`：s02a APPLIED 需独立读回证据（复用 before 409）；s02b badge delta(-1) 判定语义；s02c 读回不定 → UNKNOWN + complete/fail 双拒；s02d outcome 重放幂等/内容锁 | PASS |
| 3 | 丢 ACK / 重复上报幂等 | A | `test_s03_lost_ack_idempotency.py`：s03a 幂等键重放不建第二个任务；s03b 事件重放吸收、sequence 单调；s03c 丢 claim ACK → 同 task re-claim、attempt+1、fencing token 递增；s03d completion 重放吸收、resultType 混用 422、分叉 409 | PASS |
| 4 | 取消语义矩阵 | A | `test_s04_cancel_matrix.py`：9 态参数化（QUEUED/WAITING_MATERIALS/PREFLIGHT/PAUSE_REQUESTED/PAUSED_WAITING_USER → CANCELLED；RUNNING → CANCEL_REQUESTED；RECONCILING/SUCCEEDED/FAILED → 409）+ CANCELLED 幂等重放 + 取消后不可 claim | PASS |
| 5 | 旧租约 / fencing | A | `test_s05_stale_lease_fencing.py`：s05a resume 后 epoch+1，旧 lease 在 heartbeat/events/intent/complete 全通道 409；s05b re-claim 后旧 lease release 409；s05c 伪造 lease 不能写 outcome | PASS |
| 6 | 对账同步（三分支落库） | A | `test_s06_reconciliation_branches.py`：s06a KEEP_WAITING 落库不动账本；s06b NOT_SUBMITTED → FAILED + 账本 revision 1 + audit；s06c APPLIED 需 platformItemId → SUCCEEDED + result 落库；s06d APPLIED 报告与 NOT_SUBMITTED 矛盾 409；s06e UNKNOWN 不被 cancel/retry/resume/complete/claim 绕过；s06f 决策枚举校验；s06g badge 读回驱动的 APPLIED 对账 | PASS |
| 7 | 同 task 恢复 | A | `test_s07_same_task_recovery.py`：s07a pause→事件 ack→resume(pageVerified)→RESUME_CHECK→新 lease 续跑 RUNNING→complete，taskId/attempt/attemptId/参数/snapshot/pin/steps 全程不漂移（动态 controlEpoch 除外）；s07b 丢 lease re-claim 同 task attempt+1、pin/payload 冻结 | PASS |
| 8a | 设备重启（续跑或安全终止） | B | `test_s08_device_scenarios.py::test_b1_device_restart_task_resumes_or_terminates_safely` | SKIP（默认无设备） |
| 8b | 真机读回 | B | `test_s08_device_scenarios.py::test_b2_device_readback_after_gated_action` | SKIP（默认无设备） |

测试计数：A 类 42 通过；B 类 2 个默认 skip（marker `device_q02`）。xfail 清单：空（实现语义与任务卡全部一致，未发现需要总控裁决的偏差）。

## 运行方式（A 类，CI 可跑）

```bash
uv run python -m pytest -q tests/parallel_acceptance/q02/
```

worktree 环境注意（本次执行实测）：

```bash
uv sync --python 3.13.5 --extra dev   # worktree 需自建 venv；系统 pytest(3.10) 会收集失败
uv run python -m pytest ...           # 必须用 venv 内 pytest，PATH 上全局 pytest 是 3.10
```

## 同集成 SHA 守卫（防跨版本混跑）

`conftest.py::integration_sha`（session 级，fail-closed）：

1. 期望 SHA 来自 `tests/parallel_acceptance/q02/expected_integration_sha.txt`（当前 = 基线 29f19dd…），环境变量 `Q02_EXPECTED_SHA` 可覆盖；
2. 读 `git rev-parse HEAD`，断言期望 SHA 是 HEAD 的祖先（`git merge-base --is-ancestor`）——本分支提交后 HEAD 前移仍通过，不相关分支/未合入基线的混跑直接把整套件打成 error；
3. git 不可用同样 fail-closed。

负路径已实测：`Q02_EXPECTED_SHA=1111…` → 整套件 fail，消息提示在集成分支上用环境变量指定冻结集成 SHA。

## taskId / 哈希记录器

`conftest.py::ledger`（`ScenarioLedger`）每个用例把 taskId、actionKey、actionId、parameterHash、snapshotSha256、recipeSha256、状态/决策、新旧 lease、fencing/epoch 前后值写入：

```
<pytest tmp>/q02-ledger-<n>/
├── q02-ledger.jsonl                 # 全场景追加流（每行一个事件）
└── <test-name>-<rand8>.json         # 单用例明细（数组，含 integrationSha）
```

测试运行写 tmp（不污染仓库）；真机执行后由总控把该目录整体归档到：

```
artifacts/parallel/W5/Q02/<执行日期-serial>/
├── q02-ledger.jsonl
├── <test-name>-<rand8>.json
└── （总控补充）pytest 输出、设备侧 companion 日志、截图证据
```

## B 类（真机）执行手册 —— 仅总控、持 DEVICE:<serial> 锁

前置条件（缺一不可）：

1. 设备已 enroll（companion 安装、绑定、无障碍开启），control-api 部署可达；
2. 设备在售列表恰有 1 条可下架商品（本地可读回动作：xianyu delist，badge delta -1）；
3. 操作员身份 header 变量就绪（`Q02_TENANT/Q02_USER/Q02_ROLES`，默认与 A 类同）。

执行：

```bash
Q02_DEVICE_SERIAL=<serial> \
Q02_BASE_URL=https://<control-api> \
Q02_EXPECTED_SHA=<集成分支冻结SHA> \
Q02_POLL_SECONDS=300 \
uv run python -m pytest -q tests/parallel_acceptance/q02/test_s08_device_scenarios.py -rA
```

- b1 重启场景：用例创建 delist 任务并等到 RUNNING 后，由持锁操作员执行 `adb reboot`（或物理重启）；companion 自行回线后，断言同 attemptId 续跑或安全落终态，且 GATED 打击 ≤1 次；
- b2 读回场景：跑完受控下架后断言 badge 读回（delta -1）支撑结论；读回不定必须落 UNKNOWN+RECONCILING 交操作员，禁止盲 SUCCEEDED；
- 结束后把 tmp 的 q02-ledger 目录归档（见上节），并在 09_执行记录登记 taskId 与哈希。

## 实现要点对照（审阅入口）

- 账本幂等/顺序语义：`services/control-api/src/cloudctl_api/mobile_actions.py`（intent/outcome/replay）、`mobile_service.py::event`（sequence 单调+同内容幂等）；
- 取消/恢复/对账矩阵：`platform_tasks.py`（cancel/pause/ack_paused/resume/reconcile/mark_unknown）；
- fencing：`mobile_service.py::claim`（fencing_counter 递增）与 `platform_tasks.py::resume`（control_epoch 递增、旧 lease 删除）；
- UNKNOWN 机制背景：`artifacts/tasks/P09-unknown/xianyu-maintenance-20260916/unknown-root-cause-review.md`（IrreversibleActionGate：一次授权、恰好一次手势、无回退、操作员对账）。

## 门禁记录（本 worktree 实测）

- `uv run python -m pytest -q tests/parallel_acceptance/q02/` → 42 passed, 2 skipped；
- `uv run ruff check tests/parallel_acceptance/q02/` → All checks passed;
- 全量 `uv run python -m pytest -q` → 基线 702 passed / 1 skipped，合入本套件后 744 passed / 3 skipped（无新失败，新增 = 42 A 类 + 2 B 类 skip）。

## 2026-09-16 总控真机执行记录（b0644fb5 @ 131d3b4）

- A 类 42 用例：CI 全绿（合并前复跑确认）
- B 类首跑：2 passed 但 **B1 为空通过**（settle 窗口内无人执行重启，断言平凡成立；设备 uptime 2天12小时未变）；**B2 实走安全失败分支**（任务 5d03641e FAILED，零副作用，但读回成功路径未被走到）
- ⚠️ 风险发现：DELIST_STEPS 用 cardIndex:0 作用于在卖 tab 第一张卡（无标题定向）——对真实账号执行会命中任意真实在售商品。总控已暂停 B 类复跑，待用户裁决目标对象后再执行（候选：Q03 发布后的测试商品 / 用户指定的可牺牲旧书 / 改 titleContains 定位）
