# ORDERS-SLICE1-W1 后端交付报告

- TaskID: ORDERS-SLICE1-W1
- BaselineSHA: d942bd3
- BranchSHA: ed74a10（分支 `agent/order-sync-api`，单提交 `Add order sync slice 1 backend (order-sync/20260915.1)`）
- ContractVersion: order-sync/20260915.1（`contracts/phase1/order-sync-20260915.md`，未改动）
- 交付时间: 2026-09-15（Asia/Shanghai）

## OwnedPaths（实际改动）

全部落在授权范围内：

- `services/control-api/migrations/versions/20260915_0021_xianyu_orders.py`（新增，66 行）
- `services/control-api/src/cloudctl_api/**`：
  - 新增：`orders_service.py`（177）、`orders_routes.py`（89）、`xianyu_orders.py`（259）、`xianyu_orders_routes.py`（39）
  - 修改：`db.py`（+35，OrderRow ORM）、`mobile_schemas.py`（+15，ReadOrdersStep）、`mobile_actions.py`（+74，冻结形状校验）、`mobile_service.py`（+29/-10，创建门禁与 claim 旁路）、`app.py`（+12，装配）
- `tests/integration/test_orders_sync.py`（新增，647 行，20 个测试）
- OpenAPI 导出产物：`packages/api-contracts/openapi.json`（+524，由 `python3 scripts/export_openapi.py` 重新生成）
- 本报告所在证据目录

### 必须改动的既有文件及理由

| 文件 | 理由 |
| --- | --- |
| `db.py` | 全部 ORM 模型集中于此，OrderRow 只能加在这里（与 ImThreadRow 同模式） |
| `mobile_schemas.py` | `MobileStep` 是闭集判别联合，新增 `ui.readOrders` 步骤 DTO 必须扩展该联合 |
| `mobile_actions.py` | 冻结形状校验与 command_type 常量沿维护动作同模式放在这里 |
| `mobile_service.py` | `_insert_task` 是唯一创建门禁入口（新动作必须在此校验）；claim 路径会对未知 command_type 解析 builtin recipe（KeyError），必须把 `xianyu.collect_orders.steps.v1` 加入免 pin 集合 `UNPINNED_STEPS_COMMANDS` |
| `app.py` | 组合根，注册新 service/router |
| `packages/api-contracts/openapi.json` | 契约测试是严格相等，新增路由必须同步再生成（任务书明确要求提交其 diff） |

## ChangedFiles（git diff --stat d942bd3..HEAD）

```
 packages/api-contracts/openapi.json                | 524 +++++++++++++++++
 .../versions/20260915_0021_xianyu_orders.py        |  66 +++
 services/control-api/src/cloudctl_api/app.py       |  12 +
 services/control-api/src/cloudctl_api/db.py        |  35 ++
 services/control-api/src/cloudctl_api/mobile_actions.py |  74 +++
 services/control-api/src/cloudctl_api/mobile_schemas.py |  15 +
 services/control-api/src/cloudctl_api/mobile_service.py |  29 +-
 services/control-api/src/cloudctl_api/orders_routes.py  |  89 +++
 services/control-api/src/cloudctl_api/orders_service.py | 177 ++++++
 services/control-api/src/cloudctl_api/xianyu_orders.py  | 259 +++++++++
 services/control-api/src/cloudctl_api/xianyu_orders_routes.py |  39 ++
 tests/integration/test_orders_sync.py              | 647 +++++++++++++++++++++
 12 files changed, 1956 insertions(+), 10 deletions(-)
```

## 门禁证据（全部真实执行）

| # | 命令 | 退出码 | 结果 |
| --- | --- | --- | --- |
| 1 | `uv run python scripts/export_openapi.py`（等价 `python3 scripts/export_openapi.py`，见下方说明） | 0 | 重新生成 openapi.json，+524 行（5 个新路径：`/api/v1/orders`、`/api/v1/orders/{order_id}`、`/api/v1/xianyu/orders:collect`、`/api/v1/xianyu/orders/runs/{run_id}`、`/companion/v2/orders/batch`） |
| 2 | `uv run pytest -q tests/integration/test_orders_sync.py tests/contracts/test_openapi_contract.py` | 0 | 21 passed（订单 20 + 契约 1） |
| 3 | `uv run pytest -q`（全量回归） | 0 | 626 passed, 1 skipped（基线 606 passed / 1 skipped，+20 全为本切片新增，无新失败） |
| 4a | 迁移 up：`CLOUDCTL_DATABASE_URL=sqlite+aiosqlite:///<tmp>.db uv run alembic upgrade head`（在 `services/control-api/`） | 0 | `... -> 20260915_0021` 执行，`xianyu_order` 表存在、14 列 |
| 4b | 迁移 down：`... uv run alembic downgrade 20260915_0020` | 0 | 表干净移除（sqlite_master 计数 0），再次 `upgrade head` 亦 exit 0 |

补充：

- pytest 内另有 `test_orders_migration_up_down_roundtrip`（alembic 0020→head→0020→head + 唯一键/三组 check 约束的 IntegrityError 断言）作为可重复的迁移证据。
- 调用方式说明：本机未对系统 python 安装 `-e '.[dev]'`，`python3 scripts/export_openapi.py` 直接跑会 `ModuleNotFoundError`，故用 `uv run python scripts/export_openapi.py`（与 `uv run pytest` 同一虚拟环境，输出文件与默认路径一致）；`uv run pytest -q` 与任务书一致。
- ruff：新增文件 0 错误、已 format；`mobile_actions.py`/`mobile_service.py`/`db.py` 上各剩 2/6/4 个 **基线既有** E501（已用 `git show d942bd3:<file> | ruff check --stdin-filename` 对比确认，非本切片引入）。

