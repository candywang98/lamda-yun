# Publish Queue Wiring: Controller Review

Date: 2026-09-29 (Asia/Shanghai)

## Scope

- Product delivery remains the goal. Queue creation alone is not device delivery,
  publication, or hardware acceptance.
- Current acceptance scope: at least two phones for real inbound message
  aggregation; one capable phone for pre-publication execution; one capable phone
  for screen sharing. No third-phone or physical-disconnection prerequisite.
- This work does not authorize production requests, device writes, chat sending,
  publication, account rebinding, tenant migration, or an APK installation.
- Only the existing task's designated Sol worker is used; no other chats are read
  or controlled.

## Repository Checkpoint

- Local main and verified remote main at the start:
  `0433e814f056091c8efadcf0973633a30f24f327`.
- Recoverable, unfinished four-file checkpoint:
  `5a54d84ed3a5cdbfc228c167d40d2c04db19b69c`.
- Worker branch: `agent/sol-publish-queue-20260929`.
- Worker checkout: sibling directory `sol-publish-queue-20260929`.
- The managed worktree API could not operate on the non-Git parent directory;
  the isolated worktree was created with Git after that failure.
- The initial checkpoint did not move main. A later reviewed keyboard commit is
  recorded below. No force push or reset was performed.

Protected input hashes before worker integration:

- `docs/current/tasks.json` SHA-256:
  `3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb`.
- Existing diff for mobile, preflight script/tests, scope decisions and
  three-device execution documentation SHA-256:
  `3df84dcad82739b80e4a3557e426b2137b1d8f53e99c3511ca10edb83ba51b96`.

## Verified Contracts

- `services/control-api/src/cloudctl_api/xianyu_publish.py` defines queue request
  fields, limits, response shape, and same-ID/same-payload replay semantics.
- `services/control-api/src/cloudctl_api/services.py` provides account status and
  account-device bindings. Only an unambiguous authorized Xianyu binding should
  be selected. An account read failure is not evidence that all devices vanished.
- `services/control-api/src/cloudctl_api/platform_tasks.py` generates a media
  delivery UUID when freezing a listing that has media but no delivery ID.
- `services/control-api/src/cloudctl_api/mobile_service.py` echoes the requested
  delivery ID in a manifest and separately enforces asset authorization.
  A generated delivery ID is not proof of delivery.
- The existing publication recipe stops at a human checkpoint. Mere queue
  creation does not prove that recipe was dispatched or reached that checkpoint.

## Executed Controller Checks

- `.venv/bin/python scripts/plan_guard.py docs/current/tasks.json`: exit 0,
  `valid: true`; 54 development nodes. Static plan validation only.
- `.venv/bin/pytest -q tests/integration/test_xianyu_publish_delta.py
  tests/integration/test_im_aggregation.py
  tests/integration/test_im_fleet_ownership.py`: exit 0, 58 passed in 25.34s.
  These use isolated test fixtures, not real phones.
- `git diff --check`: exit 0 before worker integration.
- `git ls-remote origin refs/heads/main`: confirms the main SHA above.

## Final Queue-Creation Integration

- Frontend commits `93cb7acd5a719b156c7b931f6370b0f0a4576f3d`,
  `da5077563fa671dc4e295b86ac6ccb5ad48e5539`, and
  `691dae81d7dfeaa66c7a6a4db9d7d053c3ed3153` are integrated. All eleven
  delivered source/test files were compared byte-for-byte with the final worker
  commit on continuation, including previously untracked test files.
- Backend permission commit `c728d7504044f699ea5392cc3358e4cd648e4ce6`
  is integrated; both delivered files match the worker commit byte-for-byte.
- Controller final verification on the integrated working tree: 608/608 Web
  tests across 48 files; Web build (including vue-tsc) passed; 10/10 isolated
  Chromium tests across desktop/mobile passed. Fixture-only screenshots were
  inspected. `final-web.json` retains the machine-readable Web result.
- Controller combined Python regression: 139/139 passed, covering publish
  permissions, recipes, queue delta, commands, platform tasks, IM aggregation,
  IM fleet ownership, and two-or-three-device preflight.
- Scope/preflight main commit: `2684993`. Relative to `0433e81`, all 108
  `dev_state` / `acceptance_state` values remain unchanged; `tasks.json` keeps
  the SHA-256 recorded above. `plan_guard` was rerun and returned `valid: true`
  with 54 nodes. `git diff --check` passed.
