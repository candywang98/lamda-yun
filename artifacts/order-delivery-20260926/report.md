# Durable Order Delivery, 2026-09-26

## Scope And Status

User constraint D-12: production collection and synchronization run on Companion
and cloud, without USB/wireless ADB, Edge or the development computer.
The frozen wire contract is `contracts/phase1/order-delivery-20260926.md`.

This slice is software-verified and cloud-deployed. It is **not device accepted**.
No phone installation, navigation, collection, message sending, publishing,
delisting or trade action was performed. Browser space18 remains with the user.
O10 overall remains IN_PROGRESS / DEVICE_WAIT because broader historical
isolation and device acceptance are not complete.

## Implementation

- Backend `6e08f61`, `eb9ffb4`, `af94623`: heartbeat plus per-claim negotiation,
  atomic task/metadata/account/mobile-binding freeze, original-key replay,
  immutable SCREEN/COMPLETE receipts and exact replay ACK, task-local sequence,
  conflict retention, independent terminal/expired-lease uploads and operator
  delivery state. Legacy screen uploads reject durable task identities.
- Migration `20260926_0035` adds receipt and projection sidecars without
  reassignment or modification of historical order rows.
- Durable projections use an immutable per-order server collection generation
  `(task.created_at, task.id, screen)`. Old deliveries retain receipts/page
  history but do not regress newer durable snapshots. Unchanged observations
  advance the watermark; unseen keys in old runs remain admissible.
- Web `5a231e7` (worker `f5d8f38`): collection/delivery separation, no silent
  downgrade, strict identity validation, immutable retry key/request, bounded
  polling even after collection termination, GET-only manual refresh.
- Android `d0a2dbc` (worker `2c5d0fd`): normal fresh/resume execution and service
  sender are wired, not only helpers. A read's immutable envelope, recovery
  state, success journal and event commit together. COMPLETE and local success
  commit together. Same database retains unconfirmed payloads independently of
  UI leases. ACK identity, retry/backoff, auth pause, permanent block and hashed
  credential scope prevent silent loss/rebinding. Durable single and multiscreen
  tasks do not dual-write legacy channels. Uncertain physical page recovery
  pauses instead of guessing.
- OpenAPI exported once after integration in `3f539e9`.

Cross-review reproduced and corrected two defects before release: old-run
delayed status regression, and inconsistent POST task/delivery snapshots.
Regression tests cover both on SQLite and disposable PostgreSQL.

## Verification

All commands below exited 0. No tests used the production database.

| Surface | Result | Evidence |
| --- | --- | --- |
| Main backend | 144 passed, 1 skipped | `backend-final.log` |
| Focused cloud release backend | 144 passed, 1 skipped | `release-backend-final.log` |
| Main Web | 496 passed, 43 files | `web.log` |
| Focused cloud release Web | 489 passed, 43 files | `release-web.log` |
| Web typecheck/build | Passed on main and release | `web-build.log`, `release-web-build.log` |
| Integrated Android Debug | 1279 tests, zero failures/errors/skips | `android-integrated.log`, local JUnit XML |
| Integrated Android Acceptance | 1265 tests, zero failures/errors/skips | same |
| Debug and Acceptance APKs | Build successful | `android-integrated.log` |
| Scoped Ruff, mypy, Pyright, ESLint | Passed | Controller tool outputs |
| TypeScript contract build | Passed | `pnpm contracts` |

The one backend skip is the SQLite branch of a PostgreSQL row-lock concurrency
test; its PostgreSQL branch executed. Migration up/down/up and history retention
ran on both database engines. Release has seven fewer pre-existing Web tests
than main; no release tests were removed or weakened.

Backend command:

```sh
.venv/bin/pytest -q tests/integration/test_order_delivery.py tests/integration/test_order_delivery_migration.py tests/integration/test_orders_sync.py tests/integration/test_order_checkpoint_runs.py tests/integration/test_fleet_orders_pagination.py tests/integration/test_platform_tasks.py tests/integration/test_control_api_migrations.py tests/integration/test_im_notification_classification.py
```

