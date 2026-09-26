# Authorized OnePlus V3 In-Place Update

The user reconnected USB and explicitly asked the controller to perform the
replacement. Only `b0644fb5` / OnePlus LE2100 was attached. The installed
package was versionCode2. Cloud preflight was idle; the previous failed order
task was terminal. No scrcpy/LAMDA writer was observed.

## Installation

- `adb install -r` succeeded once, between `2026-09-26T16:46:24Z` and
  `16:46:29Z`. No uninstall, data clearing, force-stop, rebind or system
  permission modification.
- Installed package: `com.company.cloudctl.companion`.
- Installed version: `0.1.0-business-acceptance.3`, versionCode3.
- Pulled installed APK SHA256:
  `c6a39272612bf507c70d0a5f3084162b87770d445fcecedb4e659be5cd4a9005`.
- Old and new APK certificate SHA256:
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`.
- All 12 parsed permission entries, including repeated entries for different
  user sections, match before/after. Four secure settings and original first
  install timestamp also match.
- The prior v2 APK and package/settings metadata were backed up privately.
  Both builds are non-debuggable: private SQLite contents were not re-read.
  This is not a byte-for-byte post-install database preservation claim.

## Cloud And Cleanup

At `2026-09-26T16:46:30.267553Z`, cloud received
`companionVersion=0.1.0-business-acceptance.3`, `accessibilityEnabled=true`,
`runnerState=IDLE`, `orderDeliveryProtocol=order-delivery/1`.
The original active binding ID and credential digest are unchanged.

Local exact-serial lock fencing11 was released at `16:46:31Z`.
Maintenance false/version6 -> true/version7 -> false/version8, through the
normal operator API with expectedVersion checks. Final cloud verification at
`16:46:33Z` confirmed idle, unchanged binding, receiveOnly=true, NOTIFICATION
mode, 377 tasks and 23 outgoing messages.

No new order task, message send, publishing, delisting or trade operation was
performed. The two Huawei phones were not updated or operated.

## Remaining Gate

The earlier manual-download wait is superseded: **v3 is now installed**.
USB was connected for this authorized update. Real order collection and
delivery on v3 still require a new cloud-only attempt after the user unplugs
again and keeps wireless ADB disabled. No claim of continuous background
stability or three-device acceptance is made.

Evidence: `v3-install-summary.json`, `v3-cloud-verify.json`,
`v3-lock-released.json`; software verification remains in
[the admission-fix report](unplugged-report.md).
