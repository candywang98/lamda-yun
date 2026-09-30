# Current checkpoint: manual keyboard v9 pending user installation

Explicit user resumption only. Do not schedule or autonomously continue from this
checkpoint. The parent plans/reviews and controls devices/cloud; GPT-6 Astra / Low
implemented the approved isolated IME-MANUAL-V9 change, build and tests. This
file cannot select a runtime model or confer device/business authority.

## Verified software and repository baseline

- Verified software baseline: b469c50ee71a1ab40cc45de7cc62b8727c874436;
  sourceRevision b469c50, built from a clean committed worktree.
- Contract manual-v1: GPT-6 Astra / Low implemented the 16-path change; parent
  reviewed the exact diff and source hashes and fast-forwarded main to b469c50.
  Earlier keyboard recovery and real coroutine-cancellation protections remain.
- Final remote/GitHub synchronization check is parent-owned and pending. Do not
  claim this checkpoint was pushed. Check actual HEAD, origin tracking, index
  and diff on explicit resumption; do not rerun unchanged tests automatically.
  Docs-only later commits do not replace the APK's software baseline.
- tasks.json remains the sole task-state authority. All 54 IDs / 108 state
  fields unchanged; SHA256 3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb.
- Main's 42 preexisting untracked files were preserved.

## Manual keyboard contract and safety

- Native manual keyboard supports English lowercase/uppercase, digits, all
  ordinary ASCII punctuation across two symbol pages, space, selection
  replacement/deletion and Unicode-codepoint deletion. Password typing uses
  selection metadata without reading, logging or storing secret text.
- Newline is literal text only in eligible multiline text fields; single-line
  and actionSend fields never send. No IME_ACTION_SEND, Enter key-event fallback,
  clipboard input or queued replay of stale editor clicks was added.
- Hide/show preserves live selection metadata and resets keyboard layout.
  Switching uses the public keyboard picker with input-method settings fallback;
  canceling or failing to open the picker does not strand manual typing.
- No built-in pinyin. Chinese typing requires switching to an installed Sogou or
  iFlytek keyboard. API29 automation still requires CloudCtl selected again after
  the user switches away for Chinese input.
- Independent manual-action epoch invalidates in-flight and held IME and
  accessibility proofs, including type-delete ABA. Scoped temporary automation
  blocks manual typing but keeps the switch escape available. Normal editor
  rebuild, target/session/empty-field/password checks, cancellation and original
  keyboard restoration remain protected.

## One APK for this controlled acceptance round

- User delivery path:
  /Users/wangziheng/CloudCtlExternal/apk-delivery/cloudctl-companion-v9.apk
- SHA256: ad0fcabca505a62b72cbee7da4c911d48b75ee8598d3bc424899a34a7f662890.
- Bytes: 51009268; package com.company.cloudctl.companion; versionCode 9,
  versionName 0.1.0-business-acceptance.9; minSdk 29; sourceRevision b469c50.
- Parent independently verified and promoted the exact same universal candidate
  to this stable path. The v8 artifact is unchanged; no per-model APKs exist.
- DEBUG, HEARTBEAT_DIAGNOSTIC and IM_UPLOAD_HOLD_ALLOWED are false; the manifest
  is not debuggable.
- CONTROLLED_ACCEPTANCE_NOT_PRODUCTION_RELEASE. This does not resolve the
  missing release-owner CLOUDCTL_APP_UPDATE_PUBLIC_KEY or production signing.
- One generic APK with a single current signer B (existing OnePlus certificate
  67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796) and valid
  A-to-B v3 proof-of-rotation (A is the existing Huawei certificate
  667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736).
- Public lineage retained at:
  /Users/wangziheng/CloudCtlExternal/apk-delivery/signing/companion-A-to-B.lineage
  SHA256 70b5ee0f728d651ec077161b5752a49648d629bb1dd80818953024b6b9595e05.
  The existing lineage was reused, not rotated or recreated; rotation-min-sdk=28.
  Future candidates must preserve this migration chain and signer; do not build
  separate model packages or silently change
  signing homes. Both existing keystores' hashes and metadata were unchanged and
  matched prior v8 evidence; no private key exported.
- Exact API29 and API34 plus supported-range cryptographic checks passed.
  Embedded old-certificate installedData=true; rollback=false. This supports a
  data-preserving update path in Android's model; OEM installation, encrypted
  binding recovery and actual keyboard behavior remain unproven until installed.
  Android's pre-13 rotation caveats remain applicable. Do not promise rollback
  to an A-only/older-version package.
- Full focused Debug IME suite: 164 tests, 0 failures/errors/skips, including
  cancellation regressions. Manual tests ran on API29/32/34, 23 per API; no
  silent SDK exclusion. API29's initially missing Robolectric dependency was
  fetched from official Maven Central with authorization and checksum-verified;
  subsequent Gradle runs remained offline.
