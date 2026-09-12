# P09 Recipe/service wiring: p09-wiring/20260912.1

This extends p09-ledger/20260910.1 without changing its identity algorithm or its
Companion-only authorization scope. Real platform G3 remains blocked_hardware.

- Interpret the existing signed graph.commitActionId, not a new action language.
  A commit is one tap with a distinct approved postcondition locator. It exits to
  SUCCEEDED; no failure branch or second commit is executed. Invalid commit IDs,
  duplicate states and a known publish locator outside that commit are rejected.
- A marked commit without a ledger adapter fails closed before any graph action.
  The adapter persists local intent, obtains the once-only server grant, checks
  cancellation/control/lease again, invokes exactly one UI action, and observes
  the separate postcondition. It never treats tap completion as applied.
- Before/post screenshots are content-hashed evidence references. A postcondition
  already present before the action is rejected. Missing, stale or contradictory
  evidence leaves the action UNKNOWN and the task RECONCILING.
- The graph stops after a commit attempt, including a reported APPLIED result.
  Only authenticated matching revision>0 resolution can finish the local task.
  Service polls persisted unresolved identities before claiming new work; it does
  not replay a recipe or require the recipe cache to synchronize resolution.
- The existing unmarked Companion ledger probe contract stays supported for old
  instrumentation. Marked graphs must request their declared commitActionId.
  No platform whitelist expansion, migration, new side-effect permission or
  automatic operator reconciliation is introduced in this change.

Acceptance: focused Python recipe/ledger tests; Android RecipeEngine and adapter
unit tests plus hardware instrumentation with isolated storage. Record hardware
and synthetic/API-fixture evidence separately. Real publish/content/account
acceptance is separate and cannot be inferred from these tests.
