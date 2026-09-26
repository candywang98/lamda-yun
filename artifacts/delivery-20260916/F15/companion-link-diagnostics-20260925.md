# Companion link diagnostics

- Audited: 2026-09-25 (Asia/Shanghai)
- Scope: ADB-assisted device diagnostics and outbound Companion HTTPS heartbeat only
- Safety boundary: no platform app was opened; no task was created, claimed, executed, uploaded, published, deleted, repriced, reviewed, paid, or promoted
- Acceptance impact: F15/F16 remain `NOT_RUN`; this evidence does not satisfy real-device or external-platform acceptance

## Transport and device state

- ADB reported four online transports for three physical devices:
  - `APH0219624006517` (VOG-AL10)
  - `GBGDU19830002425` (ELE-AL00)
  - `b0644fb5` over USB and `192.168.5.6:5555` over Wi-Fi, both the same OnePlus 9R
- OnePlus Companion `0.1.0` was started through its launcher activity. Package state changed from `stopped=true` to `stopped=false`; `CompanionSyncService` is foreground and the runner remained `IDLE`.
- VOG Companion `0.1.0` was already running. Companion accessibility was enabled while preserving `com.sand.remotesupportaddon/.SmartService`.
- ELE did not have `com.company.cloudctl.companion` installed at the start of this run.

## HTTPS heartbeat evidence

- OnePlus logcat showed network validation, heartbeat payload with `accessibilityEnabled=true`, `runnerState=IDLE`, `safetyBarrier=NONE`, and `Heartbeat successful`.
- VOG logcat showed two consecutive successful heartbeats on `network=Cellular`:
  - `2026-09-25 00:31:27`: validated, sent, successful
  - `2026-09-25 00:31:47`: validated, sent, successful
- The successful heartbeat proves the enrolled Companion can authenticate to the configured cloud endpoint over outbound HTTPS on cellular data. It does not prove task claim, execution, or platform acceptance.

## Occupancy and local lock checks

- Production read-only snapshot at `2026-09-25 00:29` Asia/Shanghai equivalent:
  - `active_leases=0`
  - `expired_uncanceled_leases=0`
  - `enabled_schedules=0`
  - `active_previews=0`
  - all `mobile_task` rows were historical terminal states
- The expired OnePlus local lock at fencing `3` was broken under the SOP after the production and device checks. A new fencing `4` lock was acquired for diagnostics only and then released; final state is `FREE`.

## Remaining blocker

- ELE remained ADB-online but its remote shell did not return even for `echo`, `df`, or package queries. Both regular `adb install -r` and `adb install --no-streaming -r` timed out; `adb reconnect device` and the device-side USB-mode request did not restore the shell. No reboot, data clear, or destructive recovery was attempted.
- ELE therefore remains without Companion installed and without device-side permission configuration. It needs a physical/ADB transport recovery before installation can be retried.
- Q13/Q15 hardware-count requirements and F15/F16 external authorization/material/account evidence remain unchanged.

## Follow-up after device recovery

- After the user-side recovery and a host-side ADB server restart, ELE's no-input shell probe returned `shell_ok` and all three physical devices remained listed as online.
- The file/sync channel is still blocked: regular `adb install -r`, `adb install --no-streaming -r`, `adb push`, and a minimal shell-stdin transfer all timed out. The APK was not installed; no Companion service or accessibility setting was changed on ELE.
- A short-lived ELE fencing `1` diagnostic lock was acquired for the install attempt and released after the failed transfer. Final local lock state is `FREE`.

## Package variant clarification

- ELE identity is `HUAWEI / ELE-AL00 / Android 10`.
- The installed APK is the Gradle debug variant `com.company.cloudctl.companion.debug`, version `0.1.0`.
- The debug manifest intentionally removes the enrollment Activity, network permissions, boot receiver, and `CompanionSyncService`; it retains only the accessibility service for local diagnostics.
- `com.company.cloudctl.companion.debug/com.company.cloudctl.companion.automation.CloudCtlAccessibilityService` is enabled and bound on ELE.
- No heartbeat is expected from this debug package. Cloud-link validation requires the release/acceptance variant and must remain separately recorded from local input verification.
