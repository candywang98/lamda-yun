# P14 hard-accept knife 2026-09-09 — ACCEPTED

## Status: CLOSED for idlefish-FG + live executor expected/actual

This is a **new** knife, distinct from the stalled `knife-20260909-hard-accept-idlefish-fg.md` (that card forbade any probe). Expert later authorized **exactly one** `device.probe_capabilities.v1`. That single POST is this closeout. No second probe.

- Device OnePlus 9R serial `b0644fb5` id `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`
- Companion pid **16987** throughout (pre / post); a11y includes `CloudCtlAccessibilityService`
- Ban kept: no 2nd probe / no rewrite `7f292679` / no disable-sig / no auto-publish / no xianyu / no 65000 / no secrets.xml / no Bearer / no git-revert / no P15
- Signatures stayed on. Recipe freeze on this probe is still builtin `901f795b` / `recipe-device-probe-1` (signed `825921a4` remains on disk, unused)

## Three live criteria (all met)

### 1. Idlefish was foreground **before** the probe was sent

Local clock `2026-09-09 09:19:13 +0800` immediately before POST (`hard-accept-probe-20260909/fg-before-probe.txt` + `dumpsys-activities-before-probe.txt`):

```
topResumedActivity=ActivityRecord{e1b9196 u0 com.taobao.idlefish/.maincontainer.activity.MainActivity t1825}
mCurrentFocus=Window{d48e2f u0 com.taobao.idlefish/com.taobao.idlefish.maincontainer.activity.MainActivity}
mFocusedApp=ActivityRecord{e1b9196 u0 com.taobao.idlefish/.maincontainer.activity.MainActivity t1825}
```

Same idlefish MainActivity also captured at 09:13:45, 09:17:08, 09:18:45. Companion was **not** FG at send time.

### 2. This probe’s executor log has concrete expected vs actual packages

- New task `0d36fe3f-7a54-48aa-bfe1-4fbb36b5407e`
- POST `201` at `2026-09-09T01:19:13.570831Z` (`idempotency-replayed: false`)
- `SUCCEEDED` attempt=1 controlEpoch=97
  - `startedAt=2026-09-09T01:19:14.379606Z`
  - `completedAt=2026-09-09T01:19:17.957374Z`
  - `result={outcome:ok, resultType:DeviceProbeResult, schemaVersion:1}`
- Tenant: `X-Tenant-Id=00000000-0000-7000-8000-000000001111`

Live logcat after `logcat -c` (pid 16987, `hard-accept-probe-20260909/logcat-expected-actual.txt`):

```
09-09 09:19:13.514 CloudCtlExecutor: launchTargetApp targetPackage=com.company.cloudctl.companion xianyu=com.taobao.idlefish activeWindow=com.taobao.idlefish
09-09 09:19:14.528 CloudCtlExecutor: launchTargetApp after wait expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
09-09 09:19:14.528 CompanionSync:     launchTargetApp after wait expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
09-09 09:19:14.542 CloudCtlExecutor: ensureReady expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
09-09 09:19:14.542 CompanionSync:     ensureReady expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
```

Reading of those two values:

- **expected** = command `targetPackage` = `com.company.cloudctl.companion` (probe builtin app; **not** idlefish)
- **actual** (at launch) = accessibility active window `com.taobao.idlefish`
- **actual** (after `waitUntilPackage`, ~1.0s) = `com.company.cloudctl.companion`
- `ensureReady` then saw expected=actual=companion → no `WRONG_ACTIVE_PACKAGE`

This is the path `ca211913` never hit (companion already FG; wait skipped; no `expected=`/`actual=` lines). After this run, FG is companion MainActivity (`fg-after.txt`) — expected, because launch succeeded.

### 3. `7f292679` still FAILED; signatures not turned off

GET after this probe (`GET_7f292679-after.json`):

- id `7f292679-aa07-4908-81b4-07f7dbcb891e`
- `state=FAILED` `runnerStatus=FAILED`
- `errorCode=WRONG_ACTIVE_PACKAGE`
- `detail=Companion terminated the task safely`
- `attempt=1` `controlEpoch=95`
- `completedAt=2026-09-08T09:41:26.095338Z` (unchanged)

Did **not** redispatch or rewrite it. Did **not** disable signature verification. Did **not** auto-publish signed `825921a4` over builtin `901f795b`.

## What this proves (and what it does not)

The 2026-09-08 wait-patch in `CloudCtlAccessibilityService.kt` works on the real idlefish-in-front race:

1. `launchTargetApp(companion)` while idlefish holds focus
2. executor waits until active window == targetPackage
3. `ensureReady` logs `expected=` vs `actual=` and proceeds

Foreground-package check stays **on**. Probe success here is **not** “idlefish is the target”; the intended target remains companion. Idlefish FG is the **starting** condition the hard-accept demanded.

Install+claim (`knife-20260908-syncRecipes-install.md`) and the WRONG_ACTIVE code closeout (`knife-20260908-wrong-active-package.md`) stay closed. This card only supplies the missing live executor evidence.

## POST (exactly once; do not replay)

```
POST https://43.133.243.154.sslip.io/api/v1/platform-tasks
X-Tenant-Id: 00000000-0000-7000-8000-000000001111
X-User-Id:   00000000-0000-7000-8000-000000000222
```

Proven response headers (`POST_platform-tasks.headers`): `HTTP/2 201`, `idempotency-replayed: false`, `x-request-id: p14-hard-accept-probe-20260909`. Body (`POST_platform-tasks.body.json`): `{deviceId, accountId, expectedBindingVersion:1, commandType:device.probe_capabilities.v1, parameters:{}}`. No spoofed `targetPackage`. Do not POST again.

## Evidence directory

`artifacts/tasks/P14-recipe-publish/hard-accept-probe-20260909/`

- `fg-before-probe.txt` / `dumpsys-activities-before-probe.txt` / `fg-before-post-local.txt` — idlefish FG at send
- `POST_platform-tasks.body.json` / `.headers` / `.json` / `.curl-w.txt` — single 201
- `GET_0d36fe3f.json` / `GET_0d36fe3f-final.json` — SUCCEEDED DeviceProbeResult
- `GET_7f292679.json` / `GET_7f292679-after.json` — still FAILED / WRONG_ACTIVE_PACKAGE
- `logcat-cleared-at.txt` / `logcat-after-complete.txt` / `logcat-expected-actual.txt`
- `fg-after.txt` / `dumpsys-activities-after.txt` / `companion-pid-after.txt` (still 16987)

## Ban reminder

No second probe. No rewrite `7f292679`. No disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git revert / Ed25519 reopen / P15.

## Rollback

None this card. APK/wait-patch remains the 2026-09-08 repair (`repair-wrong-active/repair.patch`). Workspace still dirty; this card did not commit.
