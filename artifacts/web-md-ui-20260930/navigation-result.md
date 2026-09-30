WEB-MD-NAVIGATION/20260930.1
Baseline: 40d79f2016ca14e04fd68d00d5de85bfd20807cd
Sources: competitor Markdown + screenshots 001, 036, 053; OperationsView explicit dispatch branches, xianyu extra operation map, router and feature routes.
Commands:
- pnpm install --offline --frozen-lockfile: exit 0
- pnpm --filter @cloudctl/api-contracts build: exit 0
- pnpm --filter @cloudctl/web exec vitest run tests/operations-shell.spec.ts tests/operation-page-availability.spec.ts tests/operations-catalog-navigation.spec.ts tests/operations-catalog.spec.ts: exit 0; 4 files, 22 tests
- pnpm --filter @cloudctl/web build: exit 0 (vue-tsc -b and Vite); existing bundle-size warning
- pnpm --filter @cloudctl/web exec eslint src/views/OperationsCatalogView.vue src/components/OperationsShell.vue src/data/operation-page-availability.ts tests/operation-page-availability.spec.ts tests/operations-catalog-navigation.spec.ts tests/operations-shell.spec.ts: exit 0; 4 pre-existing SVG spacing warnings
- git diff --check: exit 0
Initial test invocation incorrectly passed -- through pnpm and ran the full suite: 51 files, 646 tests, 1 new navigation test failure from missing asynchronous route wait. Corrected with waitFor and reran only the four scoped files, all passing. Original output preserved in tests.log.
No cloud/device/business actions. No metadata, operation IDs, risk fields, generated client or backend changes. Static statuses never authorize execution. Retired IDs remain hidden as before. Outside-V1 entries explicitly say not integrated even if an old component exists.
Responsive CSS added; no real-browser geometry evidence collected by this worker. Parent owns browser review/integration. Additional result link is derived from route query; active orders gets a dedicated transient tab, product tab remains a stable product destination. Existing workspace persistence model is unchanged.

Review follow-up: catalog directory now derives reactively from display.visibleModules(), matching sidebar visibility. Hidden modules and operations are excluded from directory counts/search/list, and restored settings update immediately. Fixed header says visible directory entries. Quick paths remain separate workflow shortcuts.
- pnpm --filter @cloudctl/web exec vitest run tests/operations-shell.spec.ts tests/operation-page-availability.spec.ts tests/operations-catalog-navigation.spec.ts tests/operations-catalog.spec.ts: exit 0; 4 files, 23 tests (settings-tests.log)
- pnpm --filter @cloudctl/web typecheck: exit 0 (settings-typecheck.log)
- pnpm --filter @cloudctl/web exec eslint src/views/OperationsCatalogView.vue tests/operations-catalog-navigation.spec.ts: exit 0, no warnings (settings-lint.log)
- git diff --check: exit 0
