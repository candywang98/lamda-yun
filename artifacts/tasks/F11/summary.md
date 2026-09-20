# F11 evidence summary

- Task: 导入导出、内容修订和历史
- Audited: 2026-09-20 (Asia/Shanghai)
- Software status: `SOFTWARE_DONE`
- Acceptance status: `SOFTWARE_ACCEPTED`
- Device acceptance: not applicable; software verification only
- Staging status: `NOT_TESTED_AGAINST_STAGING`

## Delivered behavior

- New `/api/v1/content-io` namespace with three surfaces; the legacy `/products:import` semantics are untouched.
- Import defaults to dry-run validation with row-precise outcomes: `IMPORT` / `SKIP_EXISTING` / `ERROR`; in-file duplicate `spuCode` marks every implicated row with `DUPLICATE_IN_FILE` and row positions.
- Explicit `apply=true` writes only valid rows (existing `spuCode` skipped, never overwritten), and requires an operator-confirmed checkbox in the Web workbench.
- Same `importKey` replays the first applied result; a re-imported file without a key imports nothing new.
- CSV export is tenant-scoped, `QUOTE_ALL`, and neutralizes spreadsheet formula injection (`= + - @`, tab, CR) with a leading apostrophe; exported data re-imports to identical state.
- Immutable, paginated revision history reads over the audit trail (`product.*` events): apply-path entries carry a full field snapshot; later edits append and never rewrite earlier entries; cross-tenant reads 404.
- Web `/content-io` workbench: JSON import panel with confirm gate, CSV export, revision pager; fail-closed without Control API.

## Proven evidence

- Backend implementation: `services/control-api/src/cloudctl_api/features/content_io/`
- Web implementation: `apps/web/src/features/content-io/`
- Backend coverage: `tests/integration/test_content_io_delta.py`
- Web coverage: `apps/web/tests/content-io.spec.ts`
- Canonical API contract: `packages/api-contracts/openapi.json`
- Desktop screenshot: `artifacts/tasks/F11/evidence/desktop-workbench.png`
- Mobile screenshot: `artifacts/tasks/F11/evidence/mobile-workbench.png`

## Verification

- F11 backend integration: 3 passed (dry-run/idempotency, formula-safe export + round-trip, immutable paginated history).
- Media/content backend regression: 17 passed.
- Full backend suite on this worktree: 1051 passed, 11 skipped (worktree base predates the F10 merge; merged-tree reruns below).
- F11 Web tests: 8 passed; full Web suite (39 files, 281 tests) and production build passed.
- Web typecheck: passed. F11 scoped ESLint: passed. Python Ruff: passed.
- Strict OpenAPI equality test: passed. TypeScript API contract build: passed.
- GUI: desktop 1440x1000 and mobile 390x844 rendered correctly; mobile `scrollWidth` equalled `clientWidth` (390); apply button confirmed disabled until the operator checkbox is set.

## Scope notes

- XHS video metadata validation is not implemented: the task card freezes that conflict for an R00 ruling and forbids auto-expanding scope from legacy templates.
- No database migration was added; revision history reads existing audit structures only.

## Remaining acceptance gap

No staging, device, or production interaction was performed. Software acceptance does not claim business-side-effect, staging, or device acceptance.