- BusinessAcceptanceTransportTest: 3 tests, 0 failures/errors/skips.
  LintBusinessAcceptance: 0 errors/fatal, 19 warnings. Assembly passed.
  Parent independently matched all 16 source hashes and all 124 ZIP payload
  entries against the Gradle base, parsed actual JUnit XML, and verified the
  final hash, identity, lineage, key metadata and unchanged task ledger.
- 360dp/640dp geometry and text-label measurement assertions passed. Exported
  PNGs omit key glyphs and are not usable visual acceptance; neither those
  assertions nor Robolectric results establish device acceptance.
- Evidence root:
  /Users/wangziheng/CloudCtlExternal/acceptance/20260930-manual-keyboard-v9/
  See DELIVERY.md, candidate-manifest.json and parent-artifact-review.json;
  executor/ contains exact commands, archived JUnit, lint and signing evidence.

## User scope and historical device observations

- User confirmed selected phones idle, requested at least two usable phones,
  manual APK installation and controller-assisted binding checks. User later
  reported Huawei P30Pro and OnePlus9R configured. This is not uninstall,
  clear-data, arbitrary account rebind, cloud migration, sending or publishing
  permission. Installation remains user-owned.
- Selected phones only: OnePlus9R b0644fb5 and Huawei P30Pro (VOG) APH0219624006517.
  ELE GBGDU19830002425 and all other attached phones remain excluded.
- Last observed in the prior turn: 9R v6/B with Sogou selected; Huawei upgraded
  by the user to exact v7/A with iFlytek selected, original binding retained.
  OnePlus process was not running then. These are historical observations, not
  current readiness or new reads in the v9 keyboard turn.
- At that observation, both retained their original device IDs and same original
  tenant. Do not mint replacement IDs or rebind already-valid installations.
- 9R cloud ID: 4aabc387-6e4b-4b59-a525-b1c119ec7f5b.
  Huawei cloud ID: 769d67a5-679c-4655-aeb9-60a2a265fbc6.
- Before APK copying, 2026-09-30T10:22:45Z read-only cloud check found zero
  active leases/nonterminal tasks/enabled schedules/previews/debug sessions on
  both. These are historical checks; repeat before further device writes.
- Historical cloud observations: CLOUDCTL_IM_RECEIVE_ONLY=true and server
  release order-delivery-557f547. Neither was rechecked for this keyboard turn;
  no deployment occurred.
- Cloud website: https://43.133.243.154.sslip.io/cloudctl-mobile/
  Preserved reference only, not newly checked. No credentials belong here.
- No device/cloud/ADB operations, installation, permission changes, binding
  changes or sending occurred during this keyboard turn. This checkpoint grants
  no new authority for any of them.

## Transfer result and next step

- Historical transfer: controller copied v8 to 9R
  /sdcard/Download/cloudctl-companion-v8.apk and verified its exact hash. No
  installer/app launch or binding change was executed in that transfer.
- Historical Huawei v8 copy timed out after 40 seconds; bounded file/hash reads
  also timed out. Its /sdcard/Download/cloudctl-companion-v8.apk remains UNKNOWN
  from those observations. There have been NO v9 phone copies.
- Historical copy-operation locks were released successfully. The earlier failed
  v7 transfer lock (Huawei fencing 2) was recovered only after expiry and fresh
  occupancy/tool checks; recorded state is FREE. Never steal a live lock.
- Next: user transfers this SAME hash-verified v9 through their normal method
  and manually covers the existing installations, retaining app data and original
  bindings. Do not uninstall, clear data or rebind. If the installer rejects,
  stop and diagnose; no divergent fallback package or secret/permission bypass.
- After the user reports installation and authorizes reads, verify exact APK
  version/hash, retained device/binding, normal IME and successful heartbeats.
- Manual keyboard and no-send keyboard-switch/restoration acceptance remain
  pending, as does real inbound aggregation from at least two selected phones.
  Product flow through pre-publication and screen share/end/handoff need one
  capable phone each. No third-phone or physical cable-unplug gate.
- API29 automatic input still requires CloudCtl selected after Chinese-keyboard
  switching. Do not claim device-input acceptance from software tests or merely
  observing Sogou/iFlytek selection.

## CI boundary

Previous observed run 36604004938 at f52cec1 completed: frontend success,
Python success, Android failed at Require Android release update public key.
This is prior evidence only; no new CI result is claimed for b469c50 or this
docs-only checkpoint. Final remote verification remains the parent's work.
Do not reuse its counts for new SHAs or rerun it. A normal source push may
create a new run; inspect only its exact SHA when needed. No workflow/key
configuration, production deployment, release or device acceptance was granted
by this checkpoint.
