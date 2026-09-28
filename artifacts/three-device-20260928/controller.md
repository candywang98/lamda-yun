# Three-Device Controller Evidence

## Scope

User confirmed OnePlus9R `b0644fb5`, OnePlus7 `15faee1d`, and Huawei VOG
`APH0219624006517`; software work uses GPT-5.6 Sol with High reasoning.
No three-device business acceptance is claimed.

## 2026-09-28 Observations

- All three exact serials enumerate as ADB `device`.
- OnePlus9R: business acceptance v3. Its process was absent and accessibility
  listed as enabled but not Bound, with its component under Crashed services.
  Process exit history records a system kill on 2026-09-27 23:19 local time;
  it does not identify the underlying OEM policy.
- OnePlus7: old 0.1.0, disabled and stopped, no active accessibility service.
  Its saved binding matches an active server binding in the original test
  tenant, not the production tenant. No migration or enabling was attempted.
- Huawei: old 0.1.0. Exact accessibility service process/connection is present
  in `dumpsys activity services`. Its current saved binding differs from the
  2026-09-23 historical record. The actual current binding is active in the
  production tenant, but has no platform-account binding.
- Cloud read-only checks at 12:14, 12:22 and 12:23 UTC: schema 0035, 379 tasks,
  23 outgoing messages; no live task, lease, schedule, preview or debug session.
  Authenticated IM config reads retain receiveOnly=true / NOTIFICATION for all
  three requested device identities.

## OnePlus Launch Diagnostic

At 12:23:12 UTC, under local exact-serial device lock fencing13, one normal
`adb shell am start -W -n com.company.cloudctl.companion/.MainActivity` restored
the Companion process and foreground sync service. The lock was released in
the same diagnostic window. No force-stop, tap, swipe, settings modification,
installation, data clearing, rebind or business task was performed.

Accessibility remained unbound and the cloud heartbeat did not advance.
Subsequent logs on BOTH OnePlus9R and Huawei explicitly show a validated
network followed by `Cloud certificate fingerprint mismatch`.

## New P0: Certificate Transition

Public TLS verified using the host's default CA/hostname trust and a separate
authenticated SSH read of the server certificate agree on SHA256
`f2a9423e27fd8d6cdcd00d76e9da8918a402e118fe52656b84342dda6fb40725`.
The saved Huawei/OnePlus7 pin and retained server certificate7 instead equal
`fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1`.
See the [frozen transition contract](../../contracts/phase1/cloud-pin-transition-20260928.md).
No TLS rollback, bypass, private-key access or phone trust mutation occurred.

## Software Checks

The repeated Android order-delivery JUnit result is 35 tests, 0 failures,
0 errors, 0 skipped, timestamp 2026-09-28T12:15:33.
The interrupted command session handle no longer existed when resumed, so
this report relies on its resulting JUnit XML rather than claiming an observed
process exit code for that repeat. The preceding run's exit0 remains recorded
in the conversation.

First Sol preflight delivery: `de2b6d9`, 24 mocked tests; controller requested
additional fail-closed handling before integration.
The legacy-guard Sol task encountered provider quota failure and was resumed
at the user's explicit request. Partial work is preserved in its worktree.

## Controller Integration And Recheck

The resumed legacy guard completed as `5948e57`, reviewed and integrated as
`944c773`. The controller reran the following on the main integration tree:

```text
.venv/bin/python -m pytest -q -rs tests/integration/test_order_legacy_guard.py tests/integration/test_fleet_orders_pagination.py tests/integration/test_order_checkpoint_runs.py tests/integration/test_order_delivery.py tests/integration/test_orders_sync.py
```

Exit 0: 115 passed, 3 skipped in 39.88 seconds. The skips are the SQLite
parameters of the three PostgreSQL row-lock cases; the PostgreSQL parameters
passed against a disposable local cluster, not production.

The preflight worker and its fail-closed review fixes are integrated as
`97d2b6e` and `6db4900`. Controller rerun:
`.venv/bin/python -m pytest -q tests/ops/test_three_device_preflight.py`,
exit 0, 29 passed. Ruff for both packages' production and test files exited 0.

At 12:37:15 UTC, a fresh cloud read still reports 379 tasks, 23 OUT messages,
schema 0035 and zero active lease/task/schedule/preview/debug occupancy.
All expected mobile bindings remain active; Huawei has no platform account
binding and OnePlus7 remains in its original test tenant.

