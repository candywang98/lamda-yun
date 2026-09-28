# Worker: V5 Business-Acceptance Candidate

## Delivery

- Baseline: `f45f5d29360b721ccbf0265e0b4291c96d91600d`.
- Integrated maintenance fix: `19da0d82c163d4720042362ad1b5d208e321cf6f`.
- Branch: `agent/sol-v5-candidate-20260928`.
- Candidate source commit: `a3eb41928c6b4f654d2c441f44aab5a483bb59bd`.
- Final evidence commit: reported at handoff because this file is part of it.
- This is a business-acceptance candidate, not a formal production release.
- No ADB, SSH, phone, install, deployment, service restart, production network,
  account, tenant or real business-task operation was performed.

## Scope And Identity

- Added D-15 as the next unused scope decision. It supersedes only the physical-
  disconnection gate wording in D-12/D-13/D-14 while preserving historical
  evidence and every task state.
- Acceptance now requires evidence that the actual production path did not
  invoke ADB, a development-computer runner or Edge. Cable attachment alone is
  neither passing nor failing evidence. ADB remains an optional authorized
  diagnostic tool.
- Persisted the user workflow role split: parent plans/delegates/reviews; the
  designated GPT-5.6 Sol / High worker executes approved repository edits,
  builds and tests. Device, production, lock, consent, identity, signature,
  version, no-send and side-effect boundaries are unchanged.
- Changed only the existing businessAcceptance version identity to versionCode
  `5` and versionName `0.1.0-business-acceptance.5`; the only matching test
  assertion is
  `mobile/companion/app/src/testBusinessAcceptance/java/com/company/cloudctl/companion/network/BusinessAcceptanceTransportTest.kt`.
- Signing configuration, TLS, certificate pins, recipe/update keys, runtime
  logic, debug flags, release gates, schema and installed v4 were not changed.

## Verification

All Gradle commands ran from `mobile/companion` with `--offline --no-daemon
--console=plain` and:

```text
JAVA_TOOL_OPTIONS=-Drobolectric.dependency.repo.url=file:///Users/wangziheng/.m2/repository
```

1. `.venv/bin/python scripts/plan_guard.py docs/current/tasks.json`: exit 127;
   the isolated worktree has no ignored `.venv` directory, so no audit ran.
2. `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python scripts/plan_guard.py docs/current/tasks.json`:
   exit 0; 54 tasks, development DAG 68 edges, acceptance-union DAG 139 edges,
   no running write conflicts, 62 inherited IDs and 50 packages covered.
   The interpreter was reused read-only; the main worktree was not edited.
3. `jq empty docs/current/tasks.json`: exit 0.
4. Focused identity command:
   `./build-external.sh --offline --no-daemon --console=plain :app:testBusinessAcceptanceUnitTest --tests com.company.cloudctl.companion.network.BusinessAcceptanceTransportTest`:
   exit 0, 3/3 tests passed.
5. Full candidate command:
   `./build-external.sh --offline --no-daemon --console=plain :app:testDebugUnitTest :app:testBusinessAcceptanceUnitTest :app:assembleBusinessAcceptance`:
   exit 0, `BUILD SUCCESSFUL in 2m 38s`; 86 tasks, 85 executed and 1 up-to-date.
   Debug: 175 suites / 1303 tests. BusinessAcceptance: 175 suites / 1289
   tests. Both have 0 failures, 0 errors and 0 skipped.
6. The assembly dependency graph executed `lintVitalAnalyzeBusinessAcceptance`,
   `lintVitalReportBusinessAcceptance` and `lintVitalBusinessAcceptance`; the
   return value was 0 and the text report states `No issues found.`
7. `aapt dump badging`, `apksigner verify --print-certs`, APK SHA256, and
   `dexdump` BuildConfig inspection all exited 0. `git diff --check` exited 0.

One private-file listing used a single-quoted literal `$HOME` and exited 1
without changing files. The corrected absolute-path listing exited 0. A first
temporary DEX parser command was rejected before execution because it included
automatic temporary-file deletion; the retry wrote only
`/private/tmp/cloudctl-v5-classes2.dex` and `dexdump` exited 0.

## Candidate Artifact

- Private path:
  `/Users/wangziheng/CloudCtlExternal/acceptance/20260928-v5/cloudctl-business-acceptance-v5.apk`.
- SHA256: `8b40b9284be9f6f7aca812792ff9315d9376803b9c6ec3d1ad9190241e0e5b0f`.
- Size: 50,954,372 bytes.
- Package: `com.company.cloudctl.companion`.
- Version: code `5`, name `0.1.0-business-acceptance.5`.
- Signer certificate SHA256:
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`,
  matching the preserved v4 candidate signer.
- Embedded `SOURCE_REVISION`: `a3eb419`. The source worktree was clean before
  the build, so the revision has no `-dirty` suffix. Ignored Gradle outputs were
  produced by the build and are not source changes.
- Embedded flags: `DEBUG=false`, `HEARTBEAT_DIAGNOSTIC=false`,
  `IM_UPLOAD_HOLD_ALLOWED=false`, `RECIPE_SIGNING_PUBLIC_KEYS={}`.
- Machine-readable record:
  `artifacts/three-device-20260928/v5-candidate-manifest.json`.

The preserved v4 candidate remains SHA256
`cff3b03a72f56781a73d2713bd68a968f1d47a6c21f27c528629f72f6e9fcf70`;
the preserved installed-v3 backup remains SHA256
`c6a39272612bf507c70d0a5f3084162b87770d445fcecedb4e659be5cd4a9005`.
Neither was overwritten.

## Remaining Gates

- Controller review and explicit integration delegation are required; this
  branch was not pushed or integrated.
- The v5 candidate is not installed. An authorized idle window, exact device,
  lock, signer/version/identity checks and data-preserving upgrade remain
  controller-owned.
- Maintenance enter/exit, full service lifecycle, heartbeat continuity,
  accessibility binding, order/IM read-only flows, disconnect/recovery and the
  D-15 production invocation-path evidence remain device acceptance work.
- Software tests and a built APK do not promote B11, O10, 1E or any other task
  to device-accepted status.
