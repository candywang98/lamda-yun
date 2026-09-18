# Runbook：多机灰度与回退演练（U12）

适用范围：fleet-first-20260916.1 计划 U12「多机灰度与回退演练」。本文是 U10（APK 发布 API）、
U11（设备侧下载/安装/回执）与 WIRE2（:report-installed 回执闭环）合入后的**验收演练层**操作手册，
与集成测试 `tests/integration/test_fleet_rollout.py` 一一对应：每个章节标注对应的测试函数，
测试即演练的自动化形态，本手册是同一演练的人工/操作台形态。

- 建立日期：2026-09-17（U12）
- 演练载体：`tests/integration/test_fleet_rollout.py`（memory-sqlite + 隔离 PostgreSQL 双跑）
- 契约基线：apk-release/v1@20260917.1（FROZEN）、recipe 版本固定（P14 已验收）
- 纪律：当前环失败（安装失败/回执 FAILED/USER_DECLINED）→ **立即停止向后续环扩散**，
  按第 4 节回退；禁止带病推进全量环。

---

## 1. 前置检查

| # | 检查项 | 命令 / 判据 | 失败处置 |
|---|---|---|---|
| P1 | 发布栈基线在位（U10+WIRE2 合入） | `git log --oneline -1` 在含 `:report-installed` 的合并之后 | 先补基线，不开演练 |
| P2 | 集成测试环境可用 | 见第 6 节验证命令，退出码 0 | 修环境，不改测试迁就 |
| P3 | 制品已过准入（CLEAN + 签名验证通过） | `GET /api/v1/apk-artifacts/{id}` 的 `scan_status=CLEAN`、`policy_decision.decision=ACCEPT` | 错签名/不洁净制品直接 422，不进入发布 |
| P4 | 设备环标签就绪 | 设备 `labels` 含 `ring:canary` / `ring:early`；无标签设备只进 `all` 环 | 补标签，不要放宽 ring 校验 |
| P5 | 忙设备清单为空 | 目标设备无 RUNNING / PAUSED_WAITING_USER / RECONCILING / CLAIMED 任务，否则 assign 409 `APK_DEVICE_BUSY` | 等任务终态或换设备；**不允许强占** |
| P6 | 回滚包已备好 | 更高 versionCode 的恢复包（旧逻辑+兼容数据）制品已注册准入 | 未备回滚包不得开环（本 runbook 第 4 节依赖它） |

注意（契约事实，防误操作）：

- **制品不可覆盖**：`(tenant, sha256)` 唯一、`(tenant, artifact)` 一 release；同制品重发布 409
  `APK_RELEASE_EXISTS`。改门控（ring/能力/schema）必须走**新制品+新 release**。
- **回退用更高 versionCode**：低 versionCode 降级不可承诺（U11 验收结论），恢复包 = 旧逻辑 +
  更高 versionCode + 兼容数据。
- `requiresUserConfirmation` 是需求声明，不是静默安装承诺；SDK 标志不能覆盖。

## 2. 演练模型

```
ring:canary (1 台)  ──100% INSTALLED──▶  ring:early (小批)  ──100% INSTALLED──▶  ring:all (其余)
        │                                       │
        └─ 任一失败/拒绝 ──▶ 停止扩散（第 4 节）─┘
```

- 推进门（每环）：该环所有 `apk_release_target` 达到 `INSTALLED`（以设备回执为准，
  `outcome=INSTALLED` 且 `signatureMatched != false`），才允许下一环 assign。
- 停止门：当前环出现 FAILED / USER_DECLINED / INTERRUPTED / 签名不匹配回执，或 assign 被
  4xx/409 拒绝 → 冻结后续环（不 assign、不发布新环制品），进入第 4 节。
- 版本记录双轨：每次演练同时记录 **APK versionCode** 与 **Recipe revision（versionId）**，
  以及文件 sha256、安装回执全文、具体设备 ID（第 6 节证据清单）。

## 3. 分环顺序与每步验证（正常路径）

> 自动化形态：`test_ring_drill_canary_early_all_records_full_evidence`（canary→early→all 全程 +
> 审计齐全断言）；人工门场景：`test_manual_install_gate_blocks_until_user_confirmation`。

每一步的 API 动作与验证判据：

1. **发布 canary 波**：`POST /api/v1/apk-releases`（ring=canary）→ `POST :assign` 目标 canary 设备。
   验证：200，target `status=OFFERED`；`GET /companion/v2/apk/candidates`（设备侧）可见候选且
   `sha256`/`signatureDigest`/`requiresUserConfirmation` 与制品一致。
2. **设备侧下载校验**：`POST /companion/v2/apk/candidates/{id}:report-downloaded` 携带实测哈希。
   验证：哈希不符 422 `APK_DOWNLOAD_HASH_MISMATCH` 且候选留在 OFFERED；相符则 `DOWNLOADED`。
