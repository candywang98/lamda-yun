# delivery-delta/v1 契约 — FROZEN 20260916.1

状态：**FROZEN（已冻结）**，版本 `delivery-delta/v1@20260916.1`。起草人：W0 总控（fleet-first K12）。基线 `781b2d0`。消费者：B15（素材）、B16（可维护 Recipe）、P10、O10（订单）、X11/X12、F10–F15。

上位契约（已冻结，本契约**逐条引用、不重定义**）：
- `contracts/parallel/K02/data-assets-v1.md`：Product/MediaAsset/ContentRevision 三模型、租户隔离、价格十进制字符串、分页信封、错误码。
- `contracts/parallel/K05/platform-recipe-v1.md`：PublishTarget 语义、发布三档、定位器引用、受控提交。
- `contracts/parallel/K03/task-schedule-v1.md`：幂等键命名空间。
- `contracts/phase1/order-sync-slice2-20260915.md`：订单分页与多屏执行器。
- `contracts/phase1/p14-recipe-version-contract.md`：Recipe 签名/版本/分发。

## 1. 范围与边界

只补多机交付差额：媒体交付业务身份、字段输入证明引用、订单去重键、多设备目标展开、未证实能力台账。**不新增模型/表，不改已发布 Recipe 字节。**

## 2. 媒体交付业务身份（冻结）

- `mediaDeliveryId`（command-v1 已有字段）的语义冻结为：`(tenantId, orderedMediaAssetIds)` 的业务身份。
- **有序**选图：`orderedMediaAssetIds` 为显式顺序数组；`deliveryDigest = sha256(canonical_list)`，canonical_list = 每行 `mediaAssetId={id}` 按**给定顺序**（非排序）`\n` 连接。同集合不同顺序 → 不同 deliveryDigest（B05 有序选图语义直译）。
- 同一 deliveryDigest 重试（重发/重领）复用既有 mediaDeliveryId；不同设备各自展开的任务各有独立 mediaDeliveryId（见 §4）。

## 3. 字段输入证明（冻结，引用不重定义）

- 发布成功声明必须逐必填字段携带 `InputProof`（定义在 `contracts/ui-observation/v1` §4）。
- **必填字段缺失或 inconclusive 不能记全字段发布成功**：结果身份按实际达成分档（open-only 停确认点 / 部分字段失败），禁止以「任务 SUCCEEDED」掩盖字段缺口。
- 价格语义完全沿用 K02 §3（十进制字符串，null 422，0 合法；与订单 amount_cents 分域）。

## 4. 多设备目标展开（冻结，多机核心）

一个业务发布目标（PublishTarget/商品）展开到 N 台设备时：
- 展开产物是 N 个**独立任务**，各自携带 `(accountId, bindingVersion, deviceId, publishTargetExpansionId)`；`publishTargetExpansionId = sha256(tenantId:publishTargetId:deviceId:mediaDeliveryId)`。
- **账号绑定显式化**：每个展开项的 accountId 必须来自显式的账号↔设备绑定关系；不存在「一个账号无差别撒到多机」的隐式展开——无绑定的展开项整批拒绝 `422 FANOUT_ACCOUNT_UNBOUND`（先校验后建任务，不建一半）。
- 与 fleet-identity §6 账户写互斥联动：展开批次创建后仍逐任务过 ACCOUNT_BUSY 检查；批次内同账号多设备任务由调度器错峰，不并发 RUNNING。
- 幂等：展开操作幂等键沿用 K03 命名空间 `expand:{publishTargetId}:{batchDigest}`；重复展开返回既有批次。

## 5. 订单分页与去重键（冻结，引用补差）

- 订单列表分页沿用 K02 §4 信封（page/page_size≤200 + total；`created_at desc, id desc`）。
- 去重键：`Unique(tenantId, platform, platformOrderId)`；slice2 多屏分页游标沿用 order-sync-slice2-20260915.md，本契约不另造游标。
- 订单任务与发布任务的键空间互不混淆（前缀 `order:` vs 任务创建/重试键，见 K03 §6）；同一业务目标重试不得复用订单采集键。

## 6. 未证实能力台账（冻结）

以下能力为 `PENDING_VERIFICATION`，须逐项真机证据后才可改 `SUPPORTED`，**旧 APK A 级参考不构成当前支持证明**：

| 能力 | 状态 |
|---|---|
| SKU/多规格发布 | PENDING_VERIFICATION |
| 拍卖出价/设置 | PENDING_VERIFICATION |
| 价格修改页完整字段 | PENDING_VERIFICATION |
| 拼多多/其它平台页面 | PENDING_VERIFICATION |

- Recipe/命令注册表不得声明上述能力；声称支持的验收记录必须带平台真实回读证据。

## 7. fixtures（随契约冻结）

- `k12-positive-multidevice-expansion.json`：2 设备显式绑定展开 + 各自 expansionId 期望值（check 脚本复核）。
- 负例：
  - `k12-negative-account-spray.json`：无绑定隐式撒号 → 整批 422；
  - `k12-negative-missing-field-success.json`：缺必填字段却声明全字段成功 → 拒绝；
  - `k12-negative-sku-claimed-supported.json`：Recipe 声明 SKU 为 SUPPORTED → 注册拒绝。

## 8. 验证命令（起草时实际执行）

```
python3 contracts/delivery-delta/v1/tools/check_fixtures.py  # 退出码 0
python scripts/plan_guard.py docs/current/tasks.json        # valid
```

**消费者义务**：B15 素材引用按 §2；O10 订单按 §5；X11/X12 发布展开按 §4；F10–F15 验收记录按 §6 台账登记。未落地前不得宣称 K12 验收范围完成。
