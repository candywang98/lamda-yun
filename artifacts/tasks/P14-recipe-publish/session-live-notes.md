# P14 live notes (2026-09-08)

## IDs
- Seoul: https://43.133.243.154.sslip.io
- Device: OnePlus 9R serial=b0644fb5 id=4aabc387-6e4b-4b59-a525-b1c119ec7f5b
- Tenant: 00000000-0000-7000-8000-000000001111
- Operator: 00000000-0000-7000-8000-000000000222
- Account: 01a07a1c-572c-7ed5-83ad-a48ebbfed67a
- Recipe: 01a07f6d-e5c0-7bb1-b360-a52fa3c06d3f artifactSha256=825921a4… dep=01a07fac PUBLISHED
- Probe task: 7f292679-aa07-4908-81b4-07f7dbcb891e commandType=device.probe_capabilities.v1 created 06:33:38Z
- FGS pid=29562 CompanionSyncService isForeground=true (~2.5h+)

## Ban
No disable-signature / auto-publish / Xianyu submit / port 65000 / reading key files (cloudctl_secrets.xml).

## Evidence snapshot (local 15:50 / ~07:50Z)
- Heartbeat LIVE: logcat `15:50:40.831 I CompanionSync: Heartbeat successful` tid=30297 DefaultDispatch. presence_online=true. Network=Cellular, battery=100 charging.
- Inbox sqlite 15:50 copy: 48 rows ALL TERMINAL_* (8 SUCCEEDED, 38 FAILED, 1 TERMINAL_CONFIRMED null, 1 TERMINAL_REJECTED). Last write ca985a89 @ 04:19:27.427Z. **No PAUSED / RESUME_CHECK**. 7f292679 not in inbox.
- files/recipes: **NO_RECIPES_DIR**. files/ only automation-evidence, media-deliveries, profileInstalled@13:11.
- runtime task still ca985a89 Succeeded @ 04:19:25Z.
- hasBlockingHead (STATE_PAUSED|STATE_RESUME_CHECK) **ruled out** by sqlite.
- Server claim() blocks business_state={PAUSE_REQUESTED,PAUSED_WAITING_USER,RESUME_CHECK,CANCEL_REQUESTED,WAITING_MATERIALS}. RECONCILING cf1c028d does **not** block claim.
- Companion syncLoop: pendingResume→runResume; else hasBlockingHead→delay; else isValidated→syncRecipes THEN client.claim() POST /companion/v2/tasks/claim (204=empty).
- 4xx auth/non-retryable → stopSelf would kill presence; presence alive ⇒ not that path.
- Heartbeat can set pendingResume from JSON `resume.taskId+leaseId`. If set every beat, syncLoop never claims (starvation). markResumeCheck false → runResume returns immediately; then next beat re-sets pendingResume.
- Thread names 15:44: DefaultDispatch 29707/29708/29723/30297 (30297=heartbeat). Need Java stacks not just names.

## Ruled out
1. stopSelf / FGS dead
2. inbox blocking head
3. isValidated false (heartbeat uses same gate and is succeeding)
4. RECONCILING as server-side claim blocker

## Remaining hypotheses (priority)
1. **syncJob dead or cancelled**, presenceLoop independently alive → wake FGS (`am start-foreground-service`) may relaunch syncLoop. Only if onStartCommand restarts jobs.
2. **syncRecipes/claim hung** on IO (35s read timeout or no timeout) → DefaultDispatch/IO parked; wake FGS is no-op.
3. **pendingResume trap**: heartbeat keeps injecting resume for cf1c028d/P08 stall; runResume no-ops; claim starved.
4. Server still returning 204 because ACTIVE lease / other QUEUED-with-lease / REMOTE write lease — need GET 7f292679 + device + blocking tasks.

## Next knife
1. GET /api/v1/platform-tasks/7f292679 + GET device last_seen (DEV_AUTH_BYPASS, no secrets file).
2. Java stacks for pid 29562 (debuggerd/SIGQUIT), dumpsys VALIDATED.
3. Read onStartCommand: does second start relaunch syncLoop?
4. Wake FGS **only if** syncJob dead (not if hung on same process).
5. After claim: pin recipe hash 825921a4 ≠ builtin 901f795b; tamper→422; revoke→rollback.
6. Spreadsheet Q=模块通过, D still 非验收通过; append 09 line.

## Helpers
- artifacts/tasks/P14-recipe-publish/_probe_device.py
- temp/p14_claim_fn.py (server excerpt only)
