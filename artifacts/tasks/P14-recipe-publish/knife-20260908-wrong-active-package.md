# P14 closeout 2026-09-08 (WRONG_ACTIVE_PACKAGE)

## Status: CLOSED for post-claim WRONG_ACTIVE_PACKAGE

- Device OnePlus 9R serial `b0644fb5` id `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`
- Companion pid 16987 (lastUpdate 2026-09-08 18:45:42, FGS + a11y alive)
- Ban kept: no disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git-revert / Ed25519 reopen
- Did **not** flip `7f292679` FAILED→success; did **not** redispatch it

## Three live criteria

1. New probe left FAILED/WRONG_ACTIVE_PACKAGE
   - `ca211913-bf66-4692-b2cd-d8610b4f2561` `SUCCEEDED` attempt=1
   - `startedAt=2026-09-08T11:10:53.920770Z` `completedAt=2026-09-08T11:10:56.674587Z`
   - `result={outcome:ok, resultType:DeviceProbeResult, schemaVersion:1}`
   - Tenant that owns the device: `X-Tenant-Id=00000000-0000-7000-8000-000000001111` (not `…000111`)
2. Foreground-package check compared these two values
   - Source (`CloudCtlAccessibilityService.ensureReady`): `expected=$targetPackage` vs `actual=$root.packageName`
   - Live 17:41:24 ATM on the FAILED window: expected `com.company.cloudctl.companion`, actual `com.taobao.idlefish` (~117ms after companion launch, idlefish stole focus)
   - New 19:10 probe did not emit WRONG_ACTIVE (companion already foreground; check passed)
3. Root cause (see below). Foreground-package check stays on.

Install+claim three criteria from `knife-20260908-syncRecipes-install.md` still hold: signed recipe dir present (`825921a4` / `recipe-device-probe-signed` / `phase1-recipe-1`); `7f292679` remains `FAILED`/`WRONG_ACTIVE_PACKAGE`/`attempt=1`.

## Root cause (foreground race, NOT leftover builtin recipe)

Overturned leftover from install knife: “command still points at builtin 901f795b while signed 825921a4 is installed” is **not** why probe failed.

- Both `7f292679` (FAILED) and `ca211913` (SUCCEEDED) freeze the same recipe: `versionId=recipe-device-probe-1` `sha256=901f795b2512891cd5ee08162626d0ad6a1c92ad9d7b922516c626f9d6f155b4`
- `CommandV1.packages` has **no** mapping for `device.probe_capabilities.v1`, so `targetPackage` is whatever the command sent (companion), not idlefish
- Builtin recipe `app=com.company.cloudctl.companion`
- Signed on-disk package `01a07f6d-…` remains for Path C install; probe execution used the builtin hash. That mismatch is leftover, not this failure

What actually failed at 17:41:24:

1. `launchTargetApp(companion)` started `MainActivity` (`am start` / launch intent)
2. It did **not** wait for the accessibility active window to become companion
3. ATM: companion switched to background, `com.taobao.idlefish` to foreground (~117ms)
4. `ensureReady` then saw `actual != targetPackage` → `ExecutorFailure("WRONG_ACTIVE_PACKAGE")` in a ~1.2s window (`startedAt` 09:41:24.891Z → `completedAt` 09:41:26.095Z)

Foreground-package check is correct. Do not disable it.

## Fix

Code (`CloudCtlAccessibilityService.kt` only):

- `launchTargetApp` is `suspend` and calls `waitUntilPackage(targetPackage)` after `startActivity`
- `ensureReady` / wait timeout / after-wait log `expected=` vs `actual=` on TAG and `CompanionSync`
- Check not disabled

Live operational proof: with companion already in the foreground, a **new** probe (`ca211913`) completed. Same builtin recipe, same check.

Patched APK installed 18:45:42 (`app-debug-resigned.apk`, cert SHA-256 `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`). 19:10 companion logcat did not reprint `expected=`/`actual=` because the new probe never hit the mismatch path.

## Not this closeout

- Do not rewrite `7f292679`
- Do not auto-publish / replace builtin 901f795b with signed 825921a4
- Do not reopen Ed25519 / download header / Kotlin bytes
- Seoul POST must use tenant `…001111`; `…000111` 404s `device was not found`

## Rollback

`repair-wrong-active/repair.patch` + pre-install APK/certs under the same dir. Workspace dirty; no full-repo revert/commit by this repair.
