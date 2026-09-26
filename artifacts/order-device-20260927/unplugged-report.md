# OnePlus Unplugged Order Attempt And Admission Fix

## Runtime Result

User confirmed USB disconnection. Local `adb devices -l` returned an empty
device list. No subsequent ADB shell, install, navigation or device capture was
used in this attempt.

Cloud preflight at `2026-09-26T16:22:23Z` observed OnePlus's authenticated request
at `16:22:21.927468Z`, network WIFI, charging=false, accessibilityEnabled=true,
runnerState=IDLE and orderDeliveryProtocol=order-delivery/1. Global leases,
nonterminal tasks, schedules, preview and debug sessions were idle.

Normal operator authentication submitted exactly one read-only request:
device `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`, SOLD, maxRows=10, screens=1,
protocol order-delivery/1. No custom steps or write operations were dispatched.

- Run: `0e7c9c70-c2c2-5402-99ec-4f99e7373e21`.
- Task: `26bb23ba-362b-402b-9607-a4300d22c59b`.
- Started `2026-09-26T16:24:07.365114Z`.
- Failed `2026-09-26T16:24:08.361698Z`, `TASK_CONTRACT_REJECTED`.
- Attempt=1, currentStep=null, lastSequence=0, no task events.
- Delivery=BLOCKED/TASK_FAILED, no SCREEN or COMPLETE receipts.
- Task count 376 -> 377; outgoing message count unchanged at 23.
- Device lock fencing10 acquired `16:23:55Z`, released `16:30:22Z`.
  Subsequent cloud idle check and local FREE check passed.
- No retry, second collection, phone reconnect, sending, publishing, delisting
  or trade action. The failed task remains as evidence.

**Passed:** device-independent cloud claim and terminal failure reporting.
**Not passed:** real order collection, reliable delivery, webpage result,
network recovery, three-device acceptance. A network-connected phone is not
equivalent to a successful business workflow.

## Reproduced Defect

CloudTaskClient retains the negotiated `orderDelivery` sidecar. The service's
fresh-claim admission still called the strict legacy AutomationTaskParser,
which rejects that extra field. Normal execution and resume already used the
order-aware parsers, but the earlier admission check prevented reaching them.
The cloud task had valid durable metadata and no nested command.

The production admission block was extracted without semantic changes into
`acceptedClaimDeviceId`, called directly by CompanionSyncService. Five new
admission tests first ran against the old parser: **5 tests, 1 failure**.
The positive durable-claim test failed with `Unknown or missing task field`,
reproducing the same structural failure without operating a phone.

The helper now uses the existing `orderAwareCommandOrNull` and
`parseOrderAwareTask`. It keeps device checks and existing durable identity
validation, and does not relax the legacy parser's closed-field policy.
Tests cover valid durable admission, legacy compatibility, missing account
identity, mixed command/unknown fields and wrong device identities.
The service's enqueue and terminal failure behavior is unchanged.

## Verification And Artifact

```sh
./build-external.sh --offline :app:testBusinessAcceptanceUnitTest --tests '*OrderDeliveryIntegrationTest.serviceAdmission*' --console=plain
./build-external.sh --offline :app:testBusinessAcceptanceUnitTest :app:testDebugUnitTest :app:assembleBusinessAcceptance :app:lintBusinessAcceptance --console=plain
```

First command before the fix: exit1 as expected (`admission-red.log`).
Second command after the fix: exit0 (`admission-green.log`).

- BusinessAcceptance: 1270 tests, 173 suites, zero failures/errors/skips.
- Debug: 1284 tests, zero failures/errors/skips.
- Lint: 19 warnings, no Error/Fatal.
- APK package: `com.company.cloudctl.companion`.
- VersionCode=3, versionName=`0.1.0-business-acceptance.3`.
- SHA256: `c6a39272612bf507c70d0a5f3084162b87770d445fcecedb4e659be5cd4a9005`.
- Signing certificate unchanged:
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`.
- Requested permissions and updater/recipe trust unchanged; non-debuggable;
  HEARTBEAT_DIAGNOSTIC=false, IM_UPLOAD_HOLD_ALLOWED=false.
- Compiled APK inspection confirms both order-aware parser calls in the helper
  and the actual CompanionSyncService call to that helper.
- Existing phase-one test/debug signing remains; this is not a hardened
  production release.

Independent read-only review agreed with the cause and bounded correction.
Runtime correctness on the phone still requires installing v3 and a new,
explicitly scoped read-only attempt; unit tests do not replace that gate.

## Manual Network Update

The verified APK was added to the existing authenticated static download area:
`/cloudctl-mobile/downloads/cloudctl-companion-v3-c6a39272.apk`.
Unauthenticated GET=401; authenticated GET=200; downloaded bytes=50,937,988 and
SHA256 matches. No API/Web/Nginx restart or configuration change.

This is a **manual browser download and user-confirmed package replacement**.
It was not marked CLEAN, admitted, assigned or installed through the automatic
APK release pipeline. The checked configuration reported zero analysis public
keys; automatic admission was not attempted or bypassed with fabricated reports.
No signing key or credential was placed in the download URL.

The phone still has v2 until the user installs v3 over it, without uninstalling
or clearing data, and reopens Companion. ADB remains unnecessary for this
update and the next business attempt.

Evidence: `artifact-v3-summary.json`, `manual-update-v3.json`,
`unplugged-progress.jsonl`, and the two test logs. Raw operator task views and
private operational state remain outside Git. O10 remains
**IN_PROGRESS / DEVICE_WAIT**.
