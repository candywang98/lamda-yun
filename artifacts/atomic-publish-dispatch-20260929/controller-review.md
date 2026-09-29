# Atomic Publish Dispatch: Controller Review

Date: 2026-09-29 (Asia/Shanghai)

## Frozen Baseline and Scope

- Local main and remote main independently read back at
  `7ee8424043f3f67e73f5284b4e4ff6a595a7ff8c`.
- The tracked main worktree was clean. Existing untracked artifacts are
  preserved and excluded from integration commits.
- Two existing, isolated worker checkouts continue from this same baseline,
  using `gpt-5.6-sol` with `high` reasoning effort:
  - `agent/sol-atomic-dispatch-20260929`: mobile insertion, platform snapshot
    stamping, queue dispatch, focused regression tests and worker evidence.
  - `agent/sol-ci-python-20260929`: seven existing Python formatting failures,
    Android CI public-key configuration entry, focused workflow tests and
    the owner-facing runbook.
- The controller owns this evidence, review, integration and normal main push.
  No other conversation is read, controlled or messaged.

## Reviewed Failure and Required Proof

The baseline queue dispatch holds queue locks but calls platform task creation,
which commits mobile insertion and snapshot stamping independently. A queue
failure can therefore leave an independently visible task.

The new dispatch path must commit the task, complete immutable command
snapshot, completion boundary, queue link and dispatch audit in one database
transaction. Separate PostgreSQL sessions must see no claimable partial task
before commit. Injected failures before commit must leave no new task, link or
dispatch audit. Response loss after commit must replay the same task.

Review must also verify:

- Serial order is enforced at dispatch under concurrent requests.
- Historical orphan recovery preserves started/paused state, remote control,
  result, snapshot and hash; malformed historical records are rejected.
- Existing device/account/media validation, tenant isolation, lease/fencing,
  idempotency, scheduling and order-collection paths remain covered.
- No HTTP schema, database migration, generated contract or task-state change.
- No security-gate bypass, generated release key or dependency exclusion.

## Baseline CI: Confirmed Outcomes

GitHub Actions run `36551786225` for `7ee8424` completed:

- Frontend job `109351440119`: success.
- Python job `109351440115`: failure at `ruff format --check .`; subsequent
  Python checks did not run.
- Android job `109351440672`: failure in Companion `./gradlew lint test`;
  DPC checks did not run.

Authenticated read-only retrieval of the Android job log confirmed
`:app:verifyReleaseUpdatePublicKey FAILED` and the missing
`CLOUDCTL_APP_UPDATE_PUBLIC_KEY` / `cloudctl.appUpdatePublicKey` diagnostic.
No credential is printed or stored here.

Repository Actions variables returned HTTP 200 with `total_count: 0`.
The proposed CI configuration entry is not the controlled public key itself.
The owner must supply and verify that key; test trust or a newly manufactured
key must not substitute for the production update trust root.

## Acceptance Boundary

Software tests do not establish phone acceptance. The remaining real evidence
is new inbound aggregation from at least two eligible phones, a product task
stopping before publication on one capable phone, and live screen/termination
or handoff on one capable phone. The latter two may use the same phone.

No third-phone, all-connected-device or physical-disconnection gate applies.
ELE `GBGDU19830002425` and additional unselected phones remain excluded.
No deployment, APK installation, phone setting change, account rebinding,
tenant migration, real send, publication, upload or business write occurs in
this software work item.

## Integration Results

- CI delivery `bd62e6f`, guard-test follow-up `6dec1ec` and corrective
  `cece278` were fast-forwarded in sequence. The final two transport import
  lines are unchanged from the baseline.
- Atomic delivery `4d687c3` and replay correction `12f8f47` were cherry-picked
  as `2954594` and `8437a0c`. No ownership conflict, schema change, migration
  or generated-client change occurred.
- Controller verification used the integrated source
  `8437a0c42ff6f4aef5301626fcd616269884ac64`.
- This turn made software implementation progress. It is not a hardware
  acceptance result, release-key configuration or production deployment.

## Controller Review Findings

- The CI branch was integrated first by fast-forward to `6dec1ec`, because its
  write set is independent of atomic dispatch. Nothing was pushed at this
  intermediate revision.
- Controller AST comparison of the seven formatted files against `7ee8424`
  confirmed 7/7 unchanged. The operational scripts were not executed.
