# P14 shared contract — recipe-version/20260909.1

Frozen by Root for the three implementation lanes. Extend existing APIs and CommandV1; no new execution protocol. Changes to this contract require Root coordination.

## Operator HTTP API

- Existing `POST /api/v1/recipes` registers a fully signed LocalRecipePackage. Existing signature/trust validation remains mandatory.
- Add `GET /api/v1/recipes` -> `{ "items": RecipeVersion[] }`, tenant scoped, permission `recipe.publish`. Return newest first. No fake catalog or localStorage fallback.
- Existing `GET /api/v1/recipes/{versionId}` -> RecipeVersion.
- Existing `POST /api/v1/recipes/{versionId}:publish` and `:revoke` keep `{targetDeviceIds: string[], idempotencyKey: string}`.
- Add `POST /api/v1/recipes/{targetVersionId}:rollback` -> RecipeVersion, body `{targetDeviceIds: string[], idempotencyKey: string, expectedCurrentVersionId: string}`. User chooses the known previously deployed target; backend verifies the expected active version and target history for each device/command type. A stale current version fails 409. Rollback is explicit, atomic across requested devices, idempotent, audited, and does not delete package content. Reusing a key for a different action/target fails 409.
- RecipeVersion preserves current fields: `id`, `versionId`, `name`, `version`, `artifactSha256`, `signingKeyId`, `package` (LocalRecipePackage), `deployments`.
- Add RecipeVersion `createdAt` (ISO string); each deployment preserves `id`, `deviceId`, `commandType`, `status` (`PUBLISHED`/`REVOKED`), `previousVersionId`, `idempotencyKey`, and adds `publishedBy`, `createdAt`, `updatedAt`. Actual audit actor/time must be persisted and returned, never synthesized on reads. Catalog includes deployment history needed to select rollback candidates.
- Multi-command manifests must have deterministic per-command deployments, one active per `(tenant, device, commandType)` at DB level. Validate target device existence and tenant ownership, permissions, trusted signature, engine compatibility metadata; retain prior response fields.

## Companion HTTP and command contract

- Keep `GET /companion/v2/recipes/active` -> `{protocolVersion:"cloudctl.recipe/v1", items:[{versionId,sha256,commandType,downloadPath,engineMinVersion,previousVersionId}]}`. Catalog is authoritative only after a successful complete response; errors do not clear known-good state.
- Keep `GET /companion/v2/recipes/{versionId}` signed JSON. Current published deployment OR a live task pinned to this exact version for this authenticated device authorizes download. No cross-tenant or cross-device access; revoked unpinned packages remain unavailable.
- CommandV1 `recipe` remains `{versionId, sha256, engineMinVersion}`. No breaking schema changes.
- At first claim, persist recipe selection with the task in the same transaction/claim lock. Running/paused/reconciling/resumed tasks keep this frozen selection even after publish/revoke/rollback; subsequent claims cannot resolve latest again. Freeze the fallback builtin selection too for existing probe compatibility. Do not disable signature validation for downloaded packages.
- Android verifies expected version/hash, compatible engine, canonical hash and Ed25519 before making immutable package files visible. Invalid IDs/path traversal must be rejected. Interrupted updates cannot destroy existing packages.
- Active recipe mappings and pending updates survive restart. Activate changed mappings only when idle; RUNNING, PAUSED and reconciling tasks stay pinned. Fetch/download the exact claimed historical version when missing. Do not execute a different builtin/version as fallback for a claimed signed recipe.
- No device, deployment or real publish side effects by child agents. Root owns serial integration and acceptance.

## Ownership and tests

CONTROL owns services/control-api and relevant Python tests, including next Alembic migration (check current head first). ANDROID owns mobile/companion and its tests. WEB owns apps/web and its tests. Root owns contracts, generated clients, plans and evidence integration. Children may write their own Markdown summary under artifacts/tasks/P14-multi-agent/<work-item>/.

Backend: focused recipe API, migration, claim/version concurrency, history authorization and audit tests. Android: package update/activation/restart/failure tests plus assembleDebug. Web: catalog/detail, publish/rollback intent, permissions/loading/error tests plus typecheck/build. No weakened tests or production authentication.
