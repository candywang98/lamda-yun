# A03-WC 交付报告 — 复用素材与商品 API（最小持久闭环）

- TaskID: A03-WC
- 基线 SHA: `ce074df`
- 分支: `agent/a03-data-assets`（worktree `p14-worktrees/a03-media`）
- 契约版本: `data-assets/v1@20260916.1`（FROZEN，`contracts/parallel/K02/data-assets-v1.md` + `contracts/parallel/K02/fixtures/` 4 个正负用例）
- 日期: 2026-09-16（Asia/Shanghai）

## 1. 契约符合性核对表

| # | 契约条款（§） | 结论 | 说明 / 修复 |
|---|---|---|---|
| 1 | §1 复用现有三模型，不新建模型/表 | ✓ | 零新表、零迁移。幂等键持久化载体复用 `audit_event.metadata_json`（见未决项 3） |
| 2 | §2 tenant 隔离，跨租户 403 FORBIDDEN | ✗→修复 | `create_product`/`update_product`/`update_product_media` 原先把跨租户 media id 当「不存在」返回 422；现按主键全局解析：存在但 tenant 不同 → `ForbiddenError` 403 |
| 3 | §2 `MediaAsset` = (tenant, sha256) 内容寻址去重 | ✓ | `media_by_hash` + 两段式上传（`expected_sha256` 直传 + `:complete`）；新增测试断言重复 initiate 同内容 → `state=COMPLETED` 返回既有资产 |
| 4 | §2 引用唯一键 `Unique(product_id, media_asset_id)`、`Unique(revision_id, media_asset_id)` | ✓ | db.py 未动 |
| 5 | §3 价格非空十进制字符串 `^[0-9]+(\.[0-9]{1,2})?$`，null=422，0 合法 | ✓ | `ProductCreate.price` pattern 既有；新增测试覆盖 null / `12.800` / `-1` / `abc` 均 422，`0` 与 `12.80` 合法 |
| 6 | §3 amount_cents（订单）与 price（商品）不混用 | ✓ | 未触碰 orders 域 |
| 7 | §4 新列表端点 pageSize 上限 200 + total 信封 + created_at desc,id desc | ✗→修复 | `GET /media/assets` pageSize 上限 100 → 200（routes.py Query le=200）；排序与 total 信封原本已符合；既有测试 `pageSize=101→422` 改为 `pageSize=201→422` |
| 8 | §4 旧 `GET /products` 无分页（D3 不动）、events after_id 现状 | ✓ | 未改动 |
| 9 | §4 写操作 `Idempotency-Key`：重放 200 + `Idempotency-Replayed: true` | ✗→修复 | `POST /products` 原先无幂等。现：首次 201 + `Idempotency-Replayed: false`；同 key 同请求体重放 200 + `true` 返回原商品；同 key 异请求体 409（对齐 `create_plan` 的 request_sha256 语义）。key + `request_sha256` 写入 `product.created` 审计行 metadata，跨请求/重启可查（DB 持久，非缓存） |
| 10 | §4 派生 `POST /media/{source}/derivatives` 202 + state PENDING | ✗→修复 | 初始 state `QUEUED` → `PENDING`（fixture k02-positive-derivative）；202 路由原有 |
| 11 | §4 A06：result 携带 `output_asset_id` 且 references 反查得到来源 | ✗→修复 | `GET /media/assets/{id}/references` 新增 `sources: [{derivativeId, sourceAssetId, profileId, state}]`（以该资产为输出的 derivatives）；`error_code` 无 `outputAssetId` → state=FAILED 已有，新增测试 |
| 12 | §5 problem+json code 允许集（VALIDATION_ERROR/422 等） | ✗→修复 | FastAPI `RequestValidationError` 原先返回 `REQUEST_VALIDATION_ERROR`（不在允许集）→ 改为 `VALIDATION_ERROR`；`fields` 键由 `body.price` 剥前缀为 `price`，对齐 fixture |
| 13 | §5 引用不存在 → NOT_FOUND/404（空池失败同型） | ✗→修复 | products 三条写路径（create/update/media update）中媒体资产不存在由 `ValidationError` 422 → `NotFoundError` 404 |
| 14 | fixture `k02-positive-product` | ✓（修复后） | 价格边界 + 媒体引用 + 幂等重放全覆盖（见 §2 测试 T1）；`media[0].role` 字面为 null 的疑议见未决项 1 |
| 15 | fixture `k02-negative-price-null` | ✓ | T2：422 + `code=VALIDATION_ERROR` + fields 含 price；三位小数/负数/非数字同 422 |
| 16 | fixture `k02-negative-media-404` | ✓（修复后） | T3：不存在 id → 404 NOT_FOUND；跨租户 → 403 FORBIDDEN；update 路径同样 |
| 17 | fixture `k02-positive-derivative` | ✓（修复后） | T4：202 PENDING → SUCCEEDED 带 outputAssetId → references.sources 反查；FAILED 分支 |
| 18 | 任务4 编辑回读一致性（含 media 顺序 role/sort_order） | ✗→修复 | `POST /products`、`PUT /products/{id}`、`:archive` 响应原先缺 `media[].role`（POST/PUT 只回 `{mediaAssetId, sortOrder}`）；现统一传完整 `ProductMediaRow`（mediaAssetId/sortOrder/role），响应=GET 回读。T5 断言 PUT 后回读 price/title/revision/media 顺序一致，及 `PUT /media` 重排后回读一致 |

