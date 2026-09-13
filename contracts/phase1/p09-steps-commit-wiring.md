# P09 steps-publish commit wiring: p09-steps-commit/20260913.1

Extends `p09-wiring/20260912.1` to the legacy allowlisted idlefish steps task.
Real publish remains gated: no commit without this ledger, at most one physical
submit, and no terminal SUCCEEDED without authenticated server resolution.

## Scope expansion (deliberate)

- The Companion action ledger accepts exactly one additional task shape:
  legacy `cloudctl.mobile/v1` steps tasks with `targetPackage` idlefish whose
  steps contain exactly one `ui.tap` on `xianyu_publish_button` plus a
  `xianyu_publish_success` postcondition step and a `ui.input` on
  `xianyu_description`. Any other legacy task keeps `G3_NOT_ACCEPTED`.
- Action id is fixed: `click-publish`. Everything else (probe commands,
  recipes, other packages, deletes, charges) is unchanged and still refused.

## Frozen identity for steps tasks

- Canonical steps string: steps joined by `\n`; within a step, present keys
  sorted alphabetically, rendered `key=value`; scalars: bool `true|false`,
  int decimal, string verbatim. Absent keys are omitted.
- `snapshotSha256 = recipeSha256 = sha256(canonical steps)`.
- `commandType = xianyu.publish_listing.steps.v1`;
  `accountId = <deviceId>` (platform-account binding is future work;
  the device id plus content hash bind this identity); `bindingVersion`
  defaults to 0; `recipeVersionId = steps`.
- Any change to step content changes the action key/parameter hash and is a
  different action. Old intents can never authorize new content.

## Commit flow (mirrors the recipe adapter)

1. On reaching the publish step, the runner first checks for a recorded
   action: a prior intent only ever reconciles; it never re-taps.
2. Pre-checks: control/lease still valid, target app foreground, publish
   success indicator absent, before-screenshot evidence hashed.
3. Persist local INTENT, obtain the once-only server grant (201 AUTHORIZED),
   then exactly one `tapOnce` on the publish locator. No fallback click path.
4. Independent postcondition observation (publish success locator, bounded
   polling) with changed screenshot evidence; observation failure reports
   UNKNOWN and never replays a conflicting outcome.
5. The run stops at the commit step regardless of APPLIED or UNKNOWN; the
   task stays RECONCILING and only a server resolution with
   `resolutionRevision > 0` (operator verify) closes it as SUCCEEDED/FAILED.
6. Resume/retry/cancel cannot bypass an unresolved action; a new task with
   different steps produces a different action identity.

Acceptance: focused backend ledger tests including steps-task identity
mismatch; Android unit tests for routing, stop-after-commit, and gate
recovery; one real G3 run for the single authorized listing. No other
platform, no delete/charge actions, no automatic operator reconciliation.
