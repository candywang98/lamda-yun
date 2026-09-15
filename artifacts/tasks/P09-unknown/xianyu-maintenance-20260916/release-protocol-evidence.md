# P09 claim-time accessibility-disconnect safe release protocol

Completed at: 2026-09-16 (Asia/Shanghai)

Source-code and test work only. No APK build/install, no deployment, no device connection, no production API writes. Task `a25549e5-145a-4da0-83d8-1e0a8355002a` remains `RECONCILING` with operator decision `KEEP_WAITING` and was never touched.

## Frozen protocol (R20260916-P09-18/19)

- A companion may release a freshly claimed task back to the cloud queue ONLY while the server still sees `status=CLAIMED, business_state=PREFLIGHT` — that is, before the first task heartbeat.
- The first successful task heartbeat is the execution boundary: after it the task is server-side `RUNNING` and can never be auto-released, only finished, paused, or reconciled.
- Release requires the current exact unexpired lease and reason `ACCESSIBILITY_NOT_ENABLED|ACCESSIBILITY_NOT_ACTIVE`.
- The server rejects release for `RUNNING`, `RECONCILING`, any `MobileActionCommitRow` (INTENT/UNKNOWN/APPLIED/NOT_SUBMITTED alike), and legacy `commitIntent` payloads.
- Client-side: only a successful server release settles the local copy (`RELEASED`); a failed release leaves `RELEASE_BLOCKED` — never executed, never locally requeued, never uploaded as `/fail`.
- Liveness exits (adversarial review findings B1/B2):
  - Blocked rows older than 5 minutes retire locally to `FAILED` with journal `BLOCKED_RETIRED_TIMEOUT` and no outbox event, so an operator-cancelled or abandoned task can never wedge the device; a late redelivery lands on the existing terminal replacement-lease path.
  - The claim loop claims only when accessibility readiness `capture()` is `Ready`, so a disabled runtime produces zero claim/release churn.

## Changed files

Backend (implemented by isolated subagent, reviewed):

- `services/control-api/src/cloudctl_api/mobile_routes.py`
- `services/control-api/src/cloudctl_api/mobile_schemas.py`
- `services/control-api/src/cloudctl_api/mobile_service.py`
- `packages/api-contracts/openapi.json`
- `tests/integration/test_platform_tasks.py`

Android (completed in the main session after the delegated agent died of a provider auth failure; its partial edits were audited, one wedge defect fixed, wiring finished):

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/FreshClaimExecutionCoordinator.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/AutomationStore.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/CloudTaskClient.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/DutyController.kt` (comment only)
- Tests: `FreshClaimExecutionCoordinatorTest.kt`, `FreshClaimExecutionBoundaryTest.kt`, `AutomationStoreReleaseTest.kt`, `CloudTaskClientTest.kt`

## Verification

- Backend focused release tests: 8 passed; platform-task module 23 passed; reconciliation hardening + OpenAPI contract run: 44 passed.
- Android full JVM suite: 60 suites, 409 tests, 0 failures, 0 errors, 0 skipped.
- Independent adversarial review #1 found two blocking liveness defects (permanent wedge after server-side cancel; unbounded claim/release churn) plus three mediums. All were fixed (5-minute blocked-row retirement; pre-claim readiness gate; `includeAccessibility` TOCTOU; heartbeat attempts 2; comment) and review #2 verified each closed with no new blocking issues.

## Accepted consequences (documented by review #2)

- A blocked task whose device stays unreachable over 5 minutes is terminally failed on redelivery instead of retried — strictly more generous than the previous immediate `/fail`.
- Pathological double-timeout initial heartbeats can still fence into `START_BLOCKED`, which now recovers via redelivery or retirement.

No device acceptance is claimed. GATED semantics are untouched; the UNKNOWN task stays operator-held.