- Intermediate main checks passed global Ruff formatting (705 local files),
  Ruff lint, Pyright, 152 focused fake-only operations/CI tests and the security
  boundary script.
- The exact raw CI command `.venv/bin/mypy` failed at both
  `fleet_live_transport` imports after the CI worker removed their
  `import-untyped` ignores. The worker's explicit `MYPYPATH` changes import
  discovery and is not equivalent to raw CI. Restoring the original comments
  was assigned to the same worker; packaging and checker exclusions must not
  be changed to hide this environment mismatch.
- Atomic candidate `4d687c3` passed its reported 17 dispatch tests, but final
  source review found `recheck_after_device_lock` guarded the initial lookup
  rather than the repeat lookup. Ordinary direct replay would therefore
  acquire a device lock before finding its existing task. Integration was held
  for the original always-first lookup, conditional post-lock repeat lookup,
  and a real PostgreSQL regression with the device row held by another session.
- A separate controller finding, caller-owned flush `IntegrityError` mapping,
  was already fixed in `4d687c3`. Its PostgreSQL constraint-failure test proves
  HTTP 409 and rollback without querying an aborted session or opening a
  replacement transaction.

These review findings supersede any earlier worker interpretation of raw CI
equivalence or unchanged direct replay behavior. Final outcomes follow only
after the corrective commits and controller reruns.

## Final Controller Verification

Commands ran from the main checkout without worker `MYPYPATH` overrides.
The local Python version is 3.13.5; GitHub CI uses 3.12, so remote results must
be observed separately.

| Command | Exit | Result |
| --- | ---: | --- |
| `.venv/bin/pytest -q -rs` | 0 | 1582 passed, 14 skipped in 270.53 seconds |
| `.venv/bin/ruff format --check .` | 0 | 706 local files already formatted |
| `.venv/bin/ruff check .` | 0 | All checks passed |
| `.venv/bin/mypy` | 0 | No issues in 162 source files |
| `.venv/bin/pyright` | 0 | 0 errors, 0 warnings, 0 information |
| `bash scripts/check-security-boundaries.sh` | 0 | Security boundary checks passed |
| `git diff --check 7ee8424 HEAD` | 0 | No whitespace errors |
| `env VITE_CONTROL_API_URL= VITE_CONTROL_API_DEV_AUTH=false VITE_OPERATIONS_MOCK_ENABLED=false pnpm test` | 0 | Web 624/624, Studio 16/16, contract type check passed |
| `.venv/bin/python scripts/plan_guard.py docs/current/tasks.json` | 0 | Valid, 54 nodes |
| Structured state comparison against `0433e81` | 0 | All 108 development/acceptance fields unchanged |
| `git merge-base --is-ancestor 0433e814f056091c8efadcf0973633a30f24f327 HEAD` | 0 | Requested plan revision is already included |

The 14 skips are explicit:

- Nine require controlled real devices: four controlled-fault scenarios,
  three two-device runtime scenarios and two Q02 device scenarios.
- Five are SQLite variants requiring PostgreSQL cross-connection visibility
  or row locks. The suite also ran their PostgreSQL variants where provided.
- No atomic-dispatch test was skipped. Its disposable PostgreSQL cluster and
  separate application connections ran in this integrated full-suite check.

`docs/current/tasks.json` remains byte-identical with SHA-256
`3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb`.
The frontend emitted existing localStorage/router warnings but no failure.
Pyright printed an update notice; no dependency was changed.

## Delivery Boundary and Next Action

The controller will normally push this reviewed source and evidence to main,
then read back the remote SHA and the new GitHub Actions run. Local checks
alone do not establish remote CI success. Android remains blocked unless the
release owner configures the verified production public update key; this turn
does not modify GitHub variables or substitute test trust.

Next delivery work is a scoped deployment/acceptance window, not another
all-phone sweep: check the chosen devices' identity and readiness read-only,
retain any specific blocker, then request only the missing authority or
configuration needed for two-phone fresh inbound aggregation and one-phone
pre-publication execution/live-screen evidence. Current keyboard recovery
source is still not proof of installed-phone input recovery.

No task development/acceptance state is promoted. Existing untracked artifacts
are preserved, and only the declared source/evidence files enter the commits.
