WEB-MD-POSTLIST-20260930
Baseline a434e5b49481b3cf7454cf5c2c1ff14c38bbe7d7
Branch fix/web-md-post-list-20260930
Owned only apps/web/src/views/PostListView.vue and apps/web/tests/post-list-view.spec.ts.
Reference: competitor Markdown post list section, actual screenshot 047_帖子管理_帖子列表.png. Requested screenshot 033 belongs to another module; reviewed correct list screenshot.

Behavior: literal replacement/append preview over frozen selected clones; only changed records saved; no mutation before confirmed response. Sequential save/archive classifies successful/uncertain/unattempted and never auto retries. Uncertain record writes are locked for component lifetime even after refresh. Explicit archive confirmation, duplicate-write guards/error messages, unsupported group bulk operation disabled. Correct load-error/retry/true-empty/no-match states, clamp paging and transparent cross-page selection, full title/body detail dialog with focus trap/Escape and inert background. CSV formula neutralization, media object URLs revoked, local table scrolling.

Final commands:
- pnpm install --offline --frozen-lockfile: exit 0
- pnpm --filter @cloudctl/api-contracts build: exit 0
- pnpm --filter @cloudctl/web exec vitest run tests/post-list-view.spec.ts: exit 0; 8 tests
- pnpm --filter @cloudctl/web build: exit 0; vue-tsc + Vite, existing bundle size warning
- pnpm --filter @cloudctl/web exec eslint src/views/PostListView.vue tests/post-list-view.spec.ts: exit 0; clean
- git diff --check: exit 0
Additional scoped regression first ran tests/post-list-view.spec.ts tests/operations-view.spec.ts: 53 passed/1 failed; failure is preexisting baseline ProductImport old 上传文件 label at operations-view.spec.ts:460. Controller notified; owns separate approved supplement. No changes to that test in this work item.

Limits: read-only API adapter has no expectedRevision/idempotency, so cross-client conflicts and ambiguous responses cannot be resolved by this UI. Unknown outcome guards are component-session state, not durable auditing; operators must inspect actual records. No automatic retry or recovery promise. No backend, schema, real business, device, browser-geometry or deployment actions.
