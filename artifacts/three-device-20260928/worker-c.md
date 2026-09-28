# Worker C: Verified Cloud Leaf Transition

## Delivery

- Work item: 1D, verified cloud leaf certificate transition.
- Frozen contract: `contracts/phase1/cloud-pin-transition-20260928.md`
  (`Verified Cloud Leaf Transition / 20260928.1`).
- Baseline: `286e11fca04bf5b92da8ac0f2babebbee4e847a3`.
- Branch: `agent/sol-pin-transition-20260928`.
- Delivery commit: reported in the controller handoff because this evidence file
  is part of that commit.
- No device, ADB, SSH, production network, deployment, install, signing,
  release-version or private-key operation was performed.

## Implementation

- Preserves exact enrolled leaf-pin matching for a valid 64-character
  lowercase SHA-256 pin.
- Adds one bounded transition: the verified successor leaf is accepted only
  when the actual URI host is exactly `43.133.243.154.sslip.io`, the configured
  pin is exactly the frozen old leaf pin, and the successor leaf passes X.509
  validity checks at handshake time.
- Uses `chain.first()` only. Empty chains, malformed pins, unknown pins,
  unknown leaves, successor certificates presented only as intermediates,
  wrong or absent host context, and expired or not-yet-valid successors fail
  closed.
- Raw HTTP and file downloads pass their parsed URI host into the shared TLS
  configuration. Live WebSocket setup parses the same real base-URL host and
  uses the same trust manager. Existing SNI, literal-IP routing and OkHttp
  default hostname verification remain in place; there is no CA fallback,
  permissive hostname verifier, HTTP fallback or network-learned trust.
- Does not modify enrollment, persisted binding/token/device/account/pin data,
  queue rows or `orderConnectionScope` inputs.

## Owned Files

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/PinnedHttpsTransport.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/VerifiedCloudLeafPinPolicy.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/live/LiveSessionController.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/network/VerifiedCloudLeafPinPolicyTest.kt`
- `artifacts/three-device-20260928/worker-c.md`

## Verification

All Gradle commands used `--offline` and
`JAVA_TOOL_OPTIONS=-Drobolectric.dependency.repo.url=file:///Users/wangziheng/.m2/repository`.
The successful runs also set
`ANDROID_HOME=/opt/homebrew/share/android-commandlinetools` and the same
`ANDROID_SDK_ROOT`.

1. `./gradlew --offline :app:testDebugUnitTest --tests com.company.cloudctl.companion.network.VerifiedCloudLeafPinPolicyTest`
   without an SDK environment: exit 1 before compilation, 0 tests; isolated
   worktree had no `local.properties` and no Android SDK environment variable.
2. Same command with the SDK environment: exit 0, 7/7 tests passed.
3. `./gradlew --offline :app:testDebugUnitTest --tests com.company.cloudctl.companion.network.VerifiedCloudLeafPinPolicyTest --tests com.company.cloudctl.companion.network.CloudTaskClientTest --tests com.company.cloudctl.companion.features.xianyu.orders.OrderDeliveryIntegrationTest`:
   exit 0, 49/49 tests passed (7 + 7 + 35).
4. `./gradlew --offline :app:testDebugUnitTest`: exit 0, 1294/1294 tests
   passed across 174 suites; 0 failures, 0 errors, 0 skipped.
5. `./gradlew --offline :app:testHeartbeatDiagnosticUnitTest :app:testBusinessAcceptanceUnitTest`:
   exit 1 after the heartbeat-diagnostic task ran 1283 tests with 3 failures in
   unrelated `ImNotificationIntakeTest` assertions; Gradle stopped before the
   business-acceptance task. No certificate-transition test failed.
6. `./gradlew --offline :app:testHeartbeatDiagnosticUnitTest --tests com.company.cloudctl.companion.network.HeartbeatDiagnosticTransportTest`:
   exit 0, 6/6 tests passed.
7. `./gradlew --offline :app:testBusinessAcceptanceUnitTest --tests com.company.cloudctl.companion.network.BusinessAcceptanceTransportTest`:
   exit 0, 3/3 tests passed.
8. `git diff --check`: exit 0.

Synthetic `X509Certificate` fixtures use generated test bytes only. No real
certificate or private key is embedded in the tests.

## Remaining Gates And Risks

- Controller review and rebase/merge are required because the controller main
  branch advanced independently from this frozen baseline.
- Release signing, version selection, APK build/install and any device or
  production acceptance remain controller-owned and were not attempted.
- No live TLS handshake was performed. Software evidence verifies the frozen
  fingerprint/host policy and shared call paths, not production availability.
- The full heartbeat-diagnostic suite retains three unrelated IM intake test
  failures described above; its focused transport suite passes.
- This bridge covers only the frozen successor. Any later unlisted certificate
  rotation still fails closed and requires a reviewed application update.
