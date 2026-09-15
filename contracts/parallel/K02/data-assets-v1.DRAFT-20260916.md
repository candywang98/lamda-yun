# data-assets/v1 契约（草案）— DRAFT 20260916

状态：**DRAFT（未冻结）**。起草人：W0 总控。基线 `5c4d100`。消费者：A03（素材上传引用+商品价格/编辑回读）、A06（共享池快照/水印/派生）、A07（导入导出）。冻结需用户拍板 §6 裁决项并登记 01 合同状态。

## 1. 范围与边界

- **复用现有三模型，不新建任何模型/表**：`ProductRow`（db.py:223）、`MediaAssetRow`（db.py:177）、`ContentRevisionRow`（db.py:342）及其引用表（product_media / content_revision_media / media_derivative / media_group）。
- 本切片冻结字段：媒体上传与引用、商品价格与编辑回读、派生素材输出引用、导入导出批次——即 A03/A06/A07 验收涉及的最小集。
- 不做：素材 DELETE、按 sha256 检索 API、content_revision 单读端点（维持现状，后续切片再议）。

## 2. 身份与隔离（钉死）

- 一切按 `tenant_id` 隔离；跨租户读写 → `FORBIDDEN/403`（problem+json，code 见 §5）。
- `MediaAsset` 身份 = `(tenant_id, sha256)` 内容寻址，重复上传同内容 → 去重返回既有资产（沿用 MediaUploadRow expected_sha256 直传 + `:complete` 两段式）。
- 引用关系唯一键沿用：`Unique(product_id, media_asset_id)`、`Unique(revision_id, media_asset_id)`。

## 3. 价格语义（⚠ 裁决项 D1）

- 现状：商品价格全链路为**非空十进制字符串** `^[0-9]+(\.[0-9]{1,2})?$`（schemas.py:106 等 5 处、command_v1.py:102、content_payload.py:69）。**0 合法、无 null、无"面议"语义**。
- 任务卡原文写「价格null/0 边界」——与现状冲突。草案采纳：**维持字符串语义，null 一律 422，0 合法**（导入/导出/过滤 minPrice/maxPrice 同口径）。引入 null/面议 属新语义，本切片不做（如需，另立契约版本）。
- 对比约束：闲鱼订单 `amount_cents`（可空整数分）是**另一个域**，禁止在 data-assets 侧混用两种表示；导出列名区分 `price`（商品，字符串）与 `amount_cents`（订单，整数）。

## 4. 分页/排序/幂等（钉死，新端点一律照此）

- 新增列表端点：`page=1, page_size=50`（上限 200）+ `total` 信封，排序 `created_at desc, id desc`（对齐 media assets 现状 routes.py:274）。
- 既有 `GET /products` 无分页、events 游标 `after_id`：**维持不动**（避免破坏已验收消费方），但在本契约覆盖的新端点统一用 page 信封。
- 写操作幂等：`Idempotency-Key` 请求头；重放 200 + `Idempotency-Replayed: true`。
- 派生：`POST /media/{source}/derivatives` 202 + `POST /media/derivatives/{id}:result` 回调（异步两段式沿用）；A06 验收的「输出 asset 引用可验证」= result 携带 `output_asset_id`，且 `GET /media/assets/{id}/references` 能反查到来源。

## 5. 错误码（钉死）

problem+json：`{type: "urn:cloudctl:problem:<code小写>", title, status, code, detail, correlation_id, retryable, fields}`。本切片允许集：VALIDATION_ERROR/422、NOT_FOUND/404、CONFLICT/409、FORBIDDEN/403、AUTHENTICATION_REQUIRED/401。A06「空池失败」= 引用不存在的 asset → NOT_FOUND；A07「缺媒体行」= VALIDATION_ERROR + fields 指明行号列名。

## 6. 裁决项（冻结前需用户拍板）

| # | 事项 | 草案建议 | 备选 |
|---|---|---|---|
| D1 | 价格 null/0 语义 | 维持十进制字符串、null=422、0 合法 | 引入 null=面议（波及 5+ 处校验与 Companion 协议，另立版本） |
| D2 | 素材 DELETE | 本切片不做（引用完整性风险，references 端点先落地） | 做「仅无引用可删」软删 |
| D3 | products 列表分页 | 旧端点不动，新过滤走 `:filter` | 给 GET /products 补分页（破坏现有消费方） |

## 7. 正/负 fixture（见 fixtures/ 目录）

- `k02-positive-product.json`：合法商品（price "0"/"12.80" 两边界）+ media 引用。
- `k02-negative-price-null.json`：price null → 422 VALIDATION_ERROR + fields[price]。
- `k02-negative-media-404.json`：引用不存在 media asset id → 404 NOT_FOUND。
- `k02-positive-derivative.json`：202→result(output_asset_id)→references 反查闭环。

## 8. 消费者验证命令

- A03：`uv run pytest -q tests/integration/test_backend_accounts_media_content.py`
- A06/A07：对应新增集成测试（实现线交付时补，门禁命令在各自任务卡）。
