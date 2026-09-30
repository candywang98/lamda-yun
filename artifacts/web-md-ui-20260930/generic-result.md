# WEB-MD-GENERIC-20260930
Baseline: 4386571dcceffcc58597f911d070dfc818b67cea
Branch: fix/web-md-generic-20260930
Commit: 7eaddd574916b092371954c346c551d0a43f98f2
Owned diff: OperationsView.vue, new generic-workbench.spec.ts, operations-live.spec.ts. 218 insertions / 65 deletions. Worktree clean.

Frozen baseline contracts unchanged: OperationCatalogEntry, OperationTask, operationTasks/configDraft/devices and createOperationTask/createBatchOperation. No generated metadata, backend, ledger or dedicated child view changes.

Changes:
- Blank production device/resource/snapshot defaults; explicit resource IDs replace invented demo targets and treating historical task IDs as resource IDs. Mock selection remains explicit mock only.
- Actual device query options/names; actual task states/modules/parameters/context/results. Filters read real records and support reset.
- Supported main app and immediate/config-save choices only. Old draft fictional devices/resources/snapshot/app/time not automatically restored; generic production datetime/demo username defaults blank.
- Guide pages have no save/reset/create actions; factual links to existing fleet/content-io/product/im/orders routes replace copied source text/workflow.
- Pool examples and static trends only visible in explicit Mock; production links to verified /media-assets route and states data unavailable.
- Visible configuration-preview and disabled reason; preserve catalog permission/risk/feature/parameter gates, explicit reason/phrase, busy guard and batch rules. Async load generation prevents old route responses populating new route.
- Receipts expose actual executionState/executorAvailable and explain backend acceptance does not mean device execution; contract_only explicitly called out.
- Detail shows stored backend parameters/context/result rather than competitor references/current unsent form. CSV injection prefix protection.

Validation commands:
- pnpm install --offline --frozen-lockfile: exit 0.
- pnpm --filter @cloudctl/api-contracts build: exit 0, local dependency dist only.
- pnpm --filter @cloudctl/web exec vitest run tests/generic-workbench.spec.ts tests/operations-live.spec.ts tests/operations-fail-closed.spec.ts: exit 0; 3 files, 14/14 (9 generic, 4 live, 1 fail-closed).
- pnpm --filter @cloudctl/web typecheck: exit 0.
- pnpm --filter @cloudctl/web build: exit 0, bundle-size advisory retained.
- pnpm --filter @cloudctl/web exec eslint src/views/OperationsView.vue tests/generic-workbench.spec.ts tests/operations-live.spec.ts tests/operations-fail-closed.spec.ts: exit 0; 0 errors, 212 template-indentation warnings, no broad formatting churn.
- git diff --check and git diff --cached --check: exit 0.

Legacy regression run included read-only operations-view.spec.ts: one remaining expected failure (lines 495-496 expect competitor PDF reference and current draft as record detail); root notified to have owning post worker replace with explicit Mock no-snapshot assertion. Other 45 legacy mock tests passed. File not modified by this worker. Current focused suites pass; no full-suite acceptance claimed.

No actual cloud/device mutations; software mocks only, no browser/device/deployment acceptance. Resource IDs are user-provided; backend remains validation authority. Scope remains first 200 operation tasks, not complete business-resource listing. No integration locks required beyond controller merge lock. Integration dependent expectation edit belongs to post worker.
