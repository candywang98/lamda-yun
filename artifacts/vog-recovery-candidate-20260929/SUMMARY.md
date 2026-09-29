# VOG-RECOVERY-V7 controlled-acceptance candidate

## Delivery and scope

- Frozen baseline: `eb1eedccef0e4dd3325c1d5be4d7e154d3d1543b`.
- Branch: `agent/sol-vog-recovery-v7-20260929`.
- Source commit: `226eff2ff472459603af9c6e4a01f4e92dce7ebd`.
- Evidence commit: identified in the final handoff; created after the APK.
- Status: **PREPARED_NOT_INSTALLED**, local controlled acceptance only.
- Source changes are exactly four values in two approved files:
  `mobile/companion/app/build.gradle.kts` (businessAcceptance versionCode 6 to 7
  and suffix `.6` to `.7`) and
  `mobile/companion/app/src/testBusinessAcceptance/java/com/company/cloudctl/companion/network/BusinessAcceptanceTransportTest.kt`
  (the two matching variant assertions).
- Application ID, minSdk, flags, signing logic, update/recipe trust, pin policy,
  keyboard code, release verifier, task ledger and all other production code
  remain unchanged. Main was not modified by this worker.

The source commit was made from a clean checkout before any Gradle invocation.
`git describe --always` returned `226eff2`; clean-tree guards passed before
building and after copying the APK, before adding these evidence files.
The final APK's `classes2.dex` BuildConfig independently confirms
`SOURCE_REVISION="226eff2"` without a dirty suffix. The evidence commit is not
the APK's source revision.

## Build and signing

Commands ran directly from this worktree's `mobile/companion`, never through
`build-external.sh`. The existing wrapper, SDK, Gradle cache and local
Robolectric artifacts were used offline; no packages were installed.

```bash
export JAVA_HOME=/Users/wangziheng/CloudCtlExternal/jdks/temurin-17/Contents/Home
export ANDROID_HOME=/Users/wangziheng/CloudCtlExternal/android-sdk
export ANDROID_SDK_ROOT=/Users/wangziheng/CloudCtlExternal/android-sdk
export ANDROID_USER_HOME=/Users/wangziheng/.android
export GRADLE_USER_HOME=/Users/wangziheng/CloudCtlExternal/gradle-home
export JAVA_TOOL_OPTIONS=-Drobolectric.dependency.repo.url=file:///Users/wangziheng/.m2/repository
OUT=/Users/wangziheng/CloudCtlExternal/acceptance/20260929-vog-v7
CACHE="$OUT/project-cache-226eff2.cTiAeg"
APK="$OUT/cloudctl-vog-recovery-v7.apk"
BT="$ANDROID_HOME/build-tools/35.0.0"
```

The external output directory was new. The cache above was created with
`mktemp -d "$OUT/project-cache-226eff2.XXXXXX"` and is unique to this build.

| Command | Exit | Result |
|---|---:|---|
| `./gradlew --offline --no-daemon --console=plain --project-cache-dir "$CACHE" :app:signingReport` | 0 | Successful in 15s; businessAcceptance resolves exactly to the approved VOG keystore and certificate. |
| `./gradlew --offline --no-daemon --console=plain --project-cache-dir "$CACHE" --rerun-tasks :app:testDebugUnitTest :app:testBusinessAcceptanceUnitTest :app:lintDebug :app:lintBusinessAcceptance :app:assembleBusinessAcceptance` | 0 | BUILD SUCCESSFUL in 3m 37s; 99 actionable tasks, 99 executed. |
| `"$BT/apksigner" verify --verbose --print-certs "$APK"` | 0 | One signer, APK v2 signature verifies, exact VOG certificate. |
| `"$BT/aapt" dump badging "$APK"` | 0 | Original package, version 7 / `.7`, minSdk 29, targetSdk 35; no debuggable flag. |
| `"$BT/aapt" dump xmltree "$APK" AndroidManifest.xml` | 0 | Compiled manifest confirms version/SDK values; application has no debuggable attribute. |
| `shasum -a 256 "$APK"` and `stat -f '%z' "$APK"` | 0 / 0 | SHA-256 and size match the manifest below. |
| `cmp -s app/build/outputs/apk/businessAcceptance/app-businessAcceptance.apk "$APK"` | 0 | Delivered file is byte-for-byte identical to Gradle output. |
| `"$BT/dexdump" "$OUT/classes2.dex"` with byte-level BuildConfig extraction | 0 | Embedded version, source marker and all requested flags verified. |
| Manifest, signature and DEX field assertion parser | 0 | All exact expected values matched; not just generated Java source. |
| Evidence JSON cross-check against APK bytes, DEX fields, signature log, JUnit XML and lint XML | 0 | Recorded metadata/counts agree with existing outputs; no tests rerun. |
| `git merge-base --is-ancestor 6be7009 eb1eedccef0e4dd3325c1d5be4d7e154d3d1543b` | 0 | Frozen source includes the keyboard recovery change. |

The signing store `/Users/wangziheng/.android/debug.keystore` was checked
present/nonempty before Gradle. The businessAcceptance `signingReport` block
was checked for both that exact store path and certificate SHA-256
`667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`
before the build command was allowed to run.

An EXIT guard compared the store's SHA-256 and
`stat -f '%i:%z:%m:%c:%p'` before and after both Gradle invocations. It reported
`keystore_content_and_metadata_unchanged=true`: content, inode, size, mtime,
ctime and mode were unchanged. The checksum stayed in shell variables; no
password/private material was printed, copied, exported, created or replaced.
The OnePlus external `android-user-home` was not used.

