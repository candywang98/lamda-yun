# Queue detail responsive supplement
Baseline: e90214e5082e2a86fb1de0fce518db3eb52146c3
Branch: fix/web-queue-responsive-detail-20261001
Commit: 9f16b658e2b81a8dca5466413157185839000857
Worktree: /tmp/cloudctl-web-queue-responsive-detail-20261001
Owned path: apps/web/src/views/TaskQueueView.vue only; one CSS line changed. Working tree clean.

Evidence: global styles.css line 217 gives fixed inset backdrop padding 20px, display grid/place-items center; line 23 gives border-box sizing. Local width 95vw ignored backdrop content width. Changed queue-detail width to 100% of available grid containing block and min-width:0 so intrinsic content cannot impose a larger minimum. Preserved max-width:900px, max-height:90vh, overflow:auto and focus behavior.

Validation (all exit 0):
- pnpm install --offline --frozen-lockfile
- pnpm --filter @cloudctl/api-contracts build (local dependency build, no source/contract edit)
- pnpm --filter @cloudctl/web exec vitest run tests/task-queue.spec.ts: 11/11, 1 file
- pnpm --filter @cloudctl/web typecheck
- pnpm --filter @cloudctl/web build (existing >500kB chunk advisory)
- git diff --check; git diff --cached --check

Geometry after fix is source-derived and unverified in a browser. No browser/space created and no fresh browser acceptance claimed. No mirror CSS tests. No device/business/API mutations, deploy, or push. Contracts and permissions unchanged. Integration requires controller merge only.
