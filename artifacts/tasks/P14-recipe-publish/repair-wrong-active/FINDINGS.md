# WRONG_ACTIVE_PACKAGE repair findings (2026-09-08) — closed

Correction vs earlier draft: `7f292679` recipe freeze is builtin `901f795b` / `recipe-device-probe-1`, **not** signed `825921a4`. Same freeze on the succeeding new probe. Builtin leftover is not the fail path.

## Status
Code patched + unit tests green. Resigned APK installed 18:45:42 (cert 667ebab…). New probe `ca211913` SUCCEEDED. `7f292679` left FAILED.

## Root cause (live 17:41:24 on b0644fb5)
- Command `7f292679` targetPackage=`com.company.cloudctl.companion`, recipe `901f795b` / `recipe-device-probe-1`
- `launchTargetApp` started companion but did not wait; ATM still `com.taobao.idlefish` ~117ms later
- `ensureReady` then threw `WRONG_ACTIVE_PACKAGE` in a ~1.2s window
- Foreground-package check is correct and stays on

## Live proof
- New probe `ca211913-bf66-4692-b2cd-d8610b4f2561` SUCCEEDED 11:10:53–11:10:56Z DeviceProbeResult
- Same builtin recipe. Companion already foreground (am start before POST)
- Tenant `…001111` (not `…000111`)

## Patch (only CloudCtlAccessibilityService.kt)
- `launchTargetApp` → `suspend` + reuse `waitUntilPackage`
- `ensureReady` / wait timeout / after-wait log `expected=` vs `actual=` on TAG and `CompanionSync`
- Check not disabled

## Ban
No disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git revert / Ed25519 reopen.
Do not redispatch 7f292679 or flip FAILED→success.

## Closeout
`artifacts/tasks/P14-recipe-publish/knife-20260908-wrong-active-package.md`
Stop. Do not open next.
