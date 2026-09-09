# P14 session checkpoint 2026-09-09 (hard-accept stalled)

## Scope this card
Stronger acceptance only: idlefish must be FG **and** executor must record concrete `expected=` / `actual=` packages.
Install+claim closed. WRONG_ACTIVE code patch closed (`knife-20260908-wrong-active-package.md`). This card does **not** reopen them.

## Ban (still in force)
No disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git-revert / Ed25519 reopen.
**No new probe. No P15.** Do not redispatch or rewrite `7f292679`. Do not spoof `targetPackage`.
Do not treat dumpsys FG as executor success.

## Live device (b0644fb5) 2026-09-09 01:03:43 +0800
- companion pid 16987, lastUpdate 2026-09-08 18:45:42, FGS+a11y, runnerState=IDLE
- signed recipe still on device: `files/recipes/versions/01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f/package.json` hash 825921a4…ebd1f
- **FG = idlefish** `com.taobao.idlefish/.maincontainer.activity.MainActivity` (topResumed + mCurrentFocus + mFocusedApp)
- live CloudCtlExecutor/CompanionSync log: **no** `expected=` / `actual=` / `launchTargetApp` / `waitUntilPackage`

## Tasks
- `7f292679-aa07-4908-81b4-07f7dbcb891e` stays FAILED / WRONG_ACTIVE_PACKAGE / attempt=1
  - started 2026-09-08T09:41:24.891611Z completed 09:41:26.095338Z
  - issued `targetPackage=com.company.cloudctl.companion`
  - GET freeze still 901f795b / recipe-device-probe-1 (not the fail path)
- `ca211913-bf66-4692-b2cd-d8610b4f2561` SUCCEEDED but **invalid for this hard-accept**: companion already FG, wait skipped, no expected/actual logs (captain D)

## Why stalled
Executor `expected=`/`actual=` only prints when a command runs `launchTargetApp` / `ensureReady`.
No pending command. New probe forbidden. Therefore criterion (2) cannot be produced in-scope.

## Next (not this session)
Expert must either **authorize one new probe with idlefish already FG** or name a legal non-probe trigger.
Handoff: `/Users/wangziheng/Desktop/herdr/handoff-P14-hard-accept.md`
Knife: `knife-20260909-hard-accept-idlefish-fg.md`
Evidence: `hard-accept-20260909/`

## Do not open next
Stop after this card.
