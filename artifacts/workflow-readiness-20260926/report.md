# Business workflow readiness, 2026-09-26

## Scope and evidence

- User requested continuing unfinished publishing, order sync, delisting and
  message sync. Current hardware scope remains three physical phones (D-11).
- Preserve receive-only and no external publish/delist/delete/price-change
  boundaries. This round does not dispatch phone tasks or install APKs.
- Baseline: `351caf2`; listing contract: `listing-sync/20260926.1`.
- Historical helper tests and `SOFTWARE_ACCEPTED` labels do not establish
  production call-chain completion. Findings below distinguish actual wiring
  from remaining reliability and hardware evidence.

## Implemented and verified

### Listing history, `b7f6623`

- Add existing row `id`, `deviceId`, `platform` to history; no migration or
  rewriting of platform identities.
- Order ties by timestamp, item key and UUID. Same item keys across three
  devices retain distinct records.
- New source/isolation and stable-pagination tests run on SQLite and isolated
  PostgreSQL: four cases. Existing listing tests also pass (seven combined).
- Platform-task + listing regression: 32 passed.
- Ruff and scoped mypy passed.

### Order checkpoint, `9cdc27e`

- Reject initial uploads that do not start at screen 1.
- A newly accepted run resets its own page/counter progress; an old page replay
  cannot reset the current run.
- New three scenarios, parametrized across SQLite/PostgreSQL: six passed.
  Before the fix, first-page gaps and cross-run counters produced four genuine
  failures; the replay test also needed a persisted checkpoint read to compare
  SQLite timestamps consistently.
- Order regression: 46 passed. Ruff and scoped mypy passed.
- This fixes only backend run counters, not durable mobile upload or recovery.

## Confirmed remaining order defects

Independent read-only audit by Bohr, cross-checked against current source:

1. `CompanionSyncService.kt`, `orderReporterFor` / `orderScreensReporterFor`:
   upload exceptions are logged, not persisted for retry. Collection can
   finish while a screen never reaches the server.
2. `LocalAutomationExecutor.execute`: clears ordinal, seen registry and page
   summaries before skipping steps up to `startAfterIndex`. Recovery can
   number a later screen as screen 1, colliding with an accepted screen.
3. `xianyu_orders.py`, `XianyuOrdersService.run`: task creation does not freeze
   account/binding identity; the reporter substitutes device ID. Tenant
   isolation is not proof of platform-account isolation.
4. Default single-screen flow uses legacy batch ingestion, which skips existing
   keys rather than refreshing status or creating an O10 collection window.
5. Multi-screen batch-then-screens double-write makes new-key statistics reflect
   database insertion order, not first observation during the collection run.

The auditor ran backend 40, Android 70 and Web 38 existing tests successfully;
additional process-local probes confirmed missing coverage. Those counts are
auditor-reported, not substituted for the controller's tests above.

Next substantive order slice needs a frozen cross-component contract:
immutable persisted screen payload/digest, separate local-read and upload-ACK
cursors, independent bounded retry, frozen binding identity, verified recovery,
and a completion marker. Network-pending must not mean synchronization complete.
Simply rethrowing upload failures cannot recover payloads already discarded.

## Listing limitations

- `artifacts/tasks/X13/summary.md` records the actual 2026-09-21 executor run:
  38 screens, 156 composite identities, task succeeded. The old task description
  saying executor wiring was missing was stale and has been corrected.
- `title|price` still merges same-title/same-price items on one device. No real
  platform identifier has been fabricated.
- `listingScreensReporterFor` also logs upload failures without durable payload
  retry. The new dispatch UI must say accepted, not fully synchronized.
- Current three-device/new-version acceptance is distinct from the old run.

## Release and UI

Web worker `453f43c` integrated as `0085d20`, shared smoke test updated in
`1986d6b`. The controller reran all 414 Web tests successfully; typecheck/build
and scoped ESLint passed. OpenAPI regenerated with no changes.

The Web slice adds fresh per-batch keys, duplicate-submit guards, immutable
selected-device snapshots, original-key unresolved-only retries, strict task-ID
validation, permission guards, visible source/filter/paging/error states and
stale-response rejection. It removes unsupported scheduling controls.
In-memory dispatch receipt state does not survive a page reload; durable
cross-reload dispatch recovery is not claimed.

