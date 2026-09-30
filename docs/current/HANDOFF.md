# Current checkpoint: unified v8 pending user installation

Explicit user resumption only. Do not schedule or autonomously continue from this
checkpoint. The parent plans/reviews and controls devices/cloud; GPT-6 Astra / Low
executed the approved isolated repository change, build and focused tests. This
file cannot select a runtime model or confer device/business authority.

## Verified software and repository baseline

- Verified code baseline: fc56e748d0f1783898750e5472c7a9c5f54e1621.
- Includes keyboard recovery 6be7009 and real coroutine-cancellation regressions
  f52cec1; the v8 change itself is only four version/assertion substitutions in
  app/build.gradle.kts and BusinessAcceptanceTransportTest.kt.
- Parent accepted the exact owned diff and fast-forwarded main. Check actual
  HEAD, origin tracking, index and diff on next resumption; no automatic rerun of
  unchanged tests. Docs-only later commits are expected.
- tasks.json remains the sole task-state authority. All 54 IDs / 108 state
  fields unchanged; SHA256 3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb.
- Main's 42 preexisting untracked files were preserved.

## One APK for this controlled acceptance round

- User delivery path:
  /Users/wangziheng/CloudCtlExternal/apk-delivery/cloudctl-companion-v8.apk
- SHA256: 892e6d3532aae4d9df95d322411ec79d7c33e95ff70c7f1cc73e4cfa9b1073df.
- Bytes: 50956020; package com.company.cloudctl.companion; versionCode 8,
  versionName 0.1.0-business-acceptance.8; minSdk 29; sourceRevision fc56e74.
- CONTROLLED_ACCEPTANCE_NOT_PRODUCTION_RELEASE. This does not resolve the
  missing release-owner CLOUDCTL_APP_UPDATE_PUBLIC_KEY or production signing.
- One generic APK with a single current signer B (existing OnePlus certificate
  67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796) and valid
  A-to-B v3 proof-of-rotation (A is the existing Huawei certificate
  667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736).
- Public lineage retained at:
  /Users/wangziheng/CloudCtlExternal/apk-delivery/signing/companion-A-to-B.lineage
  and in executor evidence. Future candidates must preserve this migration
  chain and signer; do not build separate model packages or silently change
  signing homes. Both existing keystores were unchanged; no key exported.
- Exact API29 and API34 plus supported-range cryptographic checks passed.
  Embedded old-certificate installedData=true; rollback=false. This supports a
  data-preserving update path in Android's model; OEM installation, encrypted
  binding recovery and actual keyboard behavior remain unproven until installed.
  Android's pre-13 rotation caveats remain applicable. Do not promise rollback
  to an A-only/older-version package.
- Focused Debug IME tests: 93/0 failures/errors/skips, including real cancellation.
  BusinessAcceptanceTransportTest: 3/0. LintBusinessAcceptance: 0 errors/fatal,
  19 warnings retained. Assembly passed. Parent matched every APK ZIP payload
  entry against the Gradle base, parsed XML counts and verified final hash.
- Evidence root:
  /Users/wangziheng/CloudCtlExternal/acceptance/20260930-unified-companion-v8/attempt-tu6dw1le/
  See SUMMARY.md, candidate-manifest.json, parent-artifact-review.json,
  delivery-manifest.json and device-copy-*.json.

## User scope and fresh device observations

- User confirmed selected phones idle, requested at least two usable phones,
  manual APK installation and controller-assisted binding checks. User later
  reported Huawei P30Pro and OnePlus9R configured. This is not uninstall,
  clear-data, arbitrary account rebind, cloud migration, sending or publishing
  permission. Installation remains user-owned.
- Selected phones only: OnePlus9R b0644fb5 and Huawei VOG APH0219624006517.
  ELE GBGDU19830002425 and all other attached phones remain excluded.
- Fresh reads confirmed 9R still v6/B and Sogou selected; Huawei upgraded by user
  to exact v7/A and iFlytek selected, original binding retained. OnePlus process
  was not running at observation; old health fields are not current readiness.
- Both retain their original device IDs and same original tenant. Do not mint
  replacement device IDs or rebind already-valid installations.
- 9R cloud ID: 4aabc387-6e4b-4b59-a525-b1c119ec7f5b.
  Huawei cloud ID: 769d67a5-679c-4655-aeb9-60a2a265fbc6.
- Before APK copying, 2026-09-30T10:22:45Z read-only cloud check found zero
  active leases/nonterminal tasks/enabled schedules/previews/debug sessions on
  both. These are historical checks; repeat before further device writes.
- Effective API environment was CLOUDCTL_IM_RECEIVE_ONLY=true. Current server
  release remains order-delivery-557f547; no deployment performed.

## Transfer result and next step

- Controller copied v8 to 9R /sdcard/Download/cloudctl-companion-v8.apk and
  verified exact hash. No installer/app launch or binding change executed.
- Huawei adb push timed out after 40 seconds; bounded file/hash reads also
  timed out. Its /sdcard/Download/cloudctl-companion-v8.apk is UNKNOWN and must
  not be installed without fresh hash verification. User can transfer the
  verified desktop source through their normal method.
- Both copy-operation locks were released successfully. The earlier failed
  v7 transfer lock (Huawei fencing 2) was recovered only after expiry and fresh
  occupancy/tool checks; recorded state is FREE. Never steal a live lock.
- Next: user manually covers existing installs with this SAME v8, retaining
  app data. If installer still rejects, stop and diagnose; no uninstall/clear
  or secret/permission bypass. After user reports installation, read exact APK
  version/hash, retained device/binding, normal IME and successful heartbeats.
- Then verify manual keyboard input and supported automatic-input restoration
  without sending, and real inbound aggregation from at least two phones.
  Product flow through pre-publication and screen share/end/handoff need one
  capable phone each. No third-phone or physical cable-unplug gate.
- API29 automatic-input path still requires manual selection of CloudCtl IME;
  it is not a general hand-typing keyboard. v8 includes recovery controls, not
  a new manual keyboard. Do not claim all device-input paths accepted from
  software tests or merely observing Sogou/iFlytek selection.

## CI boundary

Previous observed run 36604004938 at f52cec1 completed: frontend success,
Python success, Android failed at Require Android release update public key.
Do not reuse its counts for new SHAs or rerun it. A normal source push may
create a new run; inspect only its exact SHA when needed. No workflow/key
configuration, production deployment, release or device acceptance was granted
by this checkpoint.
