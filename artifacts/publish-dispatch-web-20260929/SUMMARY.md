# publish-dispatch-web-20260929

Date: 2026-09-29

## Scope

- Baseline: `933964b2ded8a22f0d3c74d8bb061a0098b2266b`
- Branch: `agent/sol-publish-dispatch-web-20260929`
- Frozen API: `POST /api/v1/xianyu/publish/queues/{queueId}/targets/{targetId}/dispatch` with no body; existing queue GET and platform-task GET remain the sources of truth.
- Completion boundary remains `HUMAN_PRICE_HUMAN_COMMIT`.
- No backend, Android, generated OpenAPI/schema/type, plan, task ledger, device, deployment, production, upload, send, confirm, resume, failure-report, auto-advance, or real publish changes/actions were made.

## Implementation

- Added the minimal handwritten TypeScript client wrapper for the existing dispatch endpoint.
- Added strict dispatch and platform-task identity validation across queue, target, task, device, account, batch, command, and raw event identities.
- A missing legacy `commandPayload.completionBoundary` remains readable as unknown; a present mismatching boundary is rejected.
- Added explicit dispatch for only the queue-order first eligible `PENDING` target. `FAILED_UNCONFIRMED` blocks later targets and is never retried here.
- Dispatch loss, malformed response, and HTTP 409 recover by querying the same queue only; no second dispatch is issued automatically.
- Added stale-response, unmount, repeated-click, session, permission, tenant/user/API-scope, and known-result preservation guards.
- Added target/task IDs, refresh, actual task state/errors, and raw-event-backed step display. `PAUSED_WAITING_USER` is labeled as operator waiting, and task `SUCCEEDED` is not presented as publication success.
- Added `RefreshCw` and `Play` icons to the new controls without redesigning the page.
- Fixed the publish-view quota test so a shared Node 22/jsdom `Storage` prototype throws only for `sessionStorage`, while `localStorage` delegates to the original implementation.

## Verification

All commands ran with local API environment assumptions removed via `env -u VITE_CONTROL_API_URL -u VITE_DEV_AUTH` where applicable.

- `pnpm --filter @cloudctl/api-contracts build` -> exit 0.
- `pnpm --filter @cloudctl/web exec vitest run tests/xianyu-publish-hardening.spec.ts tests/xianyu-publish-view.spec.ts` -> exit 0, 2 files / 88 tests passed.
- `pnpm --filter @cloudctl/web typecheck` -> exit 0.
- `pnpm --filter @cloudctl/web test` -> exit 0, 48 files / 624 tests passed.
- `pnpm --filter @cloudctl/web build` -> exit 0, 1,924 modules transformed; only the existing Vite chunk-size warning remained.
- `pnpm --filter @cloudctl/web lint` -> exit 0, 0 errors / 219 existing warnings.
- `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' pnpm --filter @cloudctl/web exec playwright test -c playwright.xianyu-publish.config.ts` -> exit 0, 12/12 passed across desktop Chromium and Pixel 7 mobile fixtures. External and unhandled API requests were denied by the fixture router.
- Port `4209` had no listening process after Playwright completed.
- Runtime was Node `v26.10.0`; Node 22 was not installed locally. The CI regression was reproduced structurally by using the shared `Storage` prototype and guarding on `this === window.sessionStorage`.
- `git diff --check` -> exit 0.

## Non-passing Diagnostic Attempts

- The first Playwright attempt could not launch because the Playwright-managed Chromium binary was absent. No test logic ran.
- The second attempt used the generic 4173 config, so the publish fixture correctly blocked navigation because it permits only the dedicated 4209 origin. The final run used the repository's dedicated config and passed 12/12.

## Remaining Gaps

- No real device, Companion, production API, deployment, ADB, publish, upload, send, confirmation, or side-effect acceptance was performed.
- Real-device/deployment acceptance must be executed separately by the authorized controller/operator with the required locks and must not infer publication success from these fixture-only software results.