3. **安装与回执**：设备安装后 `POST .../{id}:report-installed`。验证：`INSTALLED` 回执把 target
   推进到 `INSTALLED` 且候选从设备列表消失；失败回执只落 `apk.release.install_receipt` 审计，
   target 不推进（候选保持可重试）。
4. **canary 推进门**：canary 环全部 INSTALLED → 才发布 early 波（ring=early）重复 1–3。
5. **全量收口**：early 环全部 INSTALLED → 发布 all 波（ring=all）覆盖其余设备；已升级设备
   接受更高 versionCode，各设备版本独立记录。
6. **人工安装门**（`requiresUserConfirmation=true` 的候选）：设备未确认 → 不下载不推进（候选
   保持 OFFERED）；用户拒绝 → USER_DECLINED 回执落审计、target 仍 OFFERED（不推进、不清理）；
   用户确认后同一候选正常走下载→安装→INSTALLED。

单步验证命令（对应步骤 1–6 全路径）：

```bash
cd <worktree> && \
PYTHONPATH=<worktree>/services/control-api/src \
<主仓>/.venv/bin/python -m pytest tests/integration/test_fleet_rollout.py \
  -k "ring_drill_canary_early_all or manual_install_gate" -q
```

## 4. 失败时的停止与回退动作

> 自动化形态：`test_canary_failure_stops_ring_expansion_and_rollback_restores`（安装失败→停止→
> retire→更高 versionCode 回滚包恢复）；`test_mid_rollout_retire_and_schema_containment`
> （证书撤回 retire + 数据 schema 不兼容 containment）。

停止动作（按序）：

1. **冻结扩散**：不再对后续环执行任何 `:assign`。ring 校验本身会挡跨环（422
   `APK_RING_MISMATCH`），同设备+包名的在途 OFFERED 候选也会挡新候选（409 `APK_CANDIDATE_EXISTS`），
   但不要依赖报错兜底——操作上直接停。
2. **撤回坏波**：`POST /api/v1/apk-releases/{id}:retire`（填 reason）。retire 后新 assign 一律
   409 `APK_RELEASE_RETIRED`；**已持有候选的设备 pin 不受影响**（见第 5 节）。
3. **证据固定**：导出失败回执审计（第 6 节）后再做后续动作，不要先清理后取证。

回退动作：

1. **发恢复包**：注册并发布**更高 versionCode** 的恢复制品（旧逻辑+兼容数据），assign 到受影响
   设备。设备上失败候选处于 DOWNLOADED（非 OFFERED）时不会被单飞约束挡住，可直接收到恢复候选。
2. **验证恢复**：设备走下载哈希校验 → INSTALLED 回执 → target INSTALLED；随后设备能正常领任务
   （claim 返回的 recipe pin 仍可解析）即旧业务能力恢复。
3. **遗留候选**：坏波的候选按设计保持可重试（retire 后仍显示 `releaseStatus=RETIRED`、
   `status=DOWNLOADED/OFFERED`）。设备侧协调器按最新候选优先；服务端无候选撤销端点（见第 8 节
   接缝），演练中如实记录、不手工清库。
4. **数据 schema 淘汰**：新波 `dataSchema.minCompatible` 高于设备上报版本时，该设备 422
   `APK_SCHEMA_INCOMPATIBLE`、保持旧版继续跑业务；未上报 schema 版本的设备保持可升级。

单步验证命令：

```bash
cd <worktree> && \
PYTHONPATH=<worktree>/services/control-api/src \
<主仓>/.venv/bin/python -m pytest tests/integration/test_fleet_rollout.py \
  -k "canary_failure_stops or mid_rollout_retire" -q
```

## 5. 双版本共存与持有制品的 pin 保护

> 自动化形态：`test_dual_version_coexistence_routes_by_capability_and_version`（两代 APK 同时
> ACTIVE、能力/版本路由、新旧设备任务并行）；`test_held_artifacts_of_paused_and_unknown_tasks_
> survive_withdrawal`（PAUSED/UNKNOWN 任务的 apk target pin + recipe version pin 在 retire/revoke
> 下不被清理）；`test_recipe_version_pin_read_regression`（P14 受影响路径回归：版本固定读取）。

- **双版本在线**：gen1（ring=all）与 gen2（ring=canary）可同时 ACTIVE；升级过的设备对旧版本包
  422 `APK_VERSION_DOWNGRADE`，能力不足设备 422 `APK_CAPABILITY_INSUFFICIENT` 且**从不收到候选**。
