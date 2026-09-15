# P09 UNKNOWN read-only root-cause review

Reviewed at: 2026-09-16 03:49 CST (Asia/Shanghai)

Task: `a25549e5-145a-4da0-83d8-1e0a8355002a`
Action key: `061e953236331df40f6e00367a058a6c68969485aa5569fcfb9268efbd16bb1c`
Operator decision: `KEEP_WAITING`

## Conclusion

The evidence proves one authorized destructive path entered the controlled ledger and ended in `UNKNOWN`. It does not prove that Xianyu applied the deletion. The target remained visible after the gated action and after one later refresh, so deletion was not observed during the evidence window. The existing task must not be retried.

The production artifacts do not contain the final confirmation node bounds, selected center, window ID, immediate `dispatchGesture` return, callback result, or callback latency. They therefore cannot distinguish Android accepting/completing a synthetic stroke from Xianyu consuming the click or applying the deletion.

## Evidence timeline

- Read-only preflight resolved the target card uniquely. The card was `[0,345][1080,764]`; the rejected full-list wrapper was `[0,345][1080,2337]`.
- The preflight confirmation dialog was `[81,1018][999,1436]`. Its exact title was `[297,1111][783,1198]`, Cancel was `[81,1292][540,1436]`, and Confirm was `[540,1292][999,1436]`.
- The production task ran steps 0 through 7 as succeeded. Step 8 started and did not emit `STEP_SUCCEEDED` before the task entered `RECONCILING`.
- The production log records the card tap at `(540,2280)` and one `GATED_DESTRUCTIVE_INTENT`, but does not record the destructive confirmation bounds or gesture result.
- At `2026-09-15T19:13:39.166881Z`, the task reported `UNKNOWN`: `Controlled observation unavailable; reconciliation required`.
- The target appeared once in the post-gated list and still appeared once after the recorded refresh. Those two XML hierarchies are byte-identical.
- At `2026-09-15T19:16:51.888Z`, the operator selected `KEEP_WAITING`; the task remained `RECONCILING`.

Primary evidence:

- `final-delete/task-latest.json`
- `final-delete/companion-log.txt`
- `final-delete/reconcile-response.json`
- `final-delete/list-after-gated.xml`
- `final-delete/list-after-refresh.xml`
- `readonly-preflight/delete-dialog.xml`

## Code findings

### Fixed: destructive UNKNOWN was followed by success-like steps

`IrreversibleActionGate` durably converts post-authorization failures or an absent controlled postcondition to `UNKNOWN`. `XianyuMaintenanceCommitGate.confirmOnce` returns normally after that durable outcome. Before this review, `LocalAutomationExecutor` returned `false` from the semantic delete branch, journaled the confirmation step as succeeded, and continued with later screenshots/logs. This made step events unable to distinguish gesture rejection/cancellation, a completed gesture with no business proof, and an ordinary successful step.

The semantic delete branch is now a commit barrier: after the one controlled `confirmOnce` call it returns `true`, stops the local step sequence, and leaves the durable ledger/reconciliation path as the only authority. No retry or fallback was added.

Changed files:

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/LocalAutomationExecutor.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/automation/XianyuMaintenanceGateRoutingTest.kt`

Verification:

- Focused gate tests: passed.
- Full Android JVM suite: 55 suites, 380 tests, 0 failures, 0 errors, 0 skipped.
- No APK was built or installed, no device command was issued, no API write was made, and the existing ledger/task was not modified.

### Not yet fixed: resolution-to-dispatch window race

`tapOnce` re-resolves the semantic locator after authorization, so it does not reuse the pre-authorization node. However, resolution scans interactive package roots, reads bounds, then dispatches the gesture later on the main looper. It does not bind and recheck the active window ID or refresh/revalidate bounds immediately before the sole dispatch. A window transition in that interval could make the saved point stale.

The preflight geometry implies a center near `(769.5,1364.0)`, but no production evidence proves that these were the runtime bounds or point. The race is therefore a valid code risk, not a proven explanation for this incident.

### Missing reconciliation observability

A future implementation checkpoint should record, before the only destructive dispatch:

- guarded candidate counts and selected action bounds;
- active window ID and package;
- selected center and resolution timestamp;
- immediate `dispatchGesture` acceptance;
- callback completion/cancellation and latency;
- a post-callback semantic observation indicating whether the same guarded dialog remains.

These records must not treat `onCompleted` as business success. They must preserve one authorization, exactly one gesture, no fallback, no uncertainty retry, and operator reconciliation.

## Next checkpoint

Implement and test active-window binding plus immediate bounds revalidation on the main dispatcher, and add the above evidence fields. This is code/test work only. The current UNKNOWN remains `KEEP_WAITING`; any new deletion attempt requires a new explicit authorization after the operator resolves the current UNKNOWN.
