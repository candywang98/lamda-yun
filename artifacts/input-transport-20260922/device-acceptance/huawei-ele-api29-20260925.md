# ELE Android 10 isolated input verification

- Audited: 2026-09-25 (Asia/Shanghai)
- Device: Huawei `ELE-AL00`, ADB serial `GBGDU19830002425`, Android 10 / API 29
- Scope: local isolated input harness only; no cloud task, business app, CAPTCHA handling, or platform action

## Installation

- `mobile/input-harness/app/build/outputs/apk/debug/app-debug.apk` built successfully after setting `ANDROID_HOME=/opt/homebrew/share/android-commandlinetools` without writing repository `local.properties`.
- Companion `:app:assembleDebugAndroidTest` built successfully.
- Huawei normal installer confirmation was completed through the system UI, including the `继续安装` and `完成` screens.
- Installed packages confirmed:
  - `com.company.cloudctl.companion.debug`
  - `com.company.cloudctl.inputharness`
  - `com.company.cloudctl.companion.debug.test`

## Execution result

- The input harness foreground activity was launched explicitly and its UI tree showed only the empty `isolated field` EditText.
- The fixed command was run:

  `adb -s GBGDU19830002425 shell am instrument -w -r -e class com.company.cloudctl.companion.automation.DiagnosticInputDeviceTest com.company.cloudctl.companion.debug.test/androidx.test.runner.AndroidJUnitRunner`

- `debugPackageIsBesideProductionAndHasNoClaimComponents` passed.
- `fixedFixtureIsVerifiedOnceWithoutChangingTheKeyboard` entered but did not return a result on repeated runs. No `INPUT_VERIFIED`, `DIAG_INPUT`, commit count, or proof hashes were produced.
- During the attempts the debug service process entered `D` state and `dumpsys accessibility` showed `Bound services:{}` with a dead/rebinding service. No field write was accepted as evidence.

## Compatibility finding

- API 29 selects `InputChannel.MANUAL_IME` in `InputRoutePolicy` and requires `CloudCtlInputMethod` to be enabled and selected.
- The installed `com.company.cloudctl.companion.debug` manifest intentionally removes `CloudCtlInputMethod`, `MainActivity`, network permissions, and `CompanionSyncService`; it is a debug-only local executor package.
- Therefore this debug package is suitable for the isolated service boundary, but it cannot provide the API 29 input proof without the IME component. The implementation must not be altered or the result overstated just to force a pass.
- The missing IME is a confirmed API 29 compatibility gap, not a proven explanation for the observed process `D` state or instrumentation hang. No stack evidence established the hang's root cause.

## Cleanup and safety

- Production read-only occupancy remained zero before the device write: no active lease, no enabled schedule, and no active preview.
- ELE fencing `4` was released; final local device lock is `FREE`.
- At the end of the input attempt, the system UI switch appeared off but secure settings still contained the debug component and dumpsys still listed it under binding. A clean disable/unbind was not proven then. On the subsequent network-session preflight (2026-09-24 17:54–17:56 UTC), the enabled accessibility service list was empty; this later observation must not be backdated.
- No real platform app was opened and no message, CAPTCHA, task, upload, publish, delete, repricing, review, payment, or promotion action occurred.

## Acceptance status

- This is a real-device blocked attempt, not a pass.
- API 29 input acceptance remains incomplete after a blocked attempt. API 30–32 also needs the temporary IME path; the current debug package removes that IME too. API 33+ selects the accessibility input path, but still requires its own real-device proof.
- Input instrumentation is no longer a prerequisite for the user-authorized ELE cellular HTTPS heartbeat work.
