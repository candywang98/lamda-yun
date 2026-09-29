# Feature-Scoped Device Readiness: Controller Evidence

Date: 2026-09-29 (Asia/Shanghai)
Reviewed source: `c7bde6b9745a623068e9f02f4b6af110098405db`.

## Scope and Authority

Only OnePlus 9R `b0644fb5` and Huawei VOG `APH0219624006517` were queried.
No phone input, settings change, installation, account binding, tenant change,
business send, upload, publication or deployment was performed. ELE and
unselected phones were not queried. ADB was used for optional diagnostics,
not as a business execution path or a physical-disconnection gate.

Two phones are required for fresh inbound aggregation. Product execution
stopping before publication and live-screen/end-handoff each require one
capable phone. Software evidence does not satisfy those hardware checks.

## Current Phone Evidence

The existing preflight was run once with the two exact serials and a four-second
per-command timeout. It exited 1, reporting `UNKNOWN` accessibility details:
9R had a label-only Bound entry and VOG had an unsupported section shape.
Separate read-only `dumpsys activity services com.company.cloudctl.companion`
then showed, on both phones:

- An exact user-0 `CloudCtlAccessibilityService` ServiceRecord.
- A matching Companion process and `hasBound=true`.
- A foreground `CompanionSyncService`.

This independent evidence resolves the binding identity at observation time;
it does not change the parser output, prove end-to-end ingestion or establish
long-term service health.

| Item | OnePlus 9R | Huawei VOG |
| --- | --- | --- |
| Installed version | 6 / `0.1.0-business-acceptance.6` | 1 / `0.1.0` |
| Process | Running | Running |
| Package disabled/stopped | false / false | false / false |
| Default IME | Sogou | `com.company.cloudctl.companion/.ime.CloudCtlInputMethod` |
| Other normal IMEs enabled | Sogou | Huawei, Baidu Huawei and iFlytek |

The VOG default IME is a concrete manual-input diagnostic finding. The
repository's pre-`6be7009` IME renders an invisible zero-size input view, and
`6be7009` adds a user recovery control and scoped selection restoration.
The installed VOG executable was not decompiled or behaviorally tested here;
its selected IME is not, by itself, proof of all reported input symptoms.
No keyboard was switched and recovery is not marked verified.

## Cloud Snapshot

At `2026-09-29T10:47:46.256398Z`, the reviewed read-only snapshot ran inside a
repeatable-read, read-only PostgreSQL transaction and used authenticated GET
requests for operator IM configuration.

- Both selected devices remain in the same original tenant and retain their
  expected active mobile bindings.
- 9R last activity: `2026-09-29T10:47:44.882140Z`, version v6, runner `IDLE`,
  safety barrier `NONE`, one bound Xianyu account.
- VOG last activity: `2026-09-26T18:02:43.144852Z`, version v1, no account-device
  binding. Its old capability fields are stale, not fresh health proof.
- Both operator IM reads returned HTTP 200, `receiveOnly=true`,
  `mode=NOTIFICATION`, `enabled=true`.
- Occupancy: zero active leases, nonterminal tasks, schedules, previews and
  debug sessions. Historical task count 379 and OUT-message count 23.
- The observed API WorkingDirectory and ExecStart remain
  `order-delivery-557f547`; current main has not been deployed.

No platform-account binding was created. Source IM ingestion authenticates the
mobile binding and scopes messages by tenant/device; this investigation does
not treat zero platform-account bindings as permission to rebind or as proof
that all inbound IM paths are unusable.

## VOG TLS Failure: Direct Process Evidence

At `2026-09-29T11:26:47.926Z`, the exact current Companion PID was 6103.
A bounded read of its last 800 log lines found four TLS-exception matches,
zero successful-heartbeat matches and zero network-unreachable matches.
The follow-up bounded exception-only read identified:

```text
SSLHandshakeException:
java.lang.IllegalStateException: Cloud certificate fingerprint mismatch
```

The same reason appears as a `CertificateException`. Selected exception
timestamps were Unix epochs `1790681059.097`, `1790681111.052`,
`1790681172.041` and `1790681223.946`. No raw device log, customer content,
binding token or credentials are stored in this evidence.

This establishes a current certificate-fingerprint failure in that process.
It does not authorize disabling TLS checks, rolling back server certificates,
or changing enrollment.

## VOG Installed Signature: Unknown Resolved to Mismatch

`pm path` returned exactly one installed base APK. Reading its SHA-256 on the
phone produced:

```text
2f424419719490f237784ae876d3f57f03d04e7455ffa8df1a4710fc686f5f2b
```

This exactly matches the 64,618,590-byte retained local VOG APK in the private
`20260929-two-device-readonly/20260929T040140Z` evidence directory. No repeat APK
pull was necessary. A fresh `apksigner verify --print-certs` on that exact
retained APK succeeded and reported signer certificate SHA-256:

```text
667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736
```

A fresh verification of the retained OnePlus business-acceptance v6 candidate
reported:

```text
67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796
```