The same command ran in the focused release worktree using the shared Python
executable and that checkout's pytest source paths.

Web commands, from each checkout's `apps/web`:

```sh
pnpm test
pnpm build
pnpm exec eslint src/views/OrdersView.vue src/api/orders.ts src/features/orders/delivery.ts tests/orders-view.spec.ts tests/orders-api.spec.ts
```

Release build used `pnpm build --base=/cloudctl-mobile/`.

Integrated Android command, from main `mobile/companion`, under exclusive Gradle
ownership after the worker handed it back:

```sh
env JAVA_TOOL_OPTIONS=-Drobolectric.dependency.repo.url=file:///Users/wangziheng/.m2/repository ./build-external.sh --offline --no-daemon --console=plain --continue :app:testDebugUnitTest :app:testAcceptanceUnitTest :app:assembleDebug :app:assembleAcceptance
```

Worker source and focused evidence:
`/private/tmp/cloudctl-im-notify-android-20260926/mobile/companion/.gradle/order-delivery-evidence/REPORT.md`
(focused 76/76, including 27 new tests).

## Deployment

- Focused branch: `release/order-delivery-20260926`, SHA `557f547`.
- Cloud release: `order-delivery-557f547`, activated
  `2026-09-26T15:39:50Z` / `2026-09-26T23:39:50+08:00`.
- Schema: `20260926_0035`.
- Source SHA256: `58b5ead6467f034d4dda220b8d02102bd7d1ce85bb77133fe77f294d08bf3f89`.
- Web archive SHA256: `368434bbd680290b7a4c5a51b9e9e677381067b9d696a4f7c37f8808f0a6b079`.
- New release adds only the scoped backend/Web/contracts changes to the deployed
  `listing-sync-b3bd1f3` baseline, not all unpublished main changes.
- 67-table snapshot backup restored and hashed identically; isolated migration
  upgrade/downgrade/upgrade retained existing data. Production admissions were
  stopped, occupancy rechecked, and 66 original business-table digests compared
  before/after migration, excluding only the Alembic version marker.
- Authenticated existing API reads and served index/static asset bytes passed.
  No new real collection was dispatched; receipt count remains zero.
- Original 128 messages unchanged; OUT count remains 23, task count remains 376.
  Notification mode and receiveOnly=true remain unchanged.
- Rollback restores the verified old application/Web target, retaining the
  additive database schema and all business data; it does not restore a stale
  database dump or delete receipts.

See `activation-result.json`, `deployment.log`, and the reviewed one-off
`deploy.py`. Cloud backups remain on the server; credentials are not copied into
this evidence directory.

## APK Evidence

Built from integrated main Android source `d0a2dbc`; neither APK was installed.

- Debug SHA256: `d4ef29cf65453b6feb2ccfb1fcdd6daf44d2fbff7ec13def4bd674d87ea52f09`.
- Acceptance SHA256: `ef1cdcfbef5fc895c721132695a9bdd5b9ef16f4c3d3bee4b96f24944148d320`.
- Acceptance package: `com.company.cloudctl.companion.acceptance`, versionCode 1,
  versionName 0.1.0. Package/signature/binding checks are still required before
  choosing an installation target; do not blindly install over a business APK.

## Remaining Gates

1. Fresh phone-idle confirmation, exact serial lock and package/signature/binding
   preflight before any APK installation. Start with one phone, then the existing
   three. Do not introduce five/ten/hundred-phone acceptance gates.
2. Real collection, temporary network loss, retained upload and process recovery
   with USB/wireless ADB disconnected and no Edge/development execution.
3. Browser visual acceptance only after the user returns space18.
4. Historical order-row account partition remains deferred. Frozen new-task
   ownership is not a historical data migration.
5. Projection ordering protects durable-to-durable delivery only. Legacy
   `/orders/screens` retains its old upsert behavior; downgrade/mixed-channel
   regressions remain a separately recorded compatibility limitation.
6. Uncertain physical navigation safely pauses; upload recovery is not a promise
   of automatic navigation recovery. Long-term background endurance remains a
   separate item, not a prerequisite to single-phone integration.
