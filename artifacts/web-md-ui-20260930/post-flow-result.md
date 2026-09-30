Work item WEB-MD-POSTFLOW-20260930
Frozen baseline 40d79f2016ca14e04fd68d00d5de85bfd20807cd
Branch fix/web-md-post-flow-20260930
Reviewed original competitor Markdown plus screenshots 032 article link collection and 051 Xiaohongshu publishing.
Owned: PostCollectView.vue, PostPublishView.vue, new post-flow-views.spec.ts. Controller later released operations-view.spec.ts only for the three affected post view assertions.
Queue integration prerequisite 4ab261f was cherry-picked as 9d22972 for regression validation by explicit controller instruction; this is NOT post-flow-owned work. Integrator already has original queue commit and should cherry-pick ONLY final post-flow commit.

Implemented:
- Link recording states upfront that body remains the URL; removes MD5/plugin and unsupported scraping claims.
- Every nonempty line validated before any write; duplicate-submit guard, frozen links/dedupe snapshot, 10-line bound.
- Dedupe compares sourceLinks AND exact trimmed body (cloud payload strips sourceLinks); duplicate links in the same batch also skipped.
- Group selector explicitly disabled because current catalog adapter does not persist grouping; no false group assignment promise.
- Read error/retry, known success/skipped counts, uncertain rejected save isolated from pending textarea, pending unattempted only. A failed request may have committed: user must verify it manually, no automatic replay.
- Publish page labels browser-only allocation plan near heading and primary action. No platform tasks, device commands or publishing.
- Preview assignments, immutable local save snapshot, storage failure feedback; no auto-video/watermark processing or video selections. Unsupported old config flags reset.
- Device/catalog read failure and retry including callback errors; loading blocks plan saves, empty state, search/jump/page-size bounds.
- Responsive table overflow, form stacking, accessible operation button and search/page fields.

Commands, all final exit 0:
- pnpm install --offline --frozen-lockfile
- pnpm --filter @cloudctl/api-contracts build
- pnpm --filter @cloudctl/web exec vitest run tests/post-flow-views.spec.ts tests/operations-view.spec.ts: 2 files, 58 tests (12 new + 46 existing route tests)
- pnpm --filter @cloudctl/web build: vue-tsc -b + Vite; bundle size warning only
- pnpm --filter @cloudctl/web typecheck (after final test addition)
- pnpm --filter @cloudctl/web exec eslint src/views/PostCollectView.vue src/views/PostPublishView.vue tests/post-flow-views.spec.ts tests/operations-view.spec.ts: no errors/warnings
- git diff --check

Limitations: no real browser geometry/device/cloud acceptance. Mock catalog tests do not establish backend idempotency or device readiness. Dedupe is bounded to records returned by catalog.list and cannot prevent cross-client races. Uncertain save list is session UI state, not a durable audit queue. Group assignment remains unavailable rather than silently discarded. Existing adapters/contracts unchanged.

Controller-approved supplement (2026-10-01): PostPublish CSV fields now neutralize leading whitespace plus =,+,@,- and leading tab/newline formulas before quoting; added export test. operations-view route assertions await actual group load, match ProductImport 选择文件并解析, and reject fake PDF/current-form parameter data in generic mock details, expecting the explicit no-real-snapshot explanation.
Validation-only prerequisite cherry-picks: aac1710 -> dbbd77a; 7eaddd5 -> 3498c8c; 7546cf7 -> d374e9d. Controller already has these; cherry-pick only final supplement commit.
- pnpm --filter @cloudctl/web exec vitest run tests/post-flow-views.spec.ts tests/operations-view.spec.ts: exit 0; 2 files, 59 tests (13 post flow, 46 route tests), supplement-tests.log
- pnpm --filter @cloudctl/web typecheck: exit 0, supplement-typecheck.log
- pnpm --filter @cloudctl/web exec eslint src/views/PostPublishView.vue tests/post-flow-views.spec.ts tests/operations-view.spec.ts: exit 0, no warnings, supplement-lint.log
- git diff --check: exit 0

Candidate compatibility follow-up: removed PostPublish dependency on the newer fetchXianyuTaskDevices(onError) signature. Plan device reads now call Control API devices() directly and mapControlDevice for id/name/presence only; no account API, account inference or task mutation. Rejected device reads remain visible through Promise.allSettled. Unconfigured API returns no devices and prunes stale selected devices, so no plan can be saved against stale configuration.
Owned files: PostPublishView.vue and post-flow-views.spec.ts only.
- pnpm --filter @cloudctl/web exec vitest run tests/post-flow-views.spec.ts tests/operations-view.spec.ts: exit 0, 60 tests (14 + 46), candidate-compat-tests.log
- pnpm --filter @cloudctl/web build: exit 0, candidate-compat-build.log; bundle size warning only
- pnpm --filter @cloudctl/web typecheck: exit 0 after final test synchronization, candidate-compat-typecheck.log
- scoped eslint: exit 0, clean, candidate-compat-lint.log
- git diff --check: exit 0
Candidate branch compilation remains controller acceptance; this worker verified its assigned integration tree and avoided importing newer helper behavior.
