# P09 single-shot window and observability hardening

Completed at: 2026-09-16 04:25 CST (Asia/Shanghai)

This checkpoint changed source code and JVM tests only. No APK was built or installed, no device was connected, no API write was made, and task `a25549e5-145a-4da0-83d8-1e0a8355002a` and its ledger were not modified. The task remains `RECONCILING` with operator decision `KEEP_WAITING` and must not be retried.

## Changes

- Semantic delete confirmation now stops before `STEP_SUCCEEDED`. The controlled ledger's `UNKNOWN`/reconciliation state remains the only authority, and no later screenshot or completion log executes.
- `tapOnce` is restricted to a verified `GuardedDialogAction` on `rootInActiveWindow`.
- The service captures and validates active-window snapshots before refresh, after refresh, and immediately inside the dispatch runnable.
- Package, window ID, guarded candidate structure, visibility/enabled/clickable state, and action bounds must remain stable. Any change fails before dispatch.
- A failed active-root refresh fails before dispatch.
- Cancellation is checked before final validation and again immediately after final validation. Cancellation before submission yields zero gestures.
- The dispatch boundary calls Android `dispatchGesture` at most once. There is no action fallback or retry.
- Correlated logs record the evidence ID, phase, window ID, package, candidate counts, selected bounds/center, immediate dispatch acceptance, callback `COMPLETED`/`CANCELLED`, and callback latency.
- Log wording does not call Android gesture completion a business success. Deletion remains unconfirmed until operator reconciliation.

Changed and added files:

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/LocalAutomationExecutor.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/CloudCtlAccessibilityService.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/SingleShotGestureGuard.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/SingleShotDispatchBoundary.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/automation/XianyuMaintenanceGateRoutingTest.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/automation/SingleShotGestureGuardTest.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/automation/SingleShotDispatchBoundaryTest.kt`

## Verification

- Focused single-shot, gate routing, and durable ledger tests: passed.
- Full Android JVM suite: 57 suites, 392 tests, 0 failures, 0 errors, 0 skipped.
- `git diff --check`: passed.
- Independent static review initially found false `STEP_SUCCEEDED`, a missing final window recheck, and cancellation windows. All high/medium findings were fixed and the final re-review reported no new high- or medium-severity regression.
- The project has no `ktlintCheck` Gradle task, so no ktlint result is claimed. Kotlin compilation and tests passed; the only compiler warning was the pre-existing Android deprecation of `canRetrieveWindowContent`.

## Residual risk

Android does not expose an atomic primitive that locks another app's window while submitting a screen-coordinate accessibility gesture. The final active-window validation and `dispatchGesture` call now occur consecutively in the same main-thread runnable with no app-side queue hop, which minimizes but cannot mathematically eliminate an external window change between the last read and submission.

No device acceptance is claimed. A future real deletion still requires resolution of the current UNKNOWN plus a new explicit authorization for the exact object and parameters.