Controller business regression: 157 passed across listing/platform-task, order,
maintenance, Xianyu publish, XHS publish and Douyin prepublish test files.
Focused release backend regression: 78 passed initially, then 196 passed on
`b3bd1f3` including IM classification, aggregation and migration regressions.
The combined invocation initially exposed four observer log-test failures:
Alembic `fileConfig` disabled an existing logger. The observer tests now restore
their log capture via a scoped monkeypatch; no assertion or runtime logging was
weakened. Standalone observer tests passed 7; migration-before-observer passed 17.
Fix `5df11a0` on main, `b3bd1f3` in the release.

Focused Web suite: 407 passed (main has seven additional unrelated tests).
Production typecheck/build passed using the actual API origin, dev auth false,
mock false and `/cloudctl-mobile/` base. The large-bundle warning remains.

### Cloud activation

- Release `listing-sync-b3bd1f3` active at **2026-09-26 22:39:14 +08:00**,
  based only on live `bb19ad2` plus this round's isolated changes.
- Sanitized receipt: `activation-result.json`.
- Backup: `/home/ubuntu/cloudctl-mobile/backups/listing-sync-b3bd1f3`.
  All 67 public tables restored and digests matched in an isolated database.
  Actual Web files and media archived; verification database removed.
- Exclusive deployment lock covers backup through acceptance. API admissions
  temporarily stopped and occupancy rechecked before switching. No production
  migration; revision stays `20260926_0034`.
- 156 listings unchanged; first 100 real rows verified for row/device/platform
  identity and device filtering. This is historical data from one source device,
  not new three-phone acceptance.
- Normal Basic authentication and unauthenticated rejection checked. Served
  HTML and its two entry assets match the build. Order-history read succeeds.
- IM buckets retained; `receiveOnly=true`, `mode=NOTIFICATION`. All 128 original
  messages unchanged; OUT count 23 and mobile-task count 376 unchanged.
- No APK install, actual collection dispatch, publish, delist or message send.

Deployment script:
`/home/ubuntu/cloudctl-mobile/incoming/listing-sync-b3bd1f3/cloudctl-listing-sync-deploy-20260926.py`.
SHA256 `e28575cc98ceda31ca2646329e88c63e7e002eb24064423ec5c9f31a5873a39e`.
An independent read-only rollback audit led to strengthened backup/lock,
notification-mode and rollback safeguards; final in-memory rollback tests
passed 15 cases. Hard process/machine failure is not covered by Python cleanup.

Rollback preserves data: stop API; restore Web symlink to
`/var/www/cloudctl-mobile-im-notify-bb19ad2`; remove/retire only the new drop-in
`99-zzzzzzzzzzzzz-listing-sync.conf`; daemon-reload; verify effective
WorkingDirectory and ExecStart point to `releases/im-notify-bb19ad2` before
starting. If configuration recovery fails, keep API stopped and report failure.
Never restore the database merely to roll back this no-migration release.

Production browser space 18 remains with the user; no alternate browser is used
to bypass that handoff. Component tests and HTTP asset checks do not constitute
visual browser acceptance.

## Publishing and delisting audit

Halley's read-only audit used `f0c3e4b`; no relevant source changes were made
between that baseline and this integration. Controller cross-checked the
dedicated goods and maintenance page handlers.

- `XianyuPublishGoodsView.vue:108` and `PostPublishView.vue:114`: dedicated
  create buttons record local plans, not phone tasks. This is a missing Web
  dispatch path, not a claim that no backend publish capability exists.
- `XianyuSimpleTaskView.vue:100`: local plan only. Backend
  `xianyu_maintenance_routes.py:23` already exposes the maintenance action.
  Its current contract does not accept all the page's exposure/view/want
  thresholds; explicit title targets and final approval cannot be guessed.
- XHS `BuiltinRecipes.kt:31` is open/checkpoint/WAITING_USER. Douyin business
  mint remains explicitly rejected in `test_douyin_publish_delta.py:93`.
  Planner/helper tests do not establish a production publishing pipeline.
- WeChat still depends on an externally supplied `thumbMediaId`; permanent
  cover upload/ownership/content-target association and real authorized-account
  acceptance remain separate software/external gaps (F16).
- Xianyu posts remain `AVAILABILITY_PENDING` /
  `pending_device_verification`, not a verified publishing capability.

These workflows need actual implementation beyond hardware acceptance. Do not
present them as "all implemented, only awaiting phone tests."
