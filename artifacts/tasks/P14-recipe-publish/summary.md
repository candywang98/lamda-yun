# P14 签名 Recipe 人工发布

日期：2026-09-08
设备：未在本轮对 OnePlus 做签名包真机发布（模块自测先过）。G3 未授权，不点闲鱼发布。

## 做了什么

- 生产 API 新增人工 Recipe 目录，签名强制：
  - `POST /api/v1/recipes` 必须用受信 `automation_signing_public_keys` 做 Ed25519 校验
  - 拒绝 `hash-pinned-builtin`
  - `POST /api/v1/recipes/{id}:publish` 指定 `targetDeviceIds` + `idempotencyKey`
  - `POST /api/v1/recipes/{id}:revoke` 不删 blob
  - 禁止把 LocalRecipePackage 走 automation `:promote` 百分比发版
- Companion：
  - `GET /companion/v2/recipes/active` 与按 version 下载
  - `RecipePackageManager` 先写临时文件，再校验 canonical SHA-256 + Ed25519
  - claim 若该设备有 PUBLISHED 部署，CommandV1 钉已发布 hash，而不是内置 probe
- 内置 probe 仍可用；内置不是已发布目录。

## 证据

- `tests/integration/test_backend_control_api.py::test_recipe_catalog_requires_signature_and_manual_device_publish`
- `tests/integration/test_control_api_migrations.py` 含 `recipe_device_deployment`
- Companion `RecipeCatalogTest` / `RecipeEngineTest`

## 未完成

- 首尔生产尚未部署本包（需重启 cloudctl-mobile-api，并配置受信公钥）。
- 未在 OnePlus 上跑「签名包领取」真机。
- 网页 T041 发版按钮未做。
- G3 仍未过。
