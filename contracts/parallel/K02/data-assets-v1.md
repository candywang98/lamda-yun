# data-assets/v1 契约 — FROZEN 20260916.1

状态：**FROZEN（已冻结）**，版本 `data-assets/v1@20260916.1`。起草人：W0 总控；裁决人：用户（2026-09-16，7 项全按建议）。基线 `5c4d100`。消费者：A03（素材上传引用+商品价格/编辑回读）、A06（共享池快照/水印/派生）、A07（导入导出）。

## 1. 范围与边界

- **复用现有三模型，不新建任何模型/表**：`ProductRow`（db.py:223）、`MediaAssetRow`（db.py:177）、`ContentRevisionRow`（db.py:342）及其引用表（product_media / content_revision_media / media_derivative / media_group）。
- 本切片冻结字段：媒体上传与引用、商品价格与编辑回读、派生素材输出引用、导入导出批次——即 A03/A06/A07 验收涉及的最小集。
- 不做（已裁决 D2/D3）：素材 DELETE、按 sha256 检索 API、content_revision 单读端点、products 列表分页改造。

## 2. 身份与隔离（冻结）

- 一切按 `tenant_id` 隔离；跨租户读写 → `FORBIDDEN/403`（problem+json，code 见 §5）。
- `MediaAsset` 身份 = `(tenant_id, sha256)` 内容寻址，重复上传同内容 → 去重返回既有资产（MediaUploadRow expected_sha256 直传 + `:complete` 两段式）。
- 引用关系唯一键沿用：`Unique(product_id, media_asset_id)`、`Unique(revision_id, media_asset_id)`。

## 3. 价格语义（已裁决 D1：维持十进制字符串）

- 商品价格全链路为**非空十进制字符串** `^[0-9]+(\.[0-9]{1,2})?$`；**null 一律 422，0 合法**，无「面议」语义。导入/导出/过滤 minPrice/maxPrice 同口径。
- 闲鱼订单 `amount_cents`（可空整数分）属另一域，禁止混用；导出列名区分 `price`（商品，字符串）与 `amount_cents`（订单，整数）。

## 4. 分页/排序/幂等（冻结，新端点一律照此）

- 新增列表端点：`page=1, page_size=50`（上限 200）+ `total` 信封，排序 `created_at desc, id desc`。
- 既有 `GET /products` 无分页（已裁决 D3：不动）、events 游标 `after_id` 维持现状。
- 写操作幂等：`Idempotency-Key` 请求头；重放 200 + `Idempotency-Replayed: true`。
- 派生：`POST /media/{source}/derivatives` 202 + `POST /media/derivatives/{id}:result` 回调；A06「输出 asset 引用可验证」= result 携带 `output_asset_id` 且 `GET /media/assets/{id}/references` 反查得到来源。

## 5. 错误码（冻结）

problem+json：`{type, title, status, code, detail, correlation_id, retryable, fields}`。允许集：VALIDATION_ERROR/422、NOT_FOUND/404、CONFLICT/409、FORBIDDEN/403、AUTHENTICATION_REQUIRED/401。空池失败=引用不存在→NOT_FOUND；缺媒体行=VALIDATION_ERROR + fields 指明行号列名。

## 6. 裁决记录（用户 2026-09-16 拍板，全按建议）

| # | 事项 | 裁决 |
|---|---|---|
| D1 | 价格 null/0 | ✅ 维持十进制字符串、null=422、0 合法；面议语义另立版本 |
| D2 | 素材 DELETE | ✅ 本切片不做 |
| D3 | products 分页 | ✅ 旧端点不动，新过滤走 `:filter` |

## 7. 正/负 fixture：`contracts/parallel/K02/fixtures/`（4 个，随本契约冻结）

## 8. 消费者验证命令

- A03：`uv run pytest -q tests/integration/test_backend_accounts_media_content.py`
- A06/A07：实现线交付时按各自任务卡补集成测试命令。