- These are scoped software results, not a claim that every repository CI job
  passed. No production deployment or APK installation was performed.

## Keyboard Recovery Review and Integration

- Independent Sol/high review found that both recovery buttons opened the
  settings page without first calling the existing public keyboard picker.
- Isolated worker input checkpoint:
  `0d83706bb39cf844c696a8137ebca9fde499d1e6`.
- Reviewed worker commit:
  `bf5f05ab7dfa5a13f6ac29f2791b0438bf2fda07`
  (`agent/sol-ime-picker-20260929`).
- The four-file picker-first/fallback correction was applied to the main
  working directory after an empty baseline comparison and `git apply --check`.
  `git diff --exit-code bf5f05a -- mobile/companion` then returned exit 0:
  the integrated Android source tree equals the tested worker tree.
- Main integration commit:
  `6be7009` (`fix(android): recover manual keyboard input and restore scoped IME selection`).
- Worker verification: 91 IME tests and 1,312 full Android unit tests passed;
  lint had zero errors and 19 existing warnings; debug assembly succeeded.
- Exact commands and logs:
  `../../../sol-ime-picker-20260929/artifacts/ime-picker-recovery-20260929/SUMMARY.md`
  (from the repository root's sibling worker checkout).
- The picker-first change does not alter temporary-switch cancellation recovery
  or API 30-32 readiness policy. It does not choose a keyboard automatically.
- No APK was installed and real-device typing recovery remains unverified.
- These authorized four-file corrections intentionally change the initial
  protected mobile diff hash; preflight and plan changes remain outside the write
  scope.

## Permission Gap: Confirmed in an Isolated Test

- At 2026-09-29 16:46 +08:00, the controller ran an in-memory ASGI reproduction
  using `Settings(env="test", repository_mode="memory", dev_auth_bypass=True)`.
- A legitimate test device/account was created by a test device operator. A
  subsequent viewer-role POST to `/api/v1/xianyu/publish/queues` returned 201.
  This was not a production request and did not involve a phone.
- The existing queue service lacked the permission checks already used by
  `PlatformTaskService.create`. Hiding a button is not a server authorization
  boundary.
- Frozen fix contract: queue mutation/advance requires `TASK_CREATE`; queue
  reads require `PUBLISH_READ`. Existing role definitions and schemas are not
  changed.
- Backend worker: `01a0ec59-3b09-7eb0-acd5-4142902a94ee`, requested
  `gpt-5.6-sol` / `high`, branch `agent/sol-publish-permissions-20260929`,
  baseline `6be7009`, reusing the free `sol-ime-picker-20260929` checkout.
- Web worker: `01a0ec0e-0d24-7130-83bc-1dc233f6abbc`, continuing its isolated
  publish branch, owns only the matching client gate and frontend tests.
- The controller reran the same isolated viewer reproduction after integration:
  POST now returns 403 instead of 201, with no queue created. The backend
  permission suite has 7 passing tests; the frontend also blocks a permission
  revocation occurring during asynchronous request preparation.
- The permission gap is fixed in the integrated source. It is not yet a claim
  about deployed production behavior, and no acceptance state is changed.

## Existing Online Message Page: Read-Only Check

- Existing `deployment-smoke.spec.ts --grep inbox` passed for desktop and mobile:
  2/2. The harness blocks non-GET/HEAD API requests, uses existing authentication,
  and disables tracing of credentials.
- Current deployed app only, not the new unpublished frontend patch.
- The inspected user-message tab showed the existing September 26 VOG record.
  This is not evidence of two fresh inbound device events for this delivery.
- Private screenshots stay under `/tmp/cloudctl-im-readonly-20260929/`; they are
  not committed to Git or treated as new hardware acceptance.
- The current two-or-three-device preflight unit suite was rerun: 36/36 passed.

## Remaining Product Evidence

- Two real phones feeding the same message aggregation page with source
  separation and duplicate handling.
- One authorized phone receiving the product task, stopping before external
  publication, and reporting the same target/result to the Web.
- One phone providing an authorized live screen and a verified end/handoff.
- GitHub synchronization and deployment verification for any subsequently
  approved release are separate from local software tests.
- No `dev_state` or `acceptance_state` transition is authorized by this report.