## 2. 测试证据

命令与结果（退出码均 0）：

| 命令 | 基线（ce074df） | 交付后 |
|---|---|---|
| `uv run pytest -q tests/integration/test_backend_accounts_media_content.py` | 12 passed | **17 passed**（12 既有 + 5 新增 K02/回读用例） |
| `uv run pytest -q`（全量） | 670 passed, 1 skipped | **675 passed, 1 skipped**（0 新失败） |
| `uv run pytest -q tests/contracts/test_openapi_contract.py` | — | 1 passed |

新增测试（`tests/integration/test_backend_accounts_media_content.py`）：

- `test_k02_positive_product_price_boundary_media_reference_and_idempotency`（fixture 1 + §2 去重 + 幂等重放/异 body 409/无 key SPU 409 + price "0"）
- `test_k02_negative_price_null_and_malformed_values`（fixture 2）
- `test_k02_negative_media_reference_404_and_cross_tenant_403`（fixture 3，含 PUT/`/media` 路径）
- `test_k02_positive_derivative_roundtrip`（fixture 4，含 FAILED 分支）
- `test_k02_product_edit_readback_consistency`（编辑回读 + 引用反查 productIds）

既有测试按契约更新的断言（行为变更，非放松）：

- 跨租户 media 引用：422 → 403 + `code=FORBIDDEN`
- `pageSize=101` 422 → `pageSize=201` 422（上限 200）

openapi：`uv run python scripts/export_openapi.py` 重导出 `packages/api-contracts/openapi.json`（POST /products 新增 Idempotency-Key header 参数与 200 重放响应；/media/assets pageSize maximum 100→200）。无新增端点。

## 3. 变更文件（owned paths 内）

- `services/control-api/src/cloudctl_api/app.py` — 422 problem code/fields 对齐 §5
- `services/control-api/src/cloudctl_api/services.py` — `_resolve_media_assets`（404/403 区分）、`_product_idempotency_replay`/`_product_media_rows` helper、`create_product` 幂等+返回 `(view, created)`、update/archive 响应 media 补全、derivative PENDING、references 增加 sources
- `services/control-api/src/cloudctl_api/routes.py` — POST /products 幂等头/响应码、pageSize le=200
- `tests/integration/test_backend_accounts_media_content.py` — 断言更新 + 5 个新用例
- `packages/api-contracts/openapi.json` — 重导出
- 本报告

## 4. 未决项 / 契约疑议（请总控裁决）

1. **fixture `k02-positive-product` 的 expect body 字面**：`"media":[{"id":"{{media_asset_id}}","role":null}]` — 键名 `id` 与既有 API 形状 `mediaAssetId` 冲突；`role:null` 与 DB 非空 role + 回读自动推断（首个 cover）冲突。按任务卡「编辑回读一致性（含 role/sort_order）」口径，本轮保留 `mediaAssetId/sortOrder/role` 形状并让 POST/PUT 响应与 GET 回读完全一致。若要求字面对齐 fixture，需同时改 GET/列表/openapi/前端，建议另立裁决。
2. **负 fixture body 缺必填字段**：`k02-negative-price-null` / `k02-negative-media-404` 的请求体无 `category`/`stock`（ProductCreate 必填），原样发送会先被 schema 422 拒绝而到不了目标分支。测试按 fixture 意图补全字段验证目标语义。若要求 fixture 原样可发需给两字段设默认值（改 API 合同）。
3. **POST /products 幂等存储载体**：因 DB_MIGRATION 锁（归并行线），未给 `product` 表加 `idempotency_key` 列，改为存 `product.created` 审计行 `metadata_json`（`idempotency_key` + `request_sha256`），SQL 按 tenant/action 过滤后 Python 侧匹配，SQLite/PG 均可用。若后续迁移解锁，建议加列 + `Unique(tenant_id, idempotency_key)` 并切换查询。
4. **`:result` 对不存在 derivative 返回 422**（VALIDATION_ERROR）：契约 §5 语义上或应为 404，但 fixture 未覆盖该负例，未做无依据改动。
5. **content payload 的 mediaAssetIds 校验**（`_assert_payload_media`）跨租户/不存在仍 422：属 content 域（A06/A07 消费面），本切片未动；既有测试依赖 422。
6. ruff 在 `routes.py:593`（B008）/`services.py:1862,2582`（E501）有 3 个**基线即存在**的告警（stash 验证），未纳入本轮修复。

## 5. 环境备注

工作树 `.venv` 原缺 dev 依赖（pytest），已 `uv sync --extra dev --frozen` 同步（uv.lock 未变，`--frozen`）。首次跑全量前记录基线，见 §2。
