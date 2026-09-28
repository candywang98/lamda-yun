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

## Remaining Gates

Certificate-compatible APK and signature checks, OnePlus accessibility recovery,
OnePlus7 tenant disposition, Huawei account binding, actual device collections,
network/process fault cases and final disconnected acceptance remain pending.
Synthetic tests and ADB connectivity do not satisfy those gates.
