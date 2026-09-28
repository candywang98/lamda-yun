# Worker: Claim Maintenance Recovery

## Delivery

- Frozen contract: `contracts/phase1/claim-maintenance-recovery-20260928.md`
  (`Claim Maintenance Recovery / 20260928.1`).
- Baseline: `29c4820d102c990eb36f20bf0fd80cc865b26d09`.
- Branch: `agent/sol-maintenance-recovery-20260928`.
- Delivery commit: recorded by the commit containing this evidence file.
- No ADB, SSH, device, production network, deployment, signing, version,
  identity, credential, schema or server operation was performed.

## Implementation

- Routes the production `CompanionSyncService.syncLoop` claim pass through a
  focused helper that catches `CloudHttpException` only around `client.claim()`.
- Defers only HTTP 409 whose body is a one-field JSON object with exact detail
  `device is in maintenance and cannot claim tasks`.
- Uses the existing bounded `SyncRetryPolicy.nextDelayMillis()` delay, then
  continues the sync loop without admitting a claim, mutating the local queue,
  finishing a task or executing a queued item.
- Keeps missing, wrong, null or extra detail fields, malformed JSON, wrong
  status, unrelated 409, and 401/403 on their existing exception paths.
- Keeps maintenance-shaped exceptions thrown by claim admission or local task
  execution on their existing paths; the exception is special only at the
  claim request boundary.
- Preserves the prior invalid-claim behavior: failed admission returns
  `ClaimRejected`, retains the existing reject enqueue/finish bookkeeping in
  the service callback, and skips local execution for that loop iteration.
- A later ordinary claim resumes the existing admission, enqueue and local
  execution path. A pass with no cloud claim still runs the existing local
  queue path.

## Owned Files

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/ClaimMaintenanceRecovery.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/service/ClaimMaintenanceRecoveryTest.kt`
- `artifacts/three-device-20260928/worker-maintenance.md`

## Verification

Every Gradle command ran from `mobile/companion` with `--offline --no-daemon`
and:

```text
JAVA_TOOL_OPTIONS=-Drobolectric.dependency.repo.url=file:///Users/wangziheng/.m2/repository
```

1. Test-first command:
   `./build-external.sh --offline --no-daemon :app:testDebugUnitTest --tests com.company.cloudctl.companion.service.ClaimMaintenanceRecoveryTest`:
   exit 1 during test compilation because the expected helper API did not yet
   exist; 0 tests executed.
2. First production wiring with the same command: exit 1 during compilation
   because `claimRequest` was initially scoped inside the network branch; 0
   tests executed. The scope was corrected before the first green run.
3. Initial focused suite with the same command: exit 0, 7/7 tests passed.
4. Focused suite after adding the required `acceptClaim=false` and
   admission/execution boundary regressions, with the same command: exit 0,
   9/9 tests passed; 0 failures, 0 errors, 0 skipped.
5. Adjacent regression command:
   `./build-external.sh --offline --no-daemon :app:testDebugUnitTest --tests com.company.cloudctl.companion.service.ClaimMaintenanceRecoveryTest --tests com.company.cloudctl.companion.service.SyncRetryPolicyTest --tests com.company.cloudctl.companion.service.BootStartupTest --tests com.company.cloudctl.companion.network.CloudHttpExceptionTest`:
   exit 0, 26/26 tests passed (9 + 4 + 12 + 1).
6. Full unit command:
   `./build-external.sh --offline --no-daemon :app:testDebugUnitTest`:
   exit 0, 1303/1303 tests passed across 175 suites; 0 failures, 0 errors, 0
   skipped. Gradle reported `BUILD SUCCESSFUL in 1m 28s` and 28 executed tasks.
7. `git diff --check`: exit 0.

The focused tests execute the same `runSyncClaimPass` call path used by
`CompanionSyncService.syncLoop`; they are not classifier-only tests. They prove
that an exact maintenance denial returns before the outer non-retryable error
path can call `stopSelf()`, and that non-matching or out-of-boundary exceptions
still propagate.

## Presence Evidence And Test Limit

- Source-level call-path evidence: `presenceJob` and `syncJob` are independent
  children of the service's supervisor scope. Exact maintenance denial is
  consumed inside the sync iteration and therefore does not reach the existing
  outer `CloudHttpException` branch that calls `stopSelf()` and destroys the
  service-wide scope.
- The JVM tests do not instantiate the complete Android Service lifecycle and
  do not directly observe `onDestroy` or the concurrently running
  `presenceLoop`. They must not be described as full service-lifecycle tests.
- Controller-reported device evidence is independent of this patch: after one
  normal launch following maintenance, v4 logged successful heartbeats at
  14:19:42, 14:20:03, 14:20:24 and 14:20:46 UTC on 2026-09-28, with 22 events
  through 14:27:10 UTC. This demonstrates recovery of the already-installed v4
  runtime; it is not acceptance evidence for this uninstalled source change.

## Remaining Gates And Risks

- Controller review and integration onto the advanced main branch remain
  required.
- APK build, install and an authorized maintenance-enter/exit acceptance run
  remain controller-owned and were not attempted.
- A Robolectric or instrumented lifecycle test that starts the actual service,
  injects the maintenance claim response and observes presence across the
  deferral would provide stronger direct evidence than the current JVM
  call-path coverage.
- The match is intentionally exact. Any server change to status, JSON shape or
  detail text remains fail-closed on the existing non-retryable path until a
  separately reviewed contract change is implemented.
