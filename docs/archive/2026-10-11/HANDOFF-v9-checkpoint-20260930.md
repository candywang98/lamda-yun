# Current checkpoint: user-installed v9; dual-device inbound acceptance pending

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
- Parent's preceding integration-postflight.json verifies source/old docs sync:
  main and remote main both c2761b9aeb8520d3016a6189079273a946a1dc66, pushed=true,
  remote readback verified and tracked clean. That push is complete, not pending.
  This docs-only V9-INSTALLED-HANDOFF sidecar starts from that frozen baseline
  and owns only docs/current/HANDOFF.md. The controller owns authoritative task
  state, evidence, integration and verification of this new checkpoint's sync.
  Check actual HEAD/index/diff on explicit resumption; do not rerun unchanged
  tests automatically. Docs-only commits do not replace the APK software baseline.
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
  data-preserving update path in Android's model. Subsequent installation and
  retained binding observations are bounded below; actual keyboard behavior
  remains unaccepted, and these checks alone do not prove OEM binding recovery.
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

## User scope and installed-v9 observations

- User confirmed selected phones idle, requested at least two usable phones,
  manual APK installation and controller-assisted binding checks. User later
  reported both selected phones installed the delivered v9. This is not uninstall,
  clear-data, arbitrary account rebind, cloud migration, sending or publishing
  permission. Installation remains user-owned.
- Selected phones only: OnePlus9R b0644fb5 and Huawei P30Pro (VOG) APH0219624006517.
  ELE GBGDU19830002425 and all other attached phones remain excluded.
- Primary new evidence (parent-owned, read-only input to this sidecar):
  /Users/wangziheng/CloudCtlExternal/acceptance/20260930-v9-installed-dual-inbound/preflight.json
  Prior integration evidence:
  /Users/wangziheng/CloudCtlExternal/acceptance/20260930-manual-keyboard-v9/integration-postflight.json
- At 2026-09-30 19:42 Shanghai (11:42:07Z), both authenticated cloud heartbeat
  profiles and bindings report 0.1.0-business-acceptance.9, accessibilityEnabled
  true, runner IDLE, safety barrier NONE and enabled NOTIFICATION/xianyu.
  Between 11:41:07Z and 11:42:07Z, independent heartbeat counters increased:
  9R 43206 -> 43209; Huawei 1065 -> 1067. This is fresh heartbeat evidence,
  not merely a last_seen timestamp; it does not establish business acceptance.
- Original tenant 00000000-0000-7000-8000-000000001111 and original identities
  remain, with matching active/mobile binding IDs and revoked_at=null:
  9R device 4aabc387-6e4b-4b59-a525-b1c119ec7f5b,
  binding 202ff9cb-6b6d-4ccc-bbf7-31bd91edb51e;
  Huawei device 769d67a5-679c-4655-aeb9-60a2a265fbc6,
  binding 31a74c77-6aac-4f66-bd79-f41d7293f54c. Do not replace IDs or rebind.
- Parent's optional diagnostic ADB evidence for 9R: installed versionCode 9,
  stopped=false, actual accessibility serviceBound (accessibility_bound=true),
  Sogou retained (com.sohu.inputmethod.sogouoem/.SogouIME). Installed APK SHA256
  ad0fcabca505a62b72cbee7da4c911d48b75ee8598d3bc424899a34a7f662890 exactly
  matches the delivered artifact. Keyboard selection is not typing acceptance.
- Huawei was NOT present in ADB. Its v9 evidence is authenticated cloud heartbeat
  plus the user's installation report; installed APK hash and physical keyboard
  remain unverified. Huawei's CELLULAR cloud connection demonstrates diagnostic
  ADB is not needed for that connection; it does not prove whole-path runtime-
  independent business acceptance. 9R reported WIFI.
- Server effective receive-only=true (cloudctl-mobile-api.service). The
  11:41:07Z occupancy sample found zero active leases/nonterminal mobile tasks.
  This is sampled evidence, not ongoing occupancy or fresh write authorization.
- No new IN on either phone since 2026-09-30T11:30:00Z (19:30 Shanghai).
  Parent-provided historical context: 9R IN count 104, newest September 30
  19:07:57 Shanghai; Huawei IN count 1, last September 26. These are HISTORICAL,
  not fresh dual-device acceptance; preflight records new_messages=0/accepted=false.
- Cloud website: https://43.133.243.154.sslip.io/cloudctl-mobile/
  Space 18 remains agentDelegatedToUser; no browser page operation in this turn.
  The user was asked asynchronously to arrange two external real test messages
  and explicitly hand back the logged-in webpage; both inputs remain pending.
  No credentials belong here.
- No device writes, installs, touches/configuration changes, cloud writes, sends
  or browser page operations occurred in the installed-v9 preflight turn. This
  docs-only sidecar only reads supplied evidence; it performs no device, ADB,
  SSH, cloud or browser access and grants no authority for subsequent actions.

## Next acceptance and stop conditions

- Next is real dual-device inbound acceptance, pending the user's two externally
  arranged messages and explicit webpage handback. Keep Space 18 delegated until
  then. For each selected phone, correlate a NEW real notification with cloud IN
  and the same-page result; verify device/source/peer separation and deduplication.
  Retain timestamps and identifiers as controller-owned evidence. Stop before
  send: no agent-sent messages, simulated notifications or SQL inserts may
  substitute for real inbound acceptance. Receive-only remains required.
- Installation reports do not authorize uninstall, clear-data, rebind or business
  writes. Any later device write requires fresh authorization/occupancy checks
  and controller-owned locks; never steal a live lock. No new installation or
  transfer is the next step merely because Huawei's installed hash is unknown.
- Manual keyboard and no-send keyboard-switch/restoration acceptance remain
  pending, as does real inbound aggregation from the two selected phones.
  Product flow through pre-publication and screen share/end/handoff need one
  capable phone each. No third-phone or physical cable-unplug gate.
- API29 automatic input still requires CloudCtl selected after Chinese-keyboard
  switching. Do not claim device-input acceptance from software tests or merely
  observing Sogou/iFlytek selection.

## CI boundary

Previous observed run 36604004938 at f52cec1 completed: frontend success,
Python success, Android failed at Require Android release update public key.
This is prior evidence only; no new CI result is claimed for b469c50 or this
docs-only checkpoint. Prior c2761b9 synchronization is verified above; only this
new docs checkpoint's integration/synchronization remains the controller's work.
Do not reuse its counts for new SHAs or rerun it. A normal source push may
create a new run; inspect only its exact SHA when needed. No workflow/key
configuration, production deployment, release or device acceptance was granted
by this checkpoint.