Therefore the existing OnePlus candidate is not a signature-matching VOG
in-place update candidate. Preserve the VOG installation and enrollment;
identify the original signing material and build an independently verified
compatible candidate before proposing any installation window. Do not
uninstall, clear data, replace identity or guess a signing key.

### Original Signing Material Located

Read-only public-certificate inspection of the two existing local Android
debug keystores produced:

- The existing `CloudCtlExternal/android-user-home` store matches the OnePlus
  signer `67a6d9af...a57796`.
- The existing default Android-user-home store matches the VOG signer
  `667ebabbd...b4736` exactly.

Only `keytool -list` certificate metadata was read. No private key was
exported, copied, generated, modified or used to sign a new artifact in this
diagnostic step. The matching store removes the unknown-key prerequisite
for preparing a VOG-specific candidate; it does not make the existing
OnePlus APK compatible and does not authorize installation.

The earlier retained staged-session query was uninterpretable (`RC_255`).
It remains `UNKNOWN`, not evidence that no staged installation exists.
At `2026-09-29T12:12:18.713Z`, a bounded `pm help` read also returned 255
while printing help normally. Its session-related help documents staged
session creation but no staged-session listing command. Therefore exit 255
alone is not a session inventory or proof of an empty queue. No session was
created, committed, abandoned or otherwise modified.

## Remote CI and Executable Next Work

GitHub run `36556566588` for the reviewed source completed:

- Frontend: success.
- Python: 22 failed, 1361 passed, 171 skipped, 42 setup errors.
- Android: failed at the explicit missing-public-update-key gate.

Controller source/log review identified:

- Nineteen device-lock failures reject the literal Linux `stat` output
  `ext2/ext3`, although individual ext2 and ext3 names are already allowed.
- Two fake installer tests hard-code a macOS home directory.
- Forty-two Q02 fixture failures cannot prove ancestry with the CI's explicit
  `fetch --depth=1`; the same expected ancestor check passes in the full local
  history. Keep the ancestry guard and supply the required history.
- One load test completed 12/20 tasks with an empty error list. Eight controller
  repetitions of the exact local node all passed; a deterministic reproduction
  and transaction-isolation investigation are still required.

The two disjoint Sol/high work items delivered these commits from the frozen
source:

- `1db1858de4c570bc66615e179376d467bdbda6ab`: exact local-filesystem alias,
  portable test paths, full Python checkout history and regression tests.
- `cb6a5bfdf732e21bbe4388af9984d972294deee9`: validate existing PostgreSQL
  test binaries before exporting their directory; report actual pytest skip
  reasons. No installation, server start or weakened skip/gate behavior.
- `2ca5b7933257a350381fa97926f9ea8f0c3cb31c`: isolated file-backed SQLite
  load fixture, durable-state diagnostics and focused regressions.

Controller integrated them without conflicts at
`eb1eedccef0e4dd3325c1d5be4d7e154d3d1543b`. The 200 initial focused ops
tests passed on main before the follow-up integrations. At the integrated SHA,
Ruff lint and formatting (712 files), raw configured Mypy (162 source files),
raw Pyright and security-boundary checks passed. Full Python verification is
complete: `pytest -q -rs -p no:cacheprovider` returned 0 with **1624 passed,
14 skipped in 311.92 seconds**. Five skips require separate PostgreSQL
row-lock/visibility fixtures and nine require controlled hardware; these are
not marked accepted. All integrated software scenarios, including the new
isolation regressions, passed.

Normal `git push origin main` advanced the remote from `c7bde6b` to
`eb1eedc`; a subsequent `git ls-remote` confirmed the exact SHA. Hosted run
`36564799780` completed with these results:

- Frontend job `109393998824`: success, including 624 Web and 16 Studio tests.
- Python job `109393998994`: format/lint/type gates, PostgreSQL discovery and
  pytest all succeeded. The actual runner paths were
  `/usr/lib/postgresql/16/bin/initdb`, `pg_ctl`, and `createdb`.
  Pytest reported **1624 passed, 14 skipped in 372.71 seconds**. Skip reasons
  now match the local set; the earlier 171-skip gap did not recur in this run.
- The Python job then failed at its final direct invocation of
  `scripts/check-security-boundaries.sh`: `Permission denied`, exit 126.
  Git records that script as mode `100644`. This is an invocation failure,
  not a failing security finding and not a passing complete Python job.
  The same script had passed when explicitly invoked using Bash locally.
- Android job `109393999218`: failed at the unchanged required-public-update-
  key gate, before checkout or any Gradle task.

The controller assigned Sol/high a separate minimal follow-up to invoke the
unchanged security script explicitly with Bash, with executable positive and
negative fixture tests. No security rule or file permission is to be weakened.
No public-key configuration was changed or replaced with test material.

Controller independently ran the two isolation regressions with the frozen
old harness loaded only in that test process. Both failed in 0.66 seconds:
claim observed/final states were `CLAIMED/QUEUED`, and completion states were
`SUCCEEDED/CLAIMED`, despite HTTP 200. This confirms the fixture's dirty
visibility and cross-session rollback defect, not the precise remote 12/20
failure sequence and not a production PostgreSQL defect.

