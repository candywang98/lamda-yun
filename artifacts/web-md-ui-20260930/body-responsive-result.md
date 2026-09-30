Work item WEB-MD-RESPONSIVE-20261001
Baseline 48f08e8bdb1d176e122060020d7cb96e041164f6
Branch fix/web-md-responsive-20261001
Worktree /tmp/cloudctl-web-md-responsive-20261001
Owned diff: apps/web/src/styles.css only, one line removes body min-width:320px.
Reason: parent browser evidence at 320px viewport with a 15px scrollbar gives a 305px layout viewport. The fixed body minimum forced 320px body/document scroll width. Removing the floor allows ordinary block width to follow available layout width, without hiding overflow.
Reviewed existing shell CSS: yy-shell has no fixed width; yy-main loses 232px left margin at <=760px; yy-content width is min(100%,1540px) with border-box. Existing responsive breakpoints and component-local table scrolling untouched.

Exact acceptance commands (all exit 0):
- pnpm install --offline --frozen-lockfile (install.log)
- pnpm --filter @cloudctl/api-contracts build (contracts.log)
- pnpm --filter @cloudctl/web exec vitest run tests/operations-shell.spec.ts tests/operations-catalog-navigation.spec.ts tests/operations-catalog.spec.ts tests/operation-page-availability.spec.ts (tests.log; 4 files, 23 tests)
- pnpm --filter @cloudctl/web build (build.log; vue-tsc -b and Vite, bundle size warning only)
- git diff --check (diff-check.log)

No new mirror test added for reversible CSS. Browser geometry remeasurement remains parent review; unit tests do not establish rendering geometry. No integration, production archive, fleet/task modification, deploy, push, or business/device actions. No API/shared contract changes; no merge dependency beyond baseline. Implementation executor unchanged from assigned worker.
