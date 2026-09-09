# P14 session checkpoint 2026-09-09 (hard-accept probe ACCEPTED)

Supersedes the 01:05 stall checkpoint. Install+claim and the 2026-09-08 WRONG_ACTIVE code patch stay closed. `7f292679` was not rewritten.

## Scope just completed
Expert-authorized **exactly one** probe with idlefish already FG. Live executor `expected=`/`actual=` captured. Hard-accept **ACCEPTED**.

## Ban (still in force)
No disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git-revert / Ed25519 reopen / P15.
**No 2nd probe.** Do not redispatch `7f292679`. Do not spoof `targetPackage`.

## Live device (b0644fb5) 2026-09-09 09:19:13 +0800
- companion pid 16987 (unchanged after run)
- **FG at send** = idlefish `MainActivity` t1825
- **FG after SUCCEEDED** = companion `MainActivity` t1846
- signed recipe still on device (825921a4…); this probe froze builtin 901f795b / recipe-device-probe-1

## Tasks
- `0d36fe3f-7a54-48aa-bfe1-4fbb36b5407e` SUCCEEDED attempt=1 controlEpoch=97 DeviceProbeResult ok
  - POST 201 at 2026-09-09T01:19:13.570831Z tenant `…001111`
- `7f292679-aa07-4908-81b4-07f7dbcb891e` stays FAILED / WRONG_ACTIVE_PACKAGE / attempt=1 / completedAt 2026-09-08T09:41:26.095338Z

## Executor lines (pid 16987, after logcat -c)
```
09:19:13.514 launchTargetApp targetPackage=com.company.cloudctl.companion xianyu=com.taobao.idlefish activeWindow=com.taobao.idlefish
09:19:14.528 launchTargetApp after wait expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
09:19:14.542 ensureReady expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
```

## Pointers
- Knife: `knife-20260909-hard-accept-probe.md`
- Duplicate checkpoint: `session-checkpoint-20260909-hard-accept-probe.md`
- Evidence: `hard-accept-probe-20260909/`
- Stall knife (historical): `knife-20260909-hard-accept-idlefish-fg.md`
- Code closeout: `knife-20260908-wrong-active-package.md`

## Do not open next
Stop. Do not POST again.
