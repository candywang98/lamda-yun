# P14 session checkpoint 2026-09-09 (hard-accept probe ACCEPTED)

Supersedes `session-checkpoint-20260909-hard-accept.md` (stalled: no-probe). Does **not** reopen install/claim. Does **not** flip `7f292679`.

## Scope this card
Exactly one authorized `device.probe_capabilities.v1` with idlefish already FG. Capture executor `expected=`/`actual=` packages. Keep `7f292679` FAILED. Signatures on.

## Result
**ACCEPTED.** All three criteria met. Stop. Do not send a second probe.

## Ban (still in force)
No disable-sig / auto-publish / xianyu / 65000 / secrets.xml / Bearer / git-revert / Ed25519 reopen / P15.
**No 2nd probe.** Do not redispatch or rewrite `7f292679`. Do not spoof `targetPackage`.

## Live device (b0644fb5)
- companion pid **16987** pre and post (same process)
- a11y includes `com.company.cloudctl.companion/...CloudCtlAccessibilityService`
- **FG at POST 09:19:13 +0800** = `com.taobao.idlefish/.maincontainer.activity.MainActivity`
- **FG after SUCCEEDED** = `com.company.cloudctl.companion/.MainActivity` (launchTargetApp wait succeeded)

## Tasks
- `0d36fe3f-7a54-48aa-bfe1-4fbb36b5407e` SUCCEEDED attempt=1 controlEpoch=97
  - POST 201 `2026-09-09T01:19:13.570831Z` tenant `…001111`
  - started 01:19:14.379606Z completed 01:19:17.957374Z
  - result DeviceProbeResult outcome=ok
  - recipe freeze 901f795b / recipe-device-probe-1
- `7f292679-aa07-4908-81b4-07f7dbcb891e` stays FAILED / WRONG_ACTIVE_PACKAGE / attempt=1 / completedAt 2026-09-08T09:41:26.095338Z
- `ca211913-…` remains the earlier companion-already-FG success (not this hard-accept)

## Executor expected/actual (this probe only)
```
launchTargetApp targetPackage=com.company.cloudctl.companion xianyu=com.taobao.idlefish activeWindow=com.taobao.idlefish
launchTargetApp after wait expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
ensureReady expected=com.company.cloudctl.companion actual=com.company.cloudctl.companion
```

## Seoul
- https://43.133.243.154.sslip.io DEV_AUTH_BYPASS; tenant `00000000-0000-7000-8000-000000001111`
- POST 201 `idempotency-replayed: false` `x-request-id: p14-hard-accept-probe-20260909` (do not POST again)

## Pointers
- Knife: `knife-20260909-hard-accept-probe.md`
- Evidence: `hard-accept-probe-20260909/`
- Prior stall (no-probe): `knife-20260909-hard-accept-idlefish-fg.md`
- Prior code closeout: `knife-20260908-wrong-active-package.md`

## Do not open next
Stop after this card.