The earlier Sol quota failure is historical. Both deliveries above were
executed after the retry recovered; no alternate execution model was selected.

All task-ledger states remain unchanged. The next real acceptance step is
gated by the specific VOG connection/signing issue and an authorized deployment
or device window, not by a third phone or physical cable removal.

## Additional Bounded Read-Only Checks

At `2026-09-29T11:43:31.382Z`, a new public TLS handshake using default CA and
hostname verification returned the exact frozen successor
`f2a9423e27fd8d6cdcd00d76e9da8918a402e118fe52656b84342dda6fb40725`.
Its validity remains `2026-09-27T06:21:32Z` through
`2026-12-26T06:21:31Z`. This verifies the present server leaf, not the old
installed VOG application's recovery.

At `2026-09-29T11:51:52Z`, exact-serial reads of
`enabled_notification_listeners` found no Companion entry on either selected
phone. This is NOT a new readiness failure: the source registers and handles
`AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED` in
`CloudCtlAccessibilityService`, rather than declaring a separate
`NotificationListenerService`. No notification-listener setting was changed,
and this diagnostic does not substitute for fresh real-message ingestion.

## VOG Candidate Preparation

The controller assigned the same Sol/high worker a new bounded work item from
integrated SHA `eb1eedccef0e4dd3325c1d5be4d7e154d3d1543b`, reusing its
clean worktree on `agent/sol-vog-recovery-v7-20260929`.

Approved source scope is only the business-acceptance version bump to 7 and
its matching variant assertions, plus candidate evidence. The build must use
the existing VOG-matching signing store, preserve all identity/trust/runtime
flags, and verify the final APK signature, manifest, clean source revision
and full debug/business-acceptance tests. The normal external build wrapper
cannot be used because it forces the different OnePlus signing home.

This is local candidate preparation, not installation, deployment, production
release, keyboard recovery or device acceptance. No real send/publish/upload
or account/tenant mutation is authorized.

### Independently Checked Candidate

The approved version-only source commit is
`226eff2ff472459603af9c6e4a01f4e92dce7ebd`, now fast-forwarded into local
main. It changes two version fields and their two variant assertions only.
The worker's direct offline Gradle build completed successfully in 3m37s,
with 99 tasks executed.

Controller read-back of the generated JUnit XML found:

- Debug: 175 suites, 1312 tests, zero failures/errors/skips.
- Business acceptance: 175 suites, 1298 tests, zero failures/errors/skips.
- Both include passing pin-policy, IME-availability and temporary-IME-switch
  tests. Variant lint and assembly also completed successfully.

Controller separately ran `apksigner verify --verbose --print-certs`,
`aapt2 dump badging` and `shasum -a 256` on the actual final candidate:

- Path: `/Users/wangziheng/CloudCtlExternal/acceptance/20260929-vog-v7/cloudctl-vog-recovery-v7.apk`.
- SHA256: `57f5f444566fdd3878db036eadb70f130d067092a231a4320f8bade39b6bfcb0`.
- APK Signature Scheme v2 verifies with the exact original VOG signer
  `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`.
- Package: `com.company.cloudctl.companion`, versionCode 7,
  versionName `0.1.0-business-acceptance.7`, minSdk 29, targetSdk 35.
- DEX contains clean source marker `226eff2`; the decoded APK BuildConfig
  also has `DEBUG=false`, `HEARTBEAT_DIAGNOSTIC=false` and
  `IM_UPLOAD_HOLD_ALLOWED=false`.

This candidate deliberately retains the existing controlled-acceptance update
trust. Its matching Android APK signer is distinct from the owner-controlled
release-update public key required by CI. It is not a production release.
No installed package, input method, binding, tenant or device task changed.

## Final Local Integration Checkpoint

VOG evidence commit `7b3b115d8d8d31bf4fb2006ce286809072de9a70` and the
security-entry repair `dc11a670c882fa81fdd94acee27174427f4c8a5d` are
integrated at `fbbf5ebcc5565a41f89c5323c63c63119ac92f9e`.
The latter changes one workflow invocation, its exact assertion, two
executable regression cases and the scoped evidence only. The original guard
contents and mode remain unchanged.

Controller re-verification on integrated main:

- Workflow and release-key regression files: **21 passed in 3.16s**, exit 0.
- Exact new `bash scripts/check-security-boundaries.sh`: passed, exit 0.
- Ruff lint and format: passed, 714 files already formatted.
- `plan_guard`: valid, 54 nodes.
- All 108 development/acceptance state fields equal `0433e81`.
- Task-ledger SHA256 remains
  `3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb`.

The broad local and hosted Python counts above apply to their explicitly
named integration SHA. The final source adds only the independently tested
Android version/candidate and security-entry changes plus evidence. A fresh
hosted run after the next normal main push is still required to verify its
complete Python job. Android release CI remains separately gated by the
owner-controlled update public key. No installation or deployment is
authorized or claimed by this checkpoint.
