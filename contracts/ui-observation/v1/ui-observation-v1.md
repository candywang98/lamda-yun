# ui-observation/v1 契约 — FROZEN 20260916.1

状态：**FROZEN（已冻结）**，版本 `ui-observation/v1@20260916.1`。起草人：W0 总控（fleet-first K11）。基线 `781b2d0`。消费者：B12（定位）、B13（定位续）、B14（输入/IME）、B16（可维护 Recipe）、Q12（受控故障测试）、I10、X10/X11、F14/F15。

上位契约（已冻结）：`contracts/parallel/K05/platform-recipe-v1.md`（定位器引用/发布语义/受控提交）、`contracts/phase1/xianyu-anchors-20260915.md`、`contracts/phase1/xianyu-maintenance-anchors-20260915.md`、`contracts/phase1/p09-reconciliation-hardening.md`。P09 三次删除事故（CARD_BOUNDS_UNVERIFIED / UNKNOWN）为本契约反例来源。

## 1. 快照来源标签（冻结）

`source ∈ {a11y_tree, a11y_event, uiautomator_dump, screenshot}`。
- 每个 Observation/fixture **必须**携带 source 标签；不同 source 的树/图**禁止**合并为同一 fixture 或互证相等。
- 截图（screenshot）只能作辅助证据，永远不能单独证明 UI 结构断言（见 §7）。
- 等价断言（treeDigest 相同）只在同 source 内成立。

## 2. Observation 结构（冻结）

```
Observation {
  source, package, appVersion?, windowId, display, insets,
  rotation, capturedAt, sessionEpoch, treeDigest,
  nodes: [ ...原始节点子集或引用... ]
}
```
- `treeDigest = sha256(canonical_tree(nodes))`；canonical_tree = 节点按 (depth, index) 稳定排序，每节点取 `class|resourceId|text|contentDesc|bounds|clickable` 的 `k=v` 行（同 canonical_steps 风格：key 排序、bool 小写、`\n` 连接）。会话内 rotation/insets 变化不改变节点身份字段，但改变 bounds——见 §6 banner 位移反例。
- `sessionEpoch` 与 fleet-identity AuthorizationEnvelope 对齐；跨 sessionEpoch 的两帧不可做「无进展」比较（先比对 sessionEpoch）。

## 3. 候选解析结果（冻结）

定位输出只有两种：
- `Resolved{node, identityProof}`——唯一候选且通过 IdentityProof；
- `Ambiguous{candidates[], reason}`——多候选或零候选；**禁止**自动选择第一个/中心/最大者。Ambiguous 是正常结果，不是异常：任务按 fail-closed 零副作用终止（`LOCATOR_AMBIGUOUS`）或走声明式 fallback（§5）。
- 防误选规则（P09-13 预检冻结）延续：整列表包装节点（全高 wrapper）即使文本匹配也排除，须在 IdentityProof 记录排除依据。

## 4. IdentityProof / InputProof（冻结）

```
IdentityProof {
  locatorKind: text | resource-id | anchor+position | platform-item-id,
  source, nodeDigest,
  crossCheckedAgainst: [source…],        // 跨源复核（可选但删除类必填≥2源）
  platformItemId?: string                 // 仅当真实可读或操作员授权录入
}
InputProof {
  fieldLocator, submittedValue, source,
  imeCommitted: bool, postValue?, inconclusive: bool
}
```
- `platformItemId` **仅在**平台数据可读或授权录入时存在，录入须带 provenance（操作员/时间）；**禁止杜撰或猜测**。
- SET_TEXT 类输入：Flutter 输入重绘后 imeCommitted=false 或 postValue 与 submittedValue 不一致 → `inconclusive=true`，按失败处理，不得当作已填成功继续提交（Q03 幻影输入教训）。

## 5. 可逆导航 vs 不可逆提交（冻结）

- **可逆导航**（返回/滚动/打开页面/填非提交字段）：允许声明式 fallback（如设置搜索路径重启无障碍），受轮询预算约束。
- **不可逆提交**（点发布/确认删除/发消息）：`tapOnce` 语义——单次 dispatch、无 fallback、无重试；与既有 GATED/commit_once/IrreversibleActionGate 完全一致，本契约不放宽。
- 任何 P09 门禁（三元守卫、取消闭环、语义删除 UNKNOWN 提交屏障）的改变必须走 ADR + 用户裁决；**修复不得顺手降级门禁**。

## 6. 轮询预算与无进展退出（冻结）

`PollingBudget{maxAttempts, minIntervalMs, noProgressLimit}`：
- 连续 `noProgressLimit` 次 `treeDigest` 相同（且 sessionEpoch 相同）→ 退出 `NO_PROGRESS`，零副作用。
- 预算耗尽 → fail-closed 终止（`LOCATOR_TIMEOUT`），不自动改用危险策略。
- banner 位移反例：横幅出现导致全树 bounds 平移、treeDigest 变化——**不代表进展**；无进展判定须在剔除已知横幅/键盘层后按业务节点子集 digest 比较（反例 fixture 钉死）。

## 7. 删除证明规则（冻结，P09 事故直译）

- 截图变化、角标数字减少、列表数量减少**单独都不构成**「指定商品已删除」的证明。
- 删除成功证明 = IdentityProof of absence：重读列表（分页完整）+ 目标 IdentityProof（locatorKind + platformItemId 如有）在列表全域不可解析 + crossCheckedAgainst ≥ 2 源。
- 达不到 → UNKNOWN，走对账；**严禁**以重试「碰」成功。

## 8. fixtures（随契约冻结）

- `k11-positive-observation.json`：合法 Observation + treeDigest 期望值（check 脚本复核）。
- 负例：
  - `k11-negative-samename-ambiguous.json`：同名商品两候选 → Ambiguous，禁自动选择；
  - `k11-negative-fullheight-wrapper.json`：整列表 wrapper 文本匹配但被防误选排除；
  - `k11-negative-banner-displacement.json`：横幅位移改变 treeDigest 但业务子集无进展；
  - `k11-negative-input-redraw-lost.json`：输入重绘 imeCommitted=false → inconclusive 失败。

## 9. 验证命令（起草时实际执行）

```
python3 contracts/ui-observation/v1/tools/check_fixtures.py  # 退出码 0
python scripts/plan_guard.py docs/current/tasks.json        # valid
```

**消费者义务**：B12/B13 定位器测试必须消费上述负例（Ambiguous/wrapper/banner）；B14 输入测试消费 input-redraw 负例；未落地前不得宣称 K11 验收范围完成。