The repeated three-serial ADB preflight exited 1 as intended: all three are
authorized, but OnePlus9R accessibility is still crashed/not bound, OnePlus7
is disabled/stopped, and Huawei's accessibility output remains UNKNOWN to
the generic parser. No cloud-online or device-ready claim follows.

No deployment, APK installation, tenant/account change, or business task was
performed during this integration/recheck. The certificate worker retains
the exclusive Gradle slot until its delivery.

## Certificate Integration And V4 Build

Worker C delivered `5c01340`, integrated as `7e2d985`. The controller took the
Gradle slot after the worker completed. Version preparation is `2853e6d`;
the version-specific test assertion and public TLS probe are `d200dc2`.

The first controller combined build exited 1: the business-acceptance identity
test still required versionCode 3. It ran 1280 business-acceptance tests with
one failure. Only its explicit expected version/name was changed to v4; none
of its identity or security assertions was removed.

The repeated command from `mobile/companion` was:

```text
env JAVA_TOOL_OPTIONS=-Drobolectric.dependency.repo.url=file:///Users/wangziheng/.m2/repository ./build-external.sh --offline --no-daemon --console=plain :app:testDebugUnitTest :app:testBusinessAcceptanceUnitTest :app:assembleBusinessAcceptance
```

Exit 0, BUILD SUCCESSFUL in 1m50s. JUnit XML totals:

| Variant | Suites | Tests | Failures / Errors / Skips | UTC timestamps |
| --- | --- | --- | --- | --- |
| debug | 174 | 1294 | 0 / 0 / 0 | 12:50:48 through 12:51:15 |
| businessAcceptance | 174 | 1280 | 0 / 0 / 0 | 12:51:17 through 12:51:39 |

Vital lint and assembly completed. These results do not cover the worker's
separately recorded three heartbeat-diagnostic IM intake failures, formal
release-public-key gate, or whole-repository remote CI.

V4 artifact:

- Application: `com.company.cloudctl.companion`.
- VersionCode 4, name `0.1.0-business-acceptance.4`.
- Source revision embedded in the APK: `d200dc2-dirty`. Existing untracked
  historical artifacts make the full workspace dirty; no clean-tree claim.
- DEBUG, HEARTBEAT_DIAGNOSTIC and IM_UPLOAD_HOLD_ALLOWED are all false.
- APK SHA256:
  `cff3b03a72f56781a73d2713bd68a968f1d47a6c21f27c528629f72f6e9fcf70`.
