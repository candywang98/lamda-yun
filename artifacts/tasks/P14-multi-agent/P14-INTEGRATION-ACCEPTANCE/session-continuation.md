# P14 acceptance continuation — 2026-09-10

Baseline: `bb81051`, integration branch `integration/p14-20260909`.
User authorized continued execution, parallel workers, ADB and deployment in this session. Root owns OnePlus `b0644fb5`, Seoul deployment and all runtime mutations.

## Verified runtime evidence

- API systemd WorkingDirectory is `releases/p14-bb81051`, service active, loopback health OK.
- Live PostgreSQL migration: `20260909_0015`.
- Device currently runs Companion, accessibility enabled. No live RUNNING/PAUSED/PENDING/RECONCILING runner rows returned by the queried status filter; business-state blockers require separate checks.
- Task `c1762158-a9dd-4e4e-b8d8-9c7b1bb81959`: server SUCCEEDED, recipe_pin `01a086a9-f772-7bf9-bbbb-9510b9b08c2b` / `17ab6c1089c318392950aa034b5866125787348a4d247623c5777769e4e89355`. Device inbox agrees, terminal confirmed, probe step succeeded.
- Task `74bf9edc-18b6-45d8-b06c-6fd702551d21`: server SUCCEEDED, recipe_pin `01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f` / `825921a415b7b0eaeb832ce1fb6e97847f9f981a45bb57db990491f1001ebd1f`. Device inbox agrees, terminal confirmed, probe step succeeded.
- Live catalog proves 1.0.2 published and revoked, then 1.0.1 explicitly rolled back; actor and timestamps persisted. Device active catalog now 1.0.1.
- Operator task `commandPayload.recipe` still shows the creation-time builtin snapshot; actual executed version evidence comes from server `recipe_pin` and device `payload.command.recipe`. Do not mistake the creation snapshot for the executed version.
- Android focused rerun: build successful, 45 Gradle tasks executed; XML 47 tests, zero failures/errors/skips; APK SHA `52fba6a4e335225ac7329f05f6c349cc50819077a59908ce966466becc28a2d7`.

## Browser route

Public Nginx Basic Auth is not available in the managed browser. An authenticated SSH tunnel connects loopback 18479 to existing Seoul API 8000. A loopback-only local frontend/proxy on 18480 uses the same source baseline with only API URL build configuration changed; mock mode disabled. This can validate real backend UI behavior but is not proof of public Nginx login. Ego task space 7 retained.

## Newly verified blocker and bounded correction

RecipeEngine currently logs `wait` without waiting. This prevents meaningful pending-locator pause acceptance. Root assigned isolated `agent/p14-wait-acceptance`, owned `mobile/companion/**`, to implement existing `wait` + `locatorRef` semantics: inspect approved locator until visible/enabled, bounded by recipe deadline, coroutine cancellable, with existing execution-control checks during polling. No schema/signing or third-party action changes. All non-wait actions retain current behavior. Root reviews and integrates before install.

Direct `checkpoint -> WAITING_USER` is not a valid acceptance shortcut: RecipeResumeProgress clears nextStateId on terminal transition, so persistence would throw RESUME_NO_PENDING_STATE. Do not use that graph to claim resumable pause.

## Remaining

- Verify actual running/paused old-version retention across a new publication and same-task resume.
- Verify interrupted update preserves old version on physical device.
- Finish real UI publish/rollback evidence.
- Synchronize authoritative Excel and machine work-item states without claiming complete P14 before all gates.

P15 and G3 business-side-effect acceptance remain outside this current P14 execution queue.

## Subsequent verified progress

- Web operator UI explicitly published 1.0.2 and rolled back to 1.0.1 against real Seoul API through the SSH tunnel. Phone SQLite/WAL snapshot confirmed each active version. Audit actions at 2026-09-09T16:06:10Z and 16:08:08Z prove persisted actor/time.
- Root integrated `80a5de9` (wait polling/control) and `1ca0c1a` (resume approved pending wait). Focused Android suite now 62 tests, zero failures/errors/skips; build successful. Install preserved the original device signing certificate SHA-256 `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`.
- Registered signed Companion-only acceptance version 1.0.3 as `01a086f1-af0a-7b50-840d-4e3bde44646c`, hash `0b3db8f4e273582e905929b0d1b8146f9e509cfe66289a9ebb62bb0167bd11d0`, with real signature validation unchanged.
- Task `caa22da3-8a1a-4c83-9c6e-bcba90796d80` first claimed 1.0.3, entered approved locator wait. While RUNNING, Root published 1.0.2; task pin remained 1.0.3. Pause acknowledged at 16:18:15Z. Device active stayed 1.0.3, pending held 1.0.2.
- Page-unverified resume rejected 409. First verified resume exposed inappropriate visible-target requirement for a wait; after the bounded 1ca0c1a fix and in-place APK install, same task resumed RUNNING with resumeCount=2 and original signed 1.0.3. Device journal repeated `hold:STARTED` but did not replay `started:SUCCEEDED`. Account, binding, recipe identity and approved-locator checks remain mandatory.
- Root cancelled this controlled wait after collecting evidence. Device task is TERMINAL_CONFIRMED/FAILED with CANCELLED, not falsely claimed SUCCEEDED. Deployed and active recipe restored to 1.0.1, pending null.
- `033e5ac` integrates three isolated-storage Android instrumentation tests. Build/run still in progress; no hardware fault-injection pass claimed yet.
- Raw local evidence is under `runtime-20260910/`, including SQLite/WAL snapshots, task JSON, catalog JSON and recipe audit NDJSON; do not publish raw databases.

## Final status
P14 single-device acceptance passed. `summary.md` supersedes all pending statuses in this chronological checkpoint. Real HTTPS transfer truncation and recovery were verified in addition to 3/3 hardware storage tests. Final stable task c8ec815c-bbf6-4368-94c2-822b80e37df2 SUCCEEDED with signed 1.0.1; active1.0.1, pending null. Main plan and machine queue updated 2026-09-10. Next: P09/G3.
