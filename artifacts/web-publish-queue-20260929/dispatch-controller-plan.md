# Explicit Dispatch and Device Status: Controller Plan

Date: 2026-09-29 (Asia/Shanghai)

## Reviewed Baseline

- Frozen integration baseline: `933964b2ded8a22f0d3c74d8bb061a0098b2266b`.
- Normal push to `origin/main` succeeded; remote main was read back at that SHA.
- Included main commits: `6be7009` (keyboard recovery), `2684993` (feature-specific
  device scope), `99d5509` (queue permissions), and `933964b` (persisted Web queues).
- Controller reran the combined regression on this baseline:

```sh
.venv/bin/pytest -q \
  tests/integration/test_xianyu_publish_permissions.py \
  tests/unit/test_xianyu_publish_recipe.py \
  tests/integration/test_xianyu_publish_delta.py \
  tests/integration/test_publish_commands.py \
  tests/integration/test_platform_tasks.py \
  tests/integration/test_im_aggregation.py \
  tests/integration/test_im_fleet_ownership.py \
  tests/ops/test_three_device_preflight.py
```

Result: exit 0, 139 passed in 35.98 seconds.

- `plan_guard`: valid, 54 nodes. All 108 development/acceptance state fields
  match `0433e81`. `tasks.json` SHA-256 remains
  `3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb`.
- This is not deployed software or real-device acceptance.

## Confirmed Serial-Dispatch Defect

At 17:16 +08:00, the controller used an in-memory ASGI app with test-only
authentication and the existing `test_xianyu_publish_delta` fixture helpers.
No request reached production or a physical phone.

1. Create a two-item queue: HTTP 201.
2. Dispatch the first target: HTTP 200.
3. Ask for the next target: HTTP 204, correctly blocked.
4. Directly dispatch the second target: HTTP 200, incorrectly allowed.
5. Read the queue: both targets are `IN_FLIGHT`.

The existing 139-test scope did not catch this bypass. A green queue-creation
suite therefore does not justify enabling real-device dispatch.

## Frozen Implementation Contract

- Keep existing dispatch, queue, and platform-task HTTP response schemas.
- Web dispatches only the first eligible `PENDING` target, on explicit user
  action. No automatic next item, retry, resume, failure report, or confirmation.
- Unknown/lost responses are reconciled by reading the same queue. Never mint
  another task merely because a response was lost.
- Device, account, queue, target, task, command type, and current session must
  agree before any state or result is accepted.
- Platform-task state and queue publication outcome remain separate.
  `PAUSED_WAITING_USER` is not proof of form readiness or publication;
  task `SUCCEEDED` alone is not confirmed publication.
- Backend enforces serial order at the actual dispatch boundary, including
  concurrent requests. A process-local lock or SQLite-only test is not proof of
  PostgreSQL cross-process correctness.
- No new schema, migration, Android recipe, generated contract, or plan-state
  change is assigned.

## Execution Ownership

Both isolated branches start at the same baseline. The designated model is
`gpt-5.6-sol`, reasoning effort `high`.

- Web branch: `agent/sol-publish-dispatch-web-20260929`, existing free
  `sol-publish-queue-20260929` checkout. Scope: publish data/view/tests and the
  explicitly delegated handwritten dispatch client wrapper.
- API branch: `agent/sol-publish-dispatch-api-20260929`, existing free
  `sol-ime-picker-20260929` checkout. Scope: publish queue service and focused
  integration tests.
- Controller owns review, integration, this evidence index, and main pushes.
- The first Web worker start failed with HTTP 429 before edits. One same-model
  retry was started. No model substitution or other-chat access is authorized.
- Completion, test counts, and final SHAs must be recorded after worker delivery;
  assignment alone is not implementation evidence.

## CI and Review Findings

- GitHub CI run `36547477595` for `933964b` failed. The previous baseline
  `0433e81` run `36518192733` also failed Python formatting and Android, but its
  frontend job passed. The new frontend failure must not be called pre-existing.
- Authenticated read-only job-log retrieval identified exactly one frontend
  failure: 607/608 passed; the quota-failure test spies on the shared Storage
  prototype before `renderView` writes the localStorage fixture. On CI Node 22,
  this throws from fixture preparation instead of the intended sessionStorage
  write. The Web owner must isolate that fault without removing its assertions.
  No credential was printed or stored in this evidence.
- A no-API-environment local rerun still passed 608/608, so an unset API URL did
  not reproduce the CI failure.
- Android logs for both SHAs fail at `:app:verifyReleaseUpdatePublicKey`.
  The release-key safety gate is not to be bypassed to obtain a green CI badge.
- Local read-only Ruff format checking identified eight files, including one
  new formatting issue in `test_three_device_preflight.py`. That one file and the
  new dispatch test were assigned for formatting; seven older files remain
  outside this work item's scope.