- **任务路由**：新旧两代设备并行领同一 probe 任务，claim 的 recipe pin 版本一致。
- **pin 保护**：PAUSED（RUNNING+PAUSED_WAITING_USER）与 UNKNOWN 状态任务持有的
  `apk_release_target`（OFFERED/DOWNLOADED）和 `mobile_task.recipe_pin` 在 release retire、
  recipe revoke 之后全部保持可解析（`GET /companion/v2/recipes/{versionId}` 200 +
  `X-Content-SHA256`）；任务到终态后 pin 才自然释放。**撤回 ≠ 清理持有**。
- **P14 回归边界**：只回归版本固定读取（claim pin、租约重试仍读 pin、revoke 后 pin 可读、终态
  释放）；完整 Recipe 生命周期验收不在此重做。

单步验证命令：

```bash
cd <worktree> && \
PYTHONPATH=<worktree>/services/control-api/src \
<主仓>/.venv/bin/python -m pytest tests/integration/test_fleet_rollout.py \
  -k "dual_version or held_artifacts or pin_read_regression" -q
```

## 6. 证据留存清单（审计行齐全判据）

每次演练必须能回答：**哪台设备、装了哪个 APK versionCode、按哪个 Recipe revision 执行、
文件哈希多少、安装回执说了什么**。审计行（`audit_event` 表）齐全 = 下列行全部存在且字段齐备：

| 审计 action | 记录内容 | 必查字段 |
|---|---|---|
| `apk.release.published` | 每波发布（versionCode+sha256 在 after 视图，行内存 `after_hash`） | `resource_id`=releaseId、`after_hash` |
| `apk.release.assigned` | 每波 assign | `metadata.device_ids`（具体设备 ID 清单） |
| `apk.release.downloaded` | 每次下载校验 | `device_id`、`after_hash`（对 `{releaseId, sha256}` 的规范化哈希，可复算验证文件哈希落档） |
| `apk.release.installed` | 每次成功安装 | `device_id`、`metadata.receipt`（attemptedVersionCode/installedVersionCode/signatureMatched 全文） |
| `apk.release.install_receipt` | 失败/拒绝/中断回执 | `device_id`、`metadata.receipt.outcome/message` |
| `apk.release.retired` | 撤回 | `metadata.reason` |
| `recipe.version.published` / `revoked` | Recipe revision 变更 | `metadata.version_id`、`metadata.device_ids` |
| `recipe.task.pinned` | 每次任务固定版本 | `device_id`、`metadata.recipe.versionId` |

留存物：上述审计行导出（`docs/runbooks/audit-export.md` 的流程）+ 演练测试输出（命令与退出码）+
受影响设备清单（deviceId、前后 versionCode、环名）。禁止以改库代替证据。

全量验证命令（本 runbook 全部场景 + 既有回归不破坏）：

```bash
cd <worktree> && \
PYTHONPATH=<worktree>/services/control-api/src \
<主仓>/.venv/bin/python -m pytest tests/integration/test_fleet_rollout.py -q
# 2026-09-17 实测：14 passed（sqlite+postgres 双跑），退出码 0

cd <worktree> && \
PYTHONPATH=<worktree>/services/control-api/src \
<主仓>/.venv/bin/python -m pytest -q
# 2026-09-17 实测：见 U12 交付记录（全量绿）
```

## 7. 场景 ↔ 测试对应表

| 场景 | 测试函数 | 本手册章节 |
|---|---|---|
| canary→early→all 正常推进 + 证据齐全 | `test_ring_drill_canary_early_all_records_full_evidence` | §3、§6 |
| canary 失败停止扩散 + 回滚包恢复 | `test_canary_failure_stops_ring_expansion_and_rollback_restores` | §4 |
| 双版本共存 + 能力/版本路由 | `test_dual_version_coexistence_routes_by_capability_and_version` | §5 |
| 证书/制品撤回 + 数据 schema 淘汰 | `test_mid_rollout_retire_and_schema_containment` | §4 |
| 人工安装门 | `test_manual_install_gate_blocks_until_user_confirmation` | §3.4 |
| PAUSED/UNKNOWN 任务 pin 保护 | `test_held_artifacts_of_paused_and_unknown_tasks_survive_withdrawal` | §5 |
| P14 版本固定读取回归 | `test_recipe_version_pin_read_regression` | §5 |

## 8. 已知缺口与接缝（演练如实记录，不在 U12 修）

- **APK 制品代理下载路由未建**（U10 遗留接缝）：`sourceRef` 指向 s3，公网设备无法直接取包，
  当前 fail-closed。fleet 级真机铺开前必须补（主会话已登记）。
- **候选撤销端点缺失**：失败/拒绝的候选保持可重试（契约语义），没有 `:cancel`；回退依赖更高
  versionCode 恢复包 + 设备侧最新候选优先策略。
- **心跳 apkUpdate 字段**：设备版本上报通道增强仍是建议项（WIRE2 记录）。
- 本演练为集成测试形态（ASGI 内环），未含真机；真机验收按任务卡 `device_acceptance`
  （设备所有者授权）另行执行。
