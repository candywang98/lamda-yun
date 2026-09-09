# P14 closeout 2026-09-08 (syncRecipes install)

## Status: CLOSED for install+claim

- Device OnePlus 9R serial `b0644fb5` id `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`
- Companion pid 28727 (post-repair APK, FGS alive, heartbeat OK)
- Ban kept: no disable-sig / auto-publish / xianyu / port 65000 / secrets.xml
- Out of scope: do **not** expand `WRONG_ACTIVE_PACKAGE`

## Three live criteria (re-verified this closeout)

1. `files/recipes/versions/01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f/package.json` exists
   - `kind=LocalRecipePackage` `id=recipe-device-probe-signed`
   - `manifest.hash=825921a415b7b0eaeb832ce1fb6e97847f9f981a45bb57db990491f1001ebd1f`
   - `signingKeyId=phase1-recipe-1`
2. Log: `17:41:23 CompanionSync: Recipe installed versionId=01a07f6d-… sha256=825921a4… downloadHeaderSha256=825921a4…`
   - Header reached the client (Path A dead). No `Recipe synchronization failed` in after-sync window.
3. Task `7f292679-aa07-4908-81b4-07f7dbcb891e` left QUEUED:
   - `attempt=1` `startedAt=2026-09-08T09:41:24.891611Z`
   - then `FAILED` / `WRONG_ACTIVE_PACKAGE` `completedAt=2026-09-08T09:41:26.095338Z`
   - runtime prefs events: Queued → Running/TASK_STARTED → Failed/WRONG_ACTIVE_PACKAGE

## Root cause (Path C, not A/B/kotlin-bytes)

OEM Android 14 on this 9R does **not** expose JCA Ed25519:

- `before-crypto-probe.txt`: `Ed25519 KeyFactory not available` + `Ed25519 Signature not available`
- `before-recipe-probe.txt`: `graphBytesEqual=true` `signBytesEqual=true` `trustedKeyPresent=true` but `verifyPackage` threw `recipe package signature verification failed`
- That is throw-before-write. Explains `NO_RECIPES_DIR` with Python hash + openssl both green.

Fix: APK-bundled Bouncy Castle 1.85.2 `Ed25519Signer` (no global Provider change). Signature checks kept.

- `after-recipe-probe.txt`: same inputs → `verifyPackage=PASS`
- Evidence: `artifacts/tasks/P14-recipe-publish/repair-20260908/` (`repair.patch`, `before/`, `before-installed.apk`)

Dead paths (do not reopen): Path1 empty keys; Path2 header case; Path B Python graph hash; Path A missing download header; Kotlin vs Python canonical bytes (`graphBytesEqual`/`signBytesEqual` true on-device).

## Leftover (not this closeout)

`WRONG_ACTIVE_PACKAGE` after claim. Command still points at builtin recipe `901f795b` / `versionId=recipe-device-probe-1`, while installed signed package is `825921a4` / `recipe-device-probe-signed`. Do not touch unless a new task asks.

## Rollback

`repair-20260908/before-installed.apk` + `before/` three source files. Workspace had other dirty files; no full-repo revert/commit by the repair.