- API worker delivery `55e9b18` added queue locks and six passing regressions;
  formatting follow-up `b4ffe2d` passed 36 preflight and six dispatch tests.
  Integration was held for an additional controller finding:
  `PlatformTaskService._stamp_business_fields` resets state/control/snapshot
  even on an idempotent replay. Orphan-task recovery must preserve an already
  claimed or paused task's real state, remote control, result, and frozen
  snapshot. A matching regression and minimal recovery fix are required.
- The separately committed mobile task and queue target are not one atomic
  transaction. No schema/outbox work has been assigned, and this residual crash
  window must remain explicit rather than being described as atomic delivery.

## Final Integration

- API final delivery: `09f382ada1e943b73827ed1dc91acba9b62406d4`, fast-forwarded
  into main after review. It includes the started-task recovery correction and
  canonical snapshot-hash correction.
- Web delivery: `aead0011fadde83d1762ee5c9c92517e72332149`, cherry-picked as
  `4e77a5d`. This is the source revision used for controller integration checks.
- A recovered task retains its original state, remote control, result, payload,
  and hash. Partial/mismatching task records are rejected. A missing historical
  boundary is readable as unknown; a present mismatch is rejected.
- Normal new-task snapshot hashing excludes the old hash before hashing the
  completion boundary. Recovered tasks are not rehashed.
- Both designated Sol/high workers delivered their commits and were closed.
  Their recoverable branches and checkouts were retained.

Controller regression command:

```sh
.venv/bin/pytest -q \
  tests/integration/test_xianyu_publish_dispatch.py \
  tests/integration/test_xianyu_publish_permissions.py \
  tests/unit/test_xianyu_publish_recipe.py \
  tests/integration/test_xianyu_publish_delta.py \
  tests/integration/test_publish_commands.py \
  tests/integration/test_platform_tasks.py \
  tests/integration/test_mobile_task_api.py \
  tests/integration/test_task_schedules.py \
  tests/integration/test_xhs_publish_delta.py \
  tests/integration/test_douyin_publish_delta.py \
  tests/integration/test_im_aggregation.py \
  tests/integration/test_im_fleet_ownership.py \
  tests/ops/test_three_device_preflight.py
```

Result: exit 0, 185 passed in 35.14 seconds, including the real local PostgreSQL
dispatch-concurrency fixtures. No skips were reported in this selection.

Additional controller checks on the integrated source:

- `pnpm --filter @cloudctl/api-contracts build`: exit 0.
- `env VITE_CONTROL_API_URL= VITE_CONTROL_API_DEV_AUTH=false
  VITE_OPERATIONS_MOCK_ENABLED=false pnpm test`: exit 0; Web 624/624 across
  48 files, Studio 16/16 across four files, contracts type check passed.
- `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  pnpm --filter @cloudctl/web exec playwright test -c playwright.xianyu-publish.config.ts`:
  exit 0, 12/12 desktop/mobile fixture tests in 22.9 seconds.
- `env VITE_CONTROL_API_URL= VITE_CONTROL_API_DEV_AUTH=false
  VITE_OPERATIONS_MOCK_ENABLED=false pnpm --filter @cloudctl/web build
  --outDir /tmp/cloudctl-local-preview-20260929/dist`: exit 0, including
  vue-tsc. The existing large-chunk warning remains.
- Scoped Ruff lint and format checks passed for both production modules,
  dispatch/permission tests, and preflight tests. Scoped mypy passed for both
  production modules.
- `git diff --check 933964b HEAD`: exit 0.
- Final plan guard: valid, 54 nodes; all 108 state fields still match `0433e81`,
  with the unchanged task-ledger hash above.
- These checks do not remove the unrelated older global-format/release-key CI
  blockers and do not establish hardware acceptance.

## Offline Preview

- Built with an empty `VITE_CONTROL_API_URL`, development authentication off,
  and mock writes off. Build succeeded.
- Loopback static preview has no proxy, rejects API paths and non-GET/HEAD
  methods, and sends CSP `connect-src 'none'` and `form-action 'none'`.
- Browser inspection confirmed the publish page renders and both create/query
  buttons are disabled. An API GET returned HTTP 503.
- Preview is a local software artifact, not a production deployment or a
  simulated successful device delivery.

## Remaining Real Evidence

At least two phones must produce new inbound messages in one aggregation view.
One capable phone must execute an authorized product task to the pre-publication
boundary and report its actual state. One capable phone must provide a live
screen and a verified end/handoff. These may use the same capable phone.
No third-phone, complete connected-fleet, or physical-disconnection gate applies.

No real send, publication, upload, account rebinding, tenant migration, APK
installation, or phone setting change is authorized by this document.
