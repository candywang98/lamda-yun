# Worker: OnePlus V5 Device Acceptance Harness

## Scope

- Baseline: `8d74987c2ae0bdc7dc3bbec88df50c8e52910833`.
- Branch: `agent/sol-v5-device-20260928`.
- Target is exactly OnePlus9R serial `b0644fb5`, model `LE2100`, cloud device
  `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`.
- Candidate identity remains SHA256 `8b40b9284be9f6f7aca812792ff9315d9376803b9c6ec3d1ad9190241e0e5b0f`,
  versionCode `5`, versionName `0.1.0-business-acceptance.5`, signer
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`,
  embedded source `a3eb419`.
- This commit prepares the reviewed harness only. The planner's real-write HOLD
  remains active: v5 was not installed and maintenance was not changed.

## Safety Properties

- The local harness exposes one fixed `adb -s b0644fb5 install -r` command and
  has no app launch, force-stop, uninstall, clear-data, navigation, business
  task, account, tenant or other-device operation.
- Fresh candidate, installed-v4, signer, device, process, exact service,
  accessibility, cloud occupancy, identity, receive-only and business-count
  gates run after the shared device lock is acquired.
- Maintenance prepare is split into an expectedVersion `10` CAS and a separate
  verification snapshot. Cleanup/finish is allowed only after the caller
  receives that CAS acknowledgement and stores a private run-bound ownership
  record. CAS 409, a competing version11 prepare or an uncertain/lost response
  remains unowned and is never cleared by this harness.
- An acknowledged prepare followed by a snapshot/install/observation failure
  can exit only the exact `true/version11` state using expectedVersion `11`.
  Binding, credential, account and tenant safety still gate that exit; unrelated
  occupancy or aggregate-count drift is reported but does not strand provably
  owned maintenance. Unexpected version/state remains a prominent conflict.
- Phone evidence requires the exact post-install PID, an exact user0 service
  record, explicit `isForeground=true` with non-zero foregroundId, and an exact
  user0 accessibility ConnectionRecord. Label-only, enabled-only, another user,
  another process, suffixed components and unrelated foreground markers fail.
- Logcat uses a decimal device-epoch TIME selector, then requires a finite epoch
  strictly after the phase's device watermark, the exact post-install PID,
  priority `I`, tag `CompanionSync:`, and one of the two complete emitted
  literals. Prefix/suffix/quoted messages, wrong priorities/tags/PIDs,
  non-finite timestamps and overlapping duplicates are rejected without
  clearing logcat. Host epoch bounds are retained separately for server journal
  context, so host/device clock skew and a local-midnight transition cannot
  admit maintenance-window events into post-maintenance heartbeat evidence.
- Server journal evidence remains `targetAttribution=false`; it is contextual
  interval evidence and cannot prove which device generated an event.

## Verification

Commands used the main repository's existing Python environment read-only:

1. Focused harness tests: `65 passed in 0.08s`, exit `0`.
2. Harness plus shared device-lock regression: `87 passed in 6.48s`, exit `0`.
3. Python `compileall` for both harness scripts and the focused test: exit `0`.
4. Ruff on both harness scripts and the focused test: `All checks passed`, exit `0`.
5. A bounded read-only parser smoke on `b0644fb5` confirmed the currently
   observed exact PID/service/accessibility shapes and that decimal-epoch
   `logcat -T TIME` exits `0`. Raw log lines were not retained.

Machine-readable readiness evidence is in `v5-harness-readiness.json`.

## Remaining Gate

Planner review must explicitly remove the real-write HOLD before the committed
harness may acquire `DEVICE:b0644fb5`, enter maintenance or attempt the one
authorized install. No repository integration or push is performed here.