- `apksigner verify --print-certs` exited 0; signer SHA256:
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`.
- The freshly pulled OnePlus9R v3 has the same signer and SHA256
  `c6a39272612bf507c70d0a5f3084162b87770d445fcecedb4e659be5cd4a9005`.
- Both APKs are retained under the controller's private
  `CloudCtlExternal/acceptance/20260928-v4` directory, not committed.

The Huawei/OnePlus7 read-only APK pulls stalled and were interrupted with
SIGINT (exit 130) after approximately two minutes. The partial files are
not valid backups and were not used for signing checks. Their exact signer
compatibility remains unverified; no ADB server/device restart was attempted.

At 12:49:01 UTC, `CloudPinProbe.java` ran with the actual compiled
businessAcceptance Kotlin classes and Kotlin stdlib 2.1.0 on Java 17:
default CA plus hostname verification succeeded; the leaf matched the frozen
successor; both exact-current-pin and old-pin transition checks succeeded;
wrong host, absent host and unknown configured pin were rejected. A second
TLS connection using the compiled PinnedTrustManager with the old pin returned
HTTP 200 from the public read-only `/health/ready` endpoint. Exit 0.

This probe used no credentials and no phone; it is not mobile runtime,
WebSocket, queue-recovery or disconnected-operation evidence.

## Focused Backend Candidate

Worker B's read-only review found no new runtime dependency for overlaying
the current `fleet_orders.py` onto deployed `557f547`, with existing schema
0035 as a hard prerequisite. The controller constructed that exact candidate
in a temporary extracted source tree, not by deploying all of main.

All 202 tracked Python runtime files under services/packages/edge were compared
against the base archive: only `services/control-api/src/cloudctl_api/fleet_orders.py`
differs; none is missing. Its SHA256 is
`40518bf4b4eaaeca38c341e188ce235901e4ab351b0c83569e1f32381ba1e88a`.
The five-file order test command above, with the added regression test as test
input only, exited 0: 115 passed, 3 SQLite-only skips in 41.93 seconds.

This candidate has not been uploaded, activated or deployed. Production API
remains `order-delivery-557f547`; no production service was restarted.

## Authorized OnePlus V4 Installation

The user explicitly confirmed the free-device window and the data-preserving
in-place v4 update. At 14:08 UTC all cloud occupancy checks were empty,
maintenance was false/version8, and the original binding was active. Local
lock was FREE and no scrcpy/LAMDA writer was observed.

`install-oneplus-v4.py --approved-idle-window` exited 0:

- Exact serial `b0644fb5`, model LE2100, Android user0; fencing14.
- Server-side private identity snapshot retained the binding credential digest,
  app instance and account binding for comparison; none is printed or committed.
- Maintenance changed false/version8 to true/version9 through the normal
  expectedVersion-checked operator API.
- One `adb install -r` ran from 14:13:58.755583 to 14:14:02.425942 UTC.
- Pulled installed v3 and v4 signatures and APK hashes matched the frozen values.
- All 12 permission entries, four secure settings, UID and first-install times
  matched. No uninstall, data clearing, explicit force-stop or permission write.
  PackageManager recorded its normal PACKAGE UPDATED process exit; this was
  not a controller-issued `am force-stop`.
- The non-debuggable phone's private SQLite data was not read; no byte-for-byte
  preservation claim is made.
- Original binding/credential/account identity remained unchanged; task379,
  OUT23, device order14 and receipt6 counts remained unchanged.
- Maintenance restored false/version10 and fencing14 released at 14:14:09Z.

Public summaries: `v4-install-summary.json`, `v4-cloud-after-install.json`.
Raw APK/package/settings backups remain in private local storage; the cloud
identity snapshot stays in the server's private backup directory.

## Post-Install Maintenance Failure And Recovery

The automatic v4 start sent a successful heartbeat at 14:14:04Z. However,
follow-up cloud reads at 14:15:39Z still had the same last_seen timestamp;
the exact accessibility component remained bound in process23518 while
CompanionSyncService was absent.

Server journal confirms `/companion/v2/devices/heartbeat` HTTP200 followed by
`/companion/v2/tasks/claim` HTTP409 during the maintenance window. Source
`CompanionSyncService.syncLoop` stops the whole service on non-retryable HTTP
errors, and CloudHttpException treats 409 as non-retryable. This is a separate
maintenance-recovery defect, not a continued TLS failure. The detailed
maintenance response was not captured on-device; its exact detail is verified
from the deployed server implementation and the active maintenance state.

Under fencing15 and fresh cloud idle checks, `resume-oneplus-v4.py` issued one
normal MainActivity launch at 14:19:40.868191Z. No maintenance/identity mutation
or business task was performed. Phone logs show Heartbeat successful at:

- 14:19:42.586Z
- 14:20:03.511Z
- 14:20:24.674Z
- 14:20:46.483Z

Exact service inspection showed foreground CompanionSyncService and
CloudCtlAccessibilityService with `requested=true received=true hasBound=true`
in process23518. The generic accessibility parser reported label ambiguity,
not failure of this exact-component observation.

`v4-recovery-summary.json` records three distinct fresh cloud activity samples.
Its field name was corrected from the initial private output's
`distinctFreshHeartbeats`: authentication of other requests also advances
last_seen, so only the separate phone log events above prove heartbeat count.

At 14:21:45Z the cloud was still idle, the latest authenticated activity was
14:21:43Z, maintenance false/version10, original identities unchanged, and
counts remained task379/OUT23/order14/receipt6. Fencing15 was released at
14:20:07Z; a subsequent independent lock status read confirmed FREE.

These are connected diagnostic results with one ADB normal launch after
installation, not automatic maintenance recovery, long-duration background
stability, fault-injection or disconnected business acceptance.
Sol High's bounded fix is frozen in
`contracts/phase1/claim-maintenance-recovery-20260928.md`, baseline `29c4820`.

## Remaining Gates

Certificate-compatible APK and signature checks, OnePlus accessibility recovery,
OnePlus7 tenant disposition, Huawei account binding, actual device collections,
network/process fault cases and final disconnected acceptance remain pending.
Synthetic tests and ADB connectivity do not satisfy those gates.
