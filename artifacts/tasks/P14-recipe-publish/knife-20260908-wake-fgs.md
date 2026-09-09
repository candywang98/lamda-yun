# P14 knife 2026-09-08 ~08:18Z / local ~16:18

## IDs
- Seoul: https://43.133.243.154.sslip.io
- Device serial: b0644fb5 id=4aabc387-6e4b-4b59-a525-b1c119ec7f5b
- Other device DO NOT TOUCH: 31cab785-4bf7-451b-b15d-8788a367f40a
- Tenant: 00000000-0000-7000-8000-000000001111
- Operator: 00000000-0000-7000-8000-000000000222
- Account: 01a07a1c-572c-7ed5-83ad-a48ebbfed67a
- Recipe versionId: 01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f
- artifactSha256: 825921a415b7b0eaeb832ce1fb6e97847f9f981a45bb57db990491f1001ebd1f
- deployment: 01a07fac-4f09-7521-be30-eb859c4688c7 PUBLISHED
- Probe task: 7f292679-aa07-4908-81b4-07f7dbcb891e commandType=device.probe_capabilities.v1 created 06:33:38Z
- FGS pid=29562 CompanionSyncService isForeground=true startForegroundCount=1 lastActivity~3h7m

## Ban
No disable-signature / auto-publish / Xianyu submit / port 65000 / reading key files (cloudctl_secrets.xml).
Do not mark 01.D=验收通过. Q=模块通过 only after signed probe claim+hash pin+tamper 422.

## Evidence before wake (GET 08:18:07Z)
- Task 7f292679: state=QUEUED runnerStatus=QUEUED attempt=0 lease=null startedAt=null
- GET /api/v1/platform-tasks shows builtin recipe 901f795b / recipe-device-probe-1
  (expected: published_recipe 825921a4 is injected only on companion_claim=True)
- Device 4aabc387 last_seen_at=2026-09-08T08:18:07.820824Z LIVE cellular charging a11y=true runner=IDLE
- Inbox sqlite copy: all TERMINAL_*; no PAUSED/RESUME_CHECK; 7f292679 not in inbox
- files/recipes: missing
- Heartbeat logcat LIVE independently of claim
- Presence alive ⇒ not stopSelf/auth-reject path
- hasBlockingHead ruled out
- RECONCILING does not block server claim()

## Code facts
- onStartCommand: relaunch syncJob only if `syncJob?.isActive != true`
- syncLoop: pendingResume → hasBlockingHead delay → isValidated → syncRecipes THEN POST /companion/v2/tasks/claim (204=empty, no log)
- syncRecipes: listActiveRecipes HTTP FIRST (connect 10s / read 35s) then keys; empty keys return AFTER listing (still would hit Seoul)
- ResumeCommand.fromHeartbeat needs resume.taskId+leaseId; if set every beat, claim starved
- Empty claim is silent; files/recipes missing is consistent with never completing install OR keys empty after listing

## Hypotheses at wake
1. syncJob dead, presenceLoop alive → am start-foreground-service relaunches syncLoop
2. syncJob hung in recipes/claim HTTP → wake no-op, need stopservice + start-foreground-service
3. pendingResume trap / retry backoff

## Next
Wake FGS (no stop). Poll 7f292679 + Seoul access for /recipes/active and /tasks/claim.
If still QUEUED after ~45s: stop+start FGS.
After claim: pin 825921a4 ≠ builtin 901f795b; tamper→422; revoke→rollback.
Spreadsheet: Q=模块通过, D still 非验收通过; append 09.
