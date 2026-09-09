# P09 controlled action ledger — p09-ledger/20260910.1

Frozen for the next isolated CONTROL/ANDROID slices from `c1fec9e` plus this contract. This slice permits **Companion-only probe/test effects**, not real platform publication, deletion or money actions. G3 remains unaccepted. No new device execution protocol replaces CommandV1.

## Identity (shared, deterministic)

Let `T=taskId`, `R=claimed recipe sha256`, `S=claimed snapshotSha256`, `A=commit state ID`.

- `actionKey = sha256(UTF8("cloudctl.action/v1\n" + T + "\n" + R + "\n" + A))`.
- `parameterHash = sha256(UTF8("cloudctl.action-parameters/v1\n" + T + "\n" + commandType + "\n" + accountId + "\n" + decimal(bindingVersion) + "\n" + S + "\n" + R))`.
- Action ID must match `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`. Reject newline-bearing identity fields. Lease ID, epoch and attempt are not part of the immutable hash, but the server verifies the current active lease at intent/outcome time. Recipe and snapshot come from persisted task/pin, never request-selected versions.
- Server scope for now: `commandType=device.probe_capabilities.v1`, signed pinned Recipe manifest app `com.company.cloudctl.companion`. Require A to exist in the signed package graph. Other commands rejected with 409 G3_NOT_ACCEPTED before intent or any task mutation. This scope does not make a log/checkpoint count as a platform action.

## Persistence

CONTROL adds one Alembic migration (next free head, expected 0016), `MobileActionCommitRow` / table `mobile_action_commit`, with action_key primary key (64 hex), tenant/task/device/account IDs, binding version, recipe ID/hash, snapshot hash, action ID, parameter hash, lease ID, status, before evidence, reported evidence, resolution revision (initial 0), resolution evidence, resolved timestamp, created/updated timestamp. FK task -> mobile_task. One action identity per task/action ID, immutable inputs. No fake publish_target IDs and no changes to existing CommitIntentRow.

## Companion endpoints

All use the existing authenticated Companion binding, verify tenant/device ownership and task association. Return no bearer material or secret receipt.

1. `POST /companion/v2/tasks/{task_id}/actions/intent`
   Body `{leaseId, actionId, actionKey, parameterHash, beforeEvidence}`. beforeEvidence is a nonempty bounded opaque evidence reference (max 500), not arbitrary nested data.
   With a valid first request and RUNNING task, atomically persist INTENT and set task business_state=RECONCILING (unresolved outcome). Return HTTP201 `{decision:"AUTHORIZED", action:<ActionCommit>}` exactly once. An exact duplicate returns HTTP200 `{decision:"RECONCILE_REQUIRED", action:...}` and never grants a second invocation. Identity mismatch ->409; other-device ->404. Check an existing row before the new-intent RUNNING condition so a lost response can be observed safely. Never return AUTHORIZED for a retry/restart. Row/task locking plus unique key prevent two first grants.
2. `POST /companion/v2/tasks/{task_id}/actions/{action_key}/outcome`
   Body `{leaseId, parameterHash, status:"APPLIED"|"UNKNOWN", evidence}`. Verify active lease and frozen identity. INTENT -> reported APPLIED/UNKNOWN; exact replay idempotent; conflicting replay rejected. Reported APPLIED needs a nonempty independent postcondition evidence reference. Do not clear task RECONCILING or increment resolution revision: reported observation is not operator reconciliation.
3. `GET /companion/v2/tasks/{task_id}/actions/{action_key}`
   Returns `<ActionCommit>` to the owned binding even after task lease expires or task is terminal; no other device/tenant. Used for conservative recovery and authoritative resolution sync.

`ActionCommit` fields: `actionKey, taskId, deviceId, accountId, bindingVersion, recipeVersionId, recipeSha256, snapshotSha256, actionId, parameterHash, status, beforeEvidence, reportedEvidence, resolutionRevision, resolutionEvidence, resolvedAt, createdAt, updatedAt`.

## Explicit server reconciliation

Extend existing operator `PlatformTaskService.reconcile` in the same transaction:
- KEEP_WAITING does not resolve action rows.
- CONFIRMED_APPLIED sets action rows APPLIED and revision+1 with evidence/actor/time; existing unique platformItemId requirement remains.
- CONFIRMED_NOT_SUBMITTED sets rows NOT_SUBMITTED and revision+1 with evidence/actor/time; reject contradiction if a row has already reported APPLIED (operator must inspect that evidence instead).
- Task terminal state and action resolutions commit atomically. Existing terminal/reconciliation guards stay in force.
- No automatic retries. A NOT_SUBMITTED result can only lead to a separately requested new task under existing retry policy; old actionKey is never executable again.

## Android controlled adapter (not yet wired to third-party Recipe actions)

Create a typed remote ledger client/interface around these endpoints and a `ControlledActionExecutor` that wraps the existing journal/coordinator. Use callbacks for the effect and independent postcondition evidence; do not add raw shell/ADB/network-script capability to Recipe.

Execution order: validate command/A and hashes -> persist local INTENT via existing once gate -> request server intent -> only fresh AUTHORIZED can invoke effect once -> require independent evidence callback -> report outcome -> keep local task RECONCILING pending explicit resolution. A missing confirmation, callback/HTTP failure, timeout or cancellation after intent preserves UNKNOWN/RECONCILING. Propagate coroutine cancellation. Persist enough binding identity for resolution comparison; no replay on duplicate grant or reopening.

An APPLIED local action also remains task-blocking pending server revision>0. A recovered unresolved local action reads the server row, never re-invokes effect. Only matching identity, revision>0 and APPLIED/NOT_SUBMITTED resolution can clear the local block. Apply resolution atomically: journal resolved, inbox terminal confirmed (SUCCEEDED/FAILED respectively), obsolete outbox records marked superseded with an explicit reconciliation reason, no forged upload acknowledgments. An ordinary outcome report with revision=0 never unlocks anything. Any mismatch stays blocked. Add NOT_SUBMITTED to local journal's non-executable terminal outcomes.

Keep existing service production Recipe path unchanged for this slice; Root tests the adapter with a local counter and the real ledger API. Real platform commits require a later explicit graph/approval integration and business acceptance.

## Ownership and checks

- CONTROL: services/control-api/**, tests/integration/**; one migration owner. API/migration/SQLite+PostgreSQL concurrency, exact duplicate intent does not authorize again, changed snapshot/recipe/hash/device reject, outcome never clears task, explicit resolution updates both atomically, existing P09/P14 regressions.
- ANDROID: mobile/companion/**; typed client, identity golden values, adapter and safe local resolution application, cancellation/response-loss/restart/no-double-effect tests. No ADB/deploy by child.
- Root: this contract and golden fixture, generated OpenAPI, integrated verification, deployment, physical tests, evidence and plan updates. No G3 pass claim from synthetic counters.
