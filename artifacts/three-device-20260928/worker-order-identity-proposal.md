# Order Identity Contract Evidence Note

Date: 2026-09-28

Executor: GPT-5.6 Sol / High

Branch: `agent/sol-order-identity-contract-20260928`

Baseline: `8d74987c2ae0bdc7dc3bbec88df50c8e52910833`

## Deliverable

Added the DRAFT contract `contracts/phase1/order-identity-isolation-20260928.md` to preserve the planner's decision boundary for the next software package.

The audit records two code-grounded gaps:

- `OrderSeenRegistry` can recognize a digit candidate in memory, but `SavedOrderRead.payload` and `buildOrdersScreenPayload` continue to persist the composite `OrderRowSnapshot.orderKey`.
- task and receipt admission authenticate an account, while `OrderRow` and its current natural-key lookup discard that account at the final projection.

## Decision Recorded

Frozen invariants are limited to authenticated-account preservation, unknown-owner preservation, weak-content non-identity, receipt/coordinate replay stability, payload-conflict preservation, prohibition on arbitrary digit promotion, tenant isolation, and separation of observation counts from unique-order counts.

The larger observation-table/account-scoped-projection/API/Web approach remains a candidate. No canonical identity protocol, migration, endpoint, Android extraction rule, historical-data operation, deployment, or device acceptance was approved or performed.

Commit `944c773` is treated only as the legacy projection overwrite guard. It is not described as an identity or historical-ownership fix.

## Source References

- `OrderReading.kt:117` -- weak composite construction.
- `OrderDedupe.kt:79` -- in-memory digit-candidate selection.
- `OrderDelivery.kt:105` and `CloudTaskClient.kt:449` -- durable payload path still serializes `row.orderKey`.
- `AutomationStore.kt:1194` -- durable outbox payload/digest record.
- `mobile_service.py:1210` and `order_delivery.py:158` -- authenticated task account resolution.
- `order_delivery.py:257` and `db.py:983` -- projection lookup and account-less natural key.
- `orders_service.py:53` and `OrdersView.vue:473` -- account-less query view and generic key presented as an order number.
- `tests/integration/test_order_legacy_guard.py` -- existing overwrite-guard regression suite.

## Verification and Limitations

- Documentation-only change; no runtime code, UI, schema, generated client, task JSON, controller evidence, or historical row was modified.
- No ADB, SSH, production, network, real business record, credential, Gradle, deployment, or device-lock operation was used.
- No runtime tests were executed for this read-only audit. Repository hygiene checks are limited to `git diff --check`, exact-path staging review, and commit inspection.
- Regression requirements for the future coding package are specified in the DRAFT contract but remain unexecuted.
