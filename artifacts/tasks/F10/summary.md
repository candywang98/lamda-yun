# F10 evidence summary

- Task: 素材、水印、资源池与预检完整切片
- Audited: 2026-09-19 (Asia/Shanghai)
- Software status: `SOFTWARE_DONE`
- Acceptance status: `SOFTWARE_ACCEPTED`
- Device acceptance: not applicable; software verification only
- Staging status: `NOT_TESTED_AGAINST_STAGING`

## Delivered behavior

- Renders a real deterministic PNG watermark derivative and stores it as a tenant-scoped `MediaAsset`.
- Uses one derivative hash for preview and publish inputs; repeated requests reuse the output asset.
- Freezes a deterministic ordered media selection by tenant and `taskKey`, then replays the original snapshot after group membership changes.
- Runs explainable, read-only publish preflight checks for product fields, policy words, media, account authorization/binding, device state, accessibility, and target app version.
- Does not mint a platform task or perform a publish side effect.
- Provides a typed `/media-assets` Web workbench with fail-closed API behavior and desktop/mobile layouts.

## Proven evidence

- Backend implementation: `services/control-api/src/cloudctl_api/features/media_assets/`
- Object-store integration: `services/control-api/src/cloudctl_api/media_store.py`
- Web implementation: `apps/web/src/features/media-assets/`
- Backend coverage: `tests/integration/test_media_assets_delta.py`
- Web coverage: `apps/web/tests/media-assets.spec.ts`
- Canonical API contract: `packages/api-contracts/openapi.json`
- Desktop screenshot: `artifacts/tasks/F10/evidence/desktop-workbench.png`
- Mobile screenshot: `artifacts/tasks/F10/evidence/mobile-workbench.png`

## Verification

- F10 backend integration: 3 passed.
- Media/content backend regression: 20 passed.
- Full backend suite: 1051 passed, 11 skipped.
- F10 Web tests: 7 passed.
- Full Web suite: 39 files, 280 tests passed.
- Web typecheck: passed.
- Web production build: passed; existing bundle-size warning only.
- F10 scoped ESLint: passed.
- Python Ruff for F10 backend/tests: passed.
- Strict OpenAPI equality test: passed.
- TypeScript API contract build: passed.
- `git diff --check`: passed.
- GUI: desktop 1440x1000 and mobile 390x844 rendered without overlap; mobile `scrollWidth` equaled `clientWidth` (390).

## Known non-F10 gates

- Repository-wide Web ESLint remains red on pre-existing untouched files: 19 errors and 219 warnings. No F10 file appeared in that error list; F10 scoped lint passed.
- The in-app browser exposed the preflight button in the accessibility snapshot but timed out while clicking it. No page error or state change occurred; the same empty-input and explainable-result paths are covered by passing Vitest tests.

## Remaining acceptance gap

No real-device, staging, or production publish action was executed. ADB unavailability is a supplied environment fact and was not investigated. F10 software acceptance does not claim device, staging, or business-side-effect acceptance.
