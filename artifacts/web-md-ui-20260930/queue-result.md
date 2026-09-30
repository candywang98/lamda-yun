# WEB-MD-QUEUE-20260930
Baseline: 40d79f2016ca14e04fd68d00d5de85bfd20807cd
Branch: fix/web-md-queue-20260930
Commit: 4ab261f670206ca436a582c2121bb95cd356fa9c
Frozen contracts: baseline packages/api-contracts/typescript/src/types.ts PlatformTaskView/PlatformTaskResume; client.ts listPlatformTasks/getPlatformTask/resumePlatformTask; server platform_tasks.py BUSINESS_STATES/list_tasks/resume. No contract edits.

Owned files only: OperationsView.vue (dedicated import/render/loader skip), TaskQueueView.vue (new), operations-view.spec.ts (dedicated route test), task-queue.spec.ts (new).

Validation:
- pnpm install --offline --frozen-lockfile: exit 0 (isolated dependency setup).
- pnpm --filter @cloudctl/api-contracts build: exit 0 (local compiled dependency only; no generated contract source edits).
- pnpm --filter @cloudctl/web exec vitest run tests/task-queue.spec.ts tests/operations-view.spec.ts: exit 0, 2 files, 56/56 tests (10 new queue, 46 operations).
- pnpm --filter @cloudctl/web typecheck: exit 0.
- pnpm --filter @cloudctl/web build: exit 0; existing >500kB bundle advisory.
- git diff --check and git diff --cached --check: exit 0.

Earlier diagnostic logs retained: first typecheck lacked contracts dist and failed; initial pnpm test -- invocation incorrectly expanded to all suites and failed unresolved contracts; two initial new assertions needed Vue mounted-update waiting. Corrected commands/results above supersede those runs. No claims of full-suite acceptance.

Behavior: actual device names/IDs/presence; all 13 backend business states plus unknown raw values; command, details/stall/error, created/scheduled times; local search/state/device/type filtering/reset/paging; explicit latest max 100 cap; loading/error/empty distinctions with old-data warning; actual getPlatformTask detail fields; no fake bulk controls; safe filtered CSV; DEVICE_CONTROL gate with paused state, explicit current-page checkbox, reason, duplicate guard, failure resets, stale detail protection.

Limits: no real API/device writes or browser acceptance; only mocked software tests. List and devices load atomically; device query failure surfaces an error rather than pretending names/presence were available. Latest 100 cap remains explicit despite server cursor availability. Old generic queue logic remains unreachable in OperationsView to minimize branch integration scope. No locks required for software integration; no deployment/device acceptance claimed.

## Review supplement
Commit: 41571996b9c062418d04dac2697f62ca8900b5b3 (on 4ab261f).
Owned diff: TaskQueueView.vue + task-queue.spec.ts only; 57 additions / 4 removals.
Modal focuses on enter, traps Tab/Shift+Tab, restores triggering element focus on close; Escape obeys in-flight resume guard. Explicit failed-detail retry added. Mobile controls and long header identifiers constrained/wrapped.
Focused verification: pnpm --filter @cloudctl/web exec vitest run tests/task-queue.spec.ts exit 0, 11/11. pnpm --filter @cloudctl/web typecheck exit 0. git diff --check exit 0. No full-suite rerun requested or claimed. operations-view.spec.ts released to post worker.