This is **debug-key signed but non-debuggable**, as specified by the existing
businessAcceptance variant. Existing acceptance update trust is unchanged.
No release task was requested, no `-x` or gate bypass was used, and no update
key was supplied or configured.

## Test and lint evidence

Counts were parsed with Python's XML parser from
`app/build/test-results/testDebugUnitTest/TEST-*.xml` and
`app/build/test-results/testBusinessAcceptanceUnitTest/TEST-*.xml`:

| Suite | XML suites | Tests | Failures | Errors | Skipped |
|---|---:|---:|---:|---:|---:|
| Debug | 175 | 1312 | 0 | 0 | 0 |
| BusinessAcceptance | 175 | 1298 | 0 | 0 | 0 |

Both full suites ran without `--tests` filters. Controller independently
parsed the same counts and confirmed inclusion of pin/IME recovery tests.
Gradle lifecycle/no-source task statuses are not JUnit skipped tests.

Full variant lint XML reports contain **0 errors**, but are not warning-free:
Debug has **18 warnings**, BusinessAcceptance **19 warnings**. By issue ID:
ApplySharedPref 8 each, BatteryLife 1 each, DataExtractionRules 1 each,
ObsoleteSdkInt 3/4, StaticFieldLeak 2 each, UnusedResources 3 each.
These findings were not suppressed or fixed outside the approved version scope.
The build also emitted Kotlin warnings and a native-library strip warning;
the retained external build log contains the diagnostics.

## Artifact and retained baseline

- APK: `/Users/wangziheng/CloudCtlExternal/acceptance/20260929-vog-v7/cloudctl-vog-recovery-v7.apk`
- SHA-256: `57f5f444566fdd3878db036eadb70f130d067092a231a4320f8bade39b6bfcb0`
- Size: **50,955,232 bytes**.
- Package: `com.company.cloudctl.companion`.
- Version: **7**, `0.1.0-business-acceptance.7`; minSdk **29**, targetSdk **35**.
- Certificate SHA-256:
  `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`.
- APK DEX: `BUILD_TYPE=businessAcceptance`, `SOURCE_REVISION=226eff2`,
  `DEBUG=false`, `HEARTBEAT_DIAGNOSTIC=false`, `IM_UPLOAD_HOLD_ALLOWED=false`,
  `RECIPE_SIGNING_PUBLIC_KEYS={}`.
- Machine-readable record: `candidate-manifest.json` in this evidence directory.

The retained baseline
`/Users/wangziheng/CloudCtlExternal/acceptance/20260929-two-device-readonly/20260929T040140Z/huawei-vog.base.apk`
was read-only verified by SHA-256, apksigner and aapt, all exit 0:
`2f424419719490f237784ae876d3f57f03d04e7455ffa8df1a4710fc686f5f2b`,
same package and signer, version 1 / `0.1.0`, minSdk 29, targetSdk 35,
debuggable. It was not overwritten. This is a retained APK comparison, not
a fresh observation of the phone's installed state.

Controller independently verified the new artifact using apksigner and
aapt2: signature, hash, package, version, SDK values and test counts agree.

## Inspection caveats

- The existing `apkanalyzer manifest print` launcher returned 1 with
  `ClassNotFoundException: T7.CloudCtlBuild.android-sdk.cmdline-tools.latest`.
  No SDK repair/install was attempted. Existing aapt badging and compiled
  manifest inspection replaced it successfully; its empty export was removed.
- The first DEX parser returned 1 because unrelated dexdump output contains
  non-UTF-8 bytes. Capturing bytes, selecting the exact BuildConfig class and
  decoding only that block succeeded. Neither the APK nor DEX data was changed.
- An initial output-directory listing returned 1 because the new directory
  did not yet exist; a read-only wildcard search returned 1 for no match.
  Neither was a build/test failure or changed any source.
- The first final JSON cross-check command had a Python inline-quoting
  SyntaxError and returned 1 before execution. The corrected read-only
  assertion command returned 0; no build or test cycle was repeated.

## Boundaries and later-install preconditions

1. Controller must separately authorize an exact VOG install window, exclusive
   device ownership and quiescent/no-send conditions. Package replacement can
   start the existing sync service; this build does not authorize installation.
2. Recheck the actual phone's package, version, signer and API level against
   this candidate and the retained baseline; rehash the APK. Any mismatch stops
   the operation, not a trust change or alternate signing key.
3. Controller must confirm deployed-server compatibility and a data-preserving
   upgrade/recovery plan, with normal keyboard availability and existing
   binding/tenant identity retained. No uninstall/data clear, rebinding or
   business task/send/publish is authorized here.
4. Later device evidence must separately establish keyboard/IME recovery,
   required service/permission state and the intended read-only business path.
   Software counts and generic notifications do not prove real human-message
   delivery or phone recovery. No universal three-phone/disconnection gate is added.

The frozen source pin successor is
`f2a9423e27fd8d6cdcd00d76e9da8918a402e118fe52656b84342dda6fb40725`.
Controller reported default CA/hostname TLS validation at
`2026-09-29T11:43:31.382Z` with that leaf and Sep 27-Dec 26 validity;
this worker made no network query and changed no pin/trust policy.

Latest controller-reported integration snapshot: main Python **1624 passed,
14 skipped**, raw gates passed, `eb1eedc` pushed; hosted Python was still
running after successful PG discovery. These are controller facts, not this
worker's test run or a final hosted-CI result. Android release still lacks the
controlled update public key; acceptance assembly does not resolve that gate.

No ADB, SSH, settings, device locks, production service/deployment, account or
tenant change, send/publish/upload, GitHub configuration, push, other-chat or
task-ledger operation was performed. Building proves neither device recovery
nor permission to install. Await controller reassignment after handoff.
