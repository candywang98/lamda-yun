# P14 hard-accept knife 2026-09-09 — STALLED

## Status: NOT ACCEPTED (scope gap, not a code revert)

Hard acceptance required idlefish foreground **and** executor `expected=` / `actual=` package evidence.
That executor path cannot be exercised without a **new probe**, which this card forbids.
Manual dumpsys that idlefish is in front is **not** an executor test.

## Card constraints (kept)

- Install+claim remains closed. Dead paths stay dead.
- No new probe. No P15. Do not rewrite `7f292679` FAILED / `WRONG_ACTIVE_PACKAGE` → success.
- Do not spoof `targetPackage`. Do not equate human FG observation with a successful executor run.
- No secrets.xml / Bearer export / signature disable / auto-publish / whole-repo revert-commit.
- Do not move idlefish or port 65000 as a “fix”.

## Live device (captured 2026-09-09 01:03:43 +0800)

- OnePlus 9R serial `b0644fb5` id `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`
- companion pid **16987**, lastUpdate 2026-09-08 18:45:42, FGS + a11y alive
- a11y enabled includes `com.company.cloudctl.companion/...CloudCtlAccessibilityService`
- heartbeat `runnerState=IDLE`, `accessibilityEnabled=true`
- signed recipe still on device: `files/recipes/versions/01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f/package.json` (825921a4…)

### Criterion (1) environment: idlefish IS foreground (human/ATM, not executor)

From `hard-accept-20260909/fg-now.txt` and dumpsys:

```
topResumedActivity=ActivityRecord{e1b9196 u0 com.taobao.idlefish/.maincontainer.activity.MainActivity t1825}
mCurrentFocus=Window{d48e2f u0 com.taobao.idlefish/com.taobao.idlefish.maincontainer.activity.MainActivity}
mFocusedApp=ActivityRecord{e1b9196 u0 com.taobao.idlefish/.maincontainer.activity.MainActivity t1825}
```

This satisfies “idlefish must be foreground” as **device state**. It does **not** satisfy executor hard-accept.

### Criterion (2) executor expected/actual: MISSING on the live patched APK

`adb -s b0644fb5 logcat -d -t 20000 -s CloudCtlExecutor:V CompanionSync:V` → `hard-accept-20260909/logcat-tags-live.txt`

| needle | present |
| --- | --- |
| `expected=` | no |
| `actual=` | no |
| `launchTargetApp` | no |
| `waitUntilPackage` | no |
| `WRONG_ACTIVE` | no |
| `CloudCtlExecutor` | no |

CompanionSync only heartbeats. No pending command / inbox. sqlite helper returned empty task tables on-device.

Patched source **would** emit the lines if a command ran:

- `CloudCtlAccessibilityService.kt:106-107` `launchTargetApp after wait expected=$targetPackage actual=$focused`
- `CloudCtlAccessibilityService.kt:149-153` `ensureReady expected=$targetPackage actual=$actual` and `WRONG_ACTIVE_PACKAGE expected=… actual=…`
- `CloudCtlAccessibilityService.kt:482-488` `waitUntilPackage timeout expected=$pkg actual=…`

Those lines are unreachable without claiming/running a command.

## Intended target semantics (do not spoof)

Issued command for `7f292679` (`hard-accept-20260909/command-7f292679.json`):

- `targetPackage`: **`com.company.cloudctl.companion`**
- recipe on the wire: 825921a4 / `01a07f6d-…` (server freeze on GET still shows builtin 901f795b / `recipe-device-probe-1`; that leftover is **not** the fail path)

Probe intended target is companion, **not** idlefish. Idlefish-in-front is the **starting condition** for the focus-race test, not the recipe target.

If a probe were started **now** (forbidden):

- `launchTargetApp` would see `activeWindow=com.taobao.idlefish` ≠ companion → `startActivity` + `waitUntilPackage(companion)`
- `ensureReady` would log `expected=com.company.cloudctl.companion actual=<whatever rootInActiveWindow is>`
- that is the missing hard-accept evidence

## Why ca211913 does not count (captain D)

- `ca211913-bf66-4692-b2cd-d8610b4f2561` SUCCEEDED 2026-09-08T11:10:53–11:10:56Z, `DeviceProbeResult`
- Companion was **already** foreground (`am start` before POST) → `launchTargetApp` skipped wait
- Historical log dumps under `repair-wrong-active/` contain **zero** `expected=` / `actual=` / `launchTargetApp after wait` hits
- Old failure `7f292679` left FAILED / `WRONG_ACTIVE_PACKAGE` / attempt=1 (unchanged; GET 2026-09-08T10:55:54Z and after-newprobe copy same)

17:41 ATM (`repair-wrong-active/atm-17-41-23-26.txt`) still shows the original race: companion launch while idlefish task #1825 held focus (~117ms–1.2s). That is pre-patch ATM, not patched executor `expected=`/`actual=`.

## Exact gap

Hard-accept needs a live executor run that starts with idlefish FG and prints `expected=` vs `actual=`.
The only on-device trigger for that run is claiming a new `device.probe_capabilities.v1` (or replaying a command).
This card forbids creating a new probe and forbids rewriting `7f292679`.
No legal in-scope action remains. Stop.

## Evidence directory

`artifacts/tasks/P14-recipe-publish/hard-accept-20260909/`

- `fg-now.txt` — 01:03:43 +0800 idlefish MainActivity focus + pid 16987
- `dumpsys-activity-activities.txt` / `dumpsys-window-windows.txt` / `fg-package-extract.txt`
- `logcat-tags-live.txt` — heartbeat only, no executor needles
- `enabled-a11y.txt` / `companion-pid.txt` / `companion-package-meta.txt` / `runtime-status.xml`
- copies: `GET_7f292679.json`, `command-7f292679.json`

Handoff C: `/Users/wangziheng/Desktop/herdr/handoff-P14-hard-accept.md`

## Ban reminder

No disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git revert / Ed25519 reopen / P15.
Do not flip `7f292679` FAILED→success. Do not POST a new probe from this card.

## Rollback

None. No new code/APK this card. Workspace remains dirty from the 2026-09-08 wait-patch.