## 实现要点与设计取舍

1. **表/迁移**：`xianyu_order` 完全照 im_thread 模式（tenant_id 索引无外键、device_id FK device.id）；id 用 String(36)+服务端 uuid4（仓库 UUID 惯例）。check 约束（platform/direction/amount>0）按契约用 `batch_alter_table` 添加（SQLite 可移植），down 先 batch drop 再 drop_table，干净回滚。
2. **幂等语义**：按唯一键 `(tenant_id, device_id, platform, order_key)` select-by-key，存在即跳过且**不更新快照**（slice 1 首次为准，有测试固化「重放改标题不覆盖」）；批量内有重复键时借助同一 UoW 的 autoflush 识别。任何 accepted>0 返回 201，全重复 200，结构均为 `{"accepted": n, "duplicates": m}`。
3. **occurred_at**：按任务书倾向选「置空」——DTO 收 `str | None`，服务端 fromisoformat（容忍 Z 后缀、naive 补 UTC），解析失败存 NULL（测试固化 "3天前"→null）；类型非法（如数字）仍 422。collected_at 当前不落库（表无此字段），仅接受为可选字符串。
4. **422 明细格式**：仓库统一用 problem+json 的 `fields` 映射（`body.orders.0.order_key: msg`），index 与字段在键名中，等价承载契约「指明 index 与字段」的信息；未为订单单独引入 `{"detail":[...]}` 特例，以保持全站错误格式一致（不削弱校验本身）。
5. **请求键名**：companion 批量体与查询参数按契约字面用 snake_case（`order_key` 等、`?device_id=&direction=&status_text=`）；collect 入参同时接受 `device_id/max_rows` 与 `deviceId/maxRows`（populate_by_name）。响应视图沿用仓库 camelCase 惯例（orderKey/itemTitle/…，与 im 视图一致），raw 仅出现在单条详情。
6. **采集编排**：完全仿 `maintenance:run` —— `require_permissions(DEVICE_CONTROL)`、Idempotency-Key 必填≤100、`run_id=uuid5(ORDERS_RUN_ID_NAMESPACE, "{tenant}:xianyu-orders-collect:{key}")`、task_key 含 run 后缀、`MobileTaskRow.batch_id=run_id`、runs 查询复用 batch_id 聚合（viewer 可读，DEVICE_READ）。
7. **冻结形状 `xianyu.collect_orders.steps.v1`**：固定 5 步 `ui.tap(profile) → ui.tap(入口按方向 sold/bought) → 恰好一个 ui.readOrders(direction/maxRows1..10/locatorRef=xianyu_orders_container) → ui.screenshot → run.log(XIANYU_COLLECT_ORDERS_DONE)`，逐位置逐字段校验；任何含 `ui.readOrders` 的任务（含裸 POST /api/v1/mobile/tasks）都必须精确匹配（8 个变异用例 422）。导航锚点用 §7 的未验证定位器名（verified=false 由 W2 设备侧 fail-closed，服务端只冻结名字）。
8. **红线**：steps[0] 头部只有 `totalTimeoutMs/mediaDelivery/controlEpoch/orderCollection`，**无 `action` 键**（元数据嵌套在 `orderCollection` 下，与 maintenance 的做法一致）；`steps_action_identity` 只哈希含 action 的步骤，哈希不变量保持（测试断言 hashed==5）。claim 对该 command_type 免 recipe pin（`UNPINNED_STEPS_COMMANDS`），不会因 `builtin_recipe_ref` KeyError 而炸。collect 任务无 G3 写副作用，不进 action ledger（对 collect 任务请求 intent 会得到 G3_NOT_ACCEPTED，fail-closed 不变）。
9. **安全门未削弱**：companion 端点复用 `mobile_routes.binding`（与 im/messages 完全相同）；操作员只读端点仅 current_actor+租户隔离（与 im 一致）；collect 写操作需 DEVICE_CONTROL，runs 读需 DEVICE_READ；未触碰任何既有认证/权限代码路径。

## 未决项（不扩大范围，留给总控裁定）

1. `collected_at` 语义：契约请求体含该字段但表无对应列，当前接受即忽略；若 slice 2 需要采集批次审计，需要加列。
2. 422 载荷格式为仓库统一 problem+json（fields 含 index+字段），非契约字面的 `{"detail":[...]}`；如需字面格式需改全局异常处理器（影响面大，未做）。
3. 契约 §5 允许 `ui.tapText` 导航，冻结形状 v1 只绑定 `ui.tap`+定位器注册名；真机勘测后若需文本锚点，需冻结 v2 形状。
4. `RESULT_TYPES` 未加 `xianyu.collect_orders.steps.v1`（与 maintenance steps 任务一致，complete 不带 resultType；W2 若在 complete 里带 resultType 会被 422 拒绝——W2 请按 maintenance 惯例不带）。
5. item_title/buyer_name 列长（256/128）为自选值，契约未规定；超长静默截断。
6. 操作员查询 status_text 过滤是精确匹配；「待发货/已发货」前缀/模糊匹配未实现（契约未要求）。

## 下一步

- W2：按 §5/§7 实现 `ui.readOrders` 解析与 LOCATOR_UNVERIFIED fail-closed，步成功后调 `/companion/v2/orders/batch`；complete 不带 resultType。
- W3：`/orders` 页面 + `src/api/orders.ts`（本切片响应字段为 camelCase 视图，见上文第 5 点）。
- 总控：真机勘测后冻结订单列表定位器并翻转 verified；随后做真机采集验收（本任务只有软件测试，未做任何硬件验收结论）。

## 需要的锁

- 真机验收阶段需要 DEVICE 锁（由总控持有，串行执行）；软件侧无需额外锁。
