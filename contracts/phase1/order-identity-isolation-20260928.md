# Order Identity Isolation Draft (2026-09-28)

Status: `DRAFT`

Baseline: `8d74987c2ae0bdc7dc3bbec88df50c8e52910833`

Scope: contract boundary only; no runtime, schema, API, Web, Android, deployment, or historical-data change is authorized by this document.

## 1. Proven Gaps

1. Android can detect a 15-24 digit candidate from `rawLines` for in-memory dedupe, but that value is not carried into the durable screen payload. `SavedOrderRead.payload` reparses raw rows, and `buildOrdersScreenPayload` serializes the unchanged `OrderRowSnapshot.orderKey`, which is currently the weak composite key.
2. Durable task creation and receipt admission authenticate an account, but the final `xianyu_order` projection does not retain that account. Its current uniqueness and lookup scope is tenant + device + platform + `order_key`.

These are separate defects. The legacy projection overwrite guard in commit `944c773` protects an existing durable projection from a legacy-page overwrite; it does not establish canonical order identity or historical ownership.

## 2. Frozen Safe Invariants

The following invariants are approved for every future implementation proposal:

1. A task-authenticated account identity must survive into any future account-scoped order representation. It must come from server-validated task identity, not from display text, current device binding, or client-supplied raw content.
2. Existing rows whose historical owner is not proven remain `UNKNOWN`. They must not be assigned, rewritten, migrated, quarantined, merged, or deleted merely because a device currently has an account binding.
3. Direction, nickname, title, amount, status, timestamps, or any composite of those visible fields is weak content. Equal weak content does not prove that two observations are the same order, and different weak content does not prove that they are different orders.
4. A digit string is not a platform order ID merely because it matches a length or syntax pattern. No arbitrary 15-24 digit string may be promoted without labelled UI evidence or a structured platform field whose semantics have been accepted.
5. Exact replay must continue to use the existing immutable receipt digest and collection coordinates. A replay with the same admitted payload must not create additional source observations; a payload conflict must remain a conflict and must not be silently reconciled.
6. Source-observation counts must never be presented as unique-order counts. Multiple observations may represent one order, and visually identical observations may represent distinct orders.
7. Tenant isolation remains mandatory at receipt, observation, projection, query, and presentation boundaries.

## 3. Not Frozen

The following remain `NOT_FROZEN` and require separate owner approval:

- the canonical identity field, provenance marker, or protocol version;
- whether a labelled platform order ID is available on a list page, detail page, or structured accessibility field;
- Android extraction and the point at which a proven identifier replaces or accompanies the weak key;
- whether one account's order may merge across devices or directions;
- database migration number, table shape, constraints, indexes, backfill, or downgrade behavior;
- API endpoint and response behavior, including how canonical rows and unresolved observations are exposed;
- Web labels, filters, counts, and placement;
- treatment of the legacy batch channel beyond the already accepted overwrite guard;
- any historical ownership recovery, manual claim, quarantine, deduplication, or deletion policy.

A separate unresolved-observation representation and an account-scoped canonical projection are candidate designs only. They are not approved implementation, migration, deployment, or device acceptance.

## 4. Evidence at the Baseline

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/OrderReading.kt:117` -- `OrderRowParser.compositeOrderKey` creates the weak composite key.
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/features/xianyu/orders/OrderDedupe.kt:79` -- `OrderSeenRegistry.dedupeKeyOf` can select a digit candidate from `rawLines` for in-memory dedupe.
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/features/xianyu/orders/OrderDelivery.kt:105` -- `SavedOrderRead` reparses persisted raw rows before payload construction.
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/CloudTaskClient.kt:449` -- `buildOrdersScreenPayload` writes `row.orderKey` to `order_key`.
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/AutomationStore.kt:1194` -- the durable outbox stores the immutable payload and digest by task/kind/screen.
- `services/control-api/src/cloudctl_api/mobile_service.py:1210` and `services/control-api/src/cloudctl_api/order_delivery.py:158` -- task creation resolves and freezes authenticated account/binding identity.
- `services/control-api/src/cloudctl_api/order_delivery.py:257` -- durable projection lookup uses the current order key scope after receipt admission.
- `services/control-api/src/cloudctl_api/db.py:983` -- `OrderRow` has no account column and is unique by tenant/device/platform/order key.
- `services/control-api/src/cloudctl_api/orders_service.py:53` -- the operator order view does not expose account ownership or an ownership status.
- `apps/web/src/views/OrdersView.vue:473` -- the Web UI labels the generic `orderKey` as an order number.
- `tests/integration/test_order_legacy_guard.py` -- regression coverage for commit `944c773`; this guard must remain distinct from identity work.

## 5. Required Regression Contract for a Future Coding Package

Before implementation can be accepted, isolated fixtures must demonstrate:

1. two rows with identical weak content can remain two source observations;
2. exact receipt replay does not add an observation or mutate admitted evidence;
3. a changed replay remains `PAYLOAD_CONFLICT`;
4. the same proven visible identifier under two authenticated accounts cannot collide;
5. a late older collection cannot overwrite a newer accepted representation;
6. an unknown historical owner stays unknown after account rebinding and new collection;
7. tenant boundaries hold for all new reads and writes;
8. source-observation totals are not returned or rendered as unique-order totals;
9. all legacy projection guard tests continue to pass.

No test may use production records, real credentials, device access, or inferred historical ownership.

## 6. Evidence Required to Freeze the Next Package

The planner must receive at least one of the following before canonical identity or Android extraction is frozen:

- a labelled, authenticated UI fixture showing the identifier and its stable row/detail association; or
- a structured platform/accessibility field with documented semantics and compatibility evidence.

Compatibility decisions are also required for old Companion versions, the legacy batch endpoint, cross-device behavior, query/UI presentation, and migration rollback. Until then, only the invariants in section 2 are frozen.
