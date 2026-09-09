# P07 CommandV1 production claim

Date: 2026-09-08

## What changed

Platform-task Companion claim (`POST /companion/v2/tasks/claim`) now mints a
`cloudctl.command/v1` object as the main instruction:

- envelope `protocolVersion` is `cloudctl.command/v1`
- nested `command` parses with `parse_command_v1`
- `steps` are omitted unless `legacyStepsEnabled` is true
- recipe pin is a frozen APK-local package (`builtin-phase1`), not a published catalog

Raw mobile-step tasks without `commandType` still claim as `cloudctl.mobile/v1`.

Companion `buildClaimedTaskPayload` copies `command`. `CompanionSyncService`
parses CommandV1 first, loads the matching builtin recipe by `versionId`+sha256,
and runs `RecipeEngine`. Publish/note builtins are OPEN_ONLY (checkpoint →
`WAITING_USER`); that path is not counted as execution success.

## Tests

- `.venv/bin/pytest tests/unit/test_command_v1.py tests/integration/test_platform_tasks.py tests/integration/test_mobile_task_api.py` — 49 passed
- `./gradlew :app:testDebugUnitTest` — BUILD SUCCESSFUL

## Live

- Seoul `cloudctl-mobile-api` restarted on `releases/20260901-1800` with the CommandV1 claim files.
- Companion debug APK installed on OnePlus `b0644fb5`.
- Probe `85fc2db5-af42-41b8-b8a8-d4a5eacb3009` was claimed (`controlEpoch` 92) then failed `ACCESSIBILITY_NOT_ENABLED` after APK reinstall dropped the grant.
- After a11y was restored, probe `67d95d4a-90b6-47b3-a854-4b962f7d07cf` claimed (`controlEpoch` 93) and succeeded via CommandV1 builtin recipe (`DeviceProbeResult`).
- Publish/note builtins stay OPEN_ONLY; they must not be treated as execution success.

## Not done

- P14 signed recipe publish / catalog
- Temporal still not on the production claim path
- Real 闲鱼 submit remains blocked before G3
- Phone accessibility must be turned back on by the operator after this APK install
