# P08-command-v1-resume result

CARD_ID: P08-command-v1-resume
RUN_ID: 2ac2bac297b24795b0699ad694c13606
VERDICT: NOT_ACCEPTED

This run is the captain-narrowed slice only: recipe-aware `ResumeValidator.guard(RecipePackage, next-unexecuted stateId)` plus unit tests. It is **not** the full CommandV1 pause/resume card. No service/store/engine rewrite. No next card dispatched.

## Scope kept

- Only two files were written in this slice:
  - `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/ResumeValidator.kt`
  - `mobile/companion/app/src/test/java/com/company/cloudctl/companion/automation/ResumeValidatorTest.kt`
- Legacy `guard(ui, task, checkpoint, payload, pageVerified)` kept as-is (loopCursor / `expectedLocator` path).
- New overload: `guard(ui, task, checkpoint, payload, pageVerified, recipe, resumeFromStateId)`.
- Empty `task.steps` must not skip locator inspection.
- Fail-closed when the resume state has no inspectable locator (`RESUME_LOCATOR_UNCHECKABLE`).
- Identity checks (account / binding / recipeHash / targetPackage) run before inspect.
- `pageVerified=false` refuses without inspecting.
- Unknown `resumeFromStateId` refuses without inspecting (`RESUME_UNKNOWN_STATE`).
- RecipeEngine.kt SHA-256 preserved: `e356da13d71930f4d0f26f6f2079776ffe6e62895a7b8ceded9f338ed23af4d5`
- CompanionSyncService.kt SHA-256 unchanged: `488f0b62ecea1d998efe633ab3252ba404f4da6ab0b36a5843b1eb2016a9e6b1`
- No P14 / device / network / claim / process-kill actions.

## Changes

Recipe-aware `ResumeValidator.guard` now:

1. Requires `pageVerified=true` (`RESUME_PAGE_UNVERIFIED`) before any inspect.
2. Requires checkpoint/payload identity match (accountId, bindingVersion, recipeHash, targetPackage) before inspect.
3. Requires `recipe.sha256` matches checkpoint `recipeHash` when both are present (`RESUME_RECIPE_INCOMPATIBLE`).
4. Looks up `recipe.states[resumeFromStateId]` — missing → `RESUME_UNKNOWN_STATE`, no inspect.
5. Takes `state.locatorRef` of the next-unexecuted state; blank/null → `RESUME_LOCATOR_UNCHECKABLE`, no inspect.
6. Inspects that locator; missing or not visible → `RESUME_PAGE_MISMATCH`.
7. Empty `task.steps` does **not** bypass the recipe locator inspect (legacy `expectedLocator` returning null is no longer the resume path for recipe-aware calls).

Legacy `guard` still uses `checkpoint.loopCursor` + `task.steps` and still returns early when `expectedLocator` is null. That path is unchanged so existing CommandV1/linear-step tests keep their prior semantics.

## Tests

Command (cwd `mobile/companion`):

```
./gradlew :app:testDebugUnitTest \
  --tests com.company.cloudctl.companion.automation.ResumeValidatorTest \
  --tests com.company.cloudctl.companion.automation.RecipeEngineTest \
  --console=plain
```

Result: **BUILD SUCCESSFUL in 21s**, Gradle exit 0, timestamp `2026-09-09T05:37:48Z`.

ResumeValidatorTest: **11 tests, 0 failures, 0 errors, time=0.006s**

- `refusesUnverifiedResumeWithoutInspectingThePage` (legacy)
- `continuesWhenVerifiedPageMatchesTapPostcondition` (legacy)
- `refusesWhenCurrentPageDoesNotMatchCheckpoint` (legacy)
- `refusesWhenAccountOrBindingChanged` (legacy)
- `recipeAwareGuardInspectsLocatorEvenWhenTaskStepsAreEmpty` — inspects `locator_b` once even with empty steps
- `recipeAwareGuardRefusesUnverifiedPageWithoutInspecting` — `pageVerified=false`, inspectCount=0
- `recipeAwareGuardRefusesMissingOrInvisibleLocator` — missing / not-visible → `RESUME_PAGE_MISMATCH`
- `recipeAwareGuardRefusesUnknownStateWithoutInspecting` — inspectCount=0, `RESUME_UNKNOWN_STATE`
- `recipeAwareGuardRefusesIdentityMismatchWithoutInspecting` — account / recipeHash mismatch, inspectCount=0
- `recipeAwareGuardRefusesTargetPackageMismatchWithoutInspecting` — inspectCount=0
- `recipeAwareGuardFailsClosedWhenStateHasNoLocator` — checkpoint state, inspectCount=0, `RESUME_LOCATOR_UNCHECKABLE`

RecipeEngineTest: **4 tests, 0 failures, 0 errors, time=0.056s** (regression; engine file not rewritten)

- `loopLimitAndUnknownPagePause`
- `resumesFromNextUnexecutedStateWithoutReplayingCompletedTap`
- `completesLocalGraphWithoutCloudClicks`
- `rejectsWrongHashAndUnknownAction`

## Evidence paths

- Gradle log: `artifacts/tasks/P08-command-v1-resume/gradle-ResumeValidatorTest-RecipeEngineTest-2ac2bac297b24795b0699ad694c13606.log`
- JUnit XML: `artifacts/tasks/P08-command-v1-resume/TEST-com.company.cloudctl.companion.automation.ResumeValidatorTest-2ac2bac297b24795b0699ad694c13606.xml`
- JUnit XML: `artifacts/tasks/P08-command-v1-resume/TEST-com.company.cloudctl.companion.automation.RecipeEngineTest-2ac2bac297b24795b0699ad694c13606.xml`
- HTML: `artifacts/tasks/P08-command-v1-resume/ResumeValidatorTest-html-2ac2bac297b24795b0699ad694c13606.html`
- HTML: `artifacts/tasks/P08-command-v1-resume/RecipeEngineTest-html-2ac2bac297b24795b0699ad694c13606.html`
- Suite HTML: `artifacts/tasks/P08-command-v1-resume/testDebugUnitTest-html-2ac2bac297b24795b0699ad694c13606.html`

## SHA-256 after this run

- RecipeEngine.kt `e356da13d71930f4d0f26f6f2079776ffe6e62895a7b8ceded9f338ed23af4d5` (preserved; 135 lines / 6191 bytes)
- ResumeValidator.kt `b66c543debb303c19a80ed8ebbec317d32cb54dac4a09242d0cc33fa6cce397b` (112 lines / 5148 bytes)
- ResumeValidatorTest.kt `0a6d6871b8ce20d98e9e9ac2af0e9a91885b23cfb22b2847b7806f819695ea1d` (332 lines / 11921 bytes)
- RecipeEngineTest.kt `3b8b494ba605278a1223b916a87a2c1293920783230947761e6e8c69b7f0fa4c` (not rewritten this run)
- CompanionSyncService.kt `488f0b62ecea1d998efe633ab3252ba404f4da6ab0b36a5843b1eb2016a9e6b1` (unchanged)

HEAD at verification: `b394475c56a07b0ea660531222d182646e1c7e66` (`b394475`). The two ResumeValidator files remain untracked (`??`), same as RecipeEngine.kt from the prior slice.

## Why NOT_ACCEPTED (full card still open)

Card criterion: pause then continue the **same CommandV1** from a completed checkpoint without replaying consumed side effects.

This slice only proves validator-level recipe resume:

- recipe-aware guard inspects the next-unexecuted state's locator even when `task.steps` is empty
- fail-closed on unknown state / no locator / unverified page / identity mismatch
- engine-level `resumeFromStateId = "tapB"` still taps `[locator_b]` only (prior slice, regression-green here)

It does **not** prove:

- CompanionSyncService WAITING_USER → same-taskId resume path
- CommandV1 checkpoint persistence of `resumeFromStateId` / recipeHash / account / binding
- executor wiring that passes recipe + next-unexecuted stateId into this new `guard` overload
- end-to-end "pause then continue the same CommandV1 without replaying consumed side effects"

No store, no service, no engine rewrite in this run. Captain reviews. No next card dispatched.

## Stop

Executor stopped after writing this result. Captain reviews. No next card dispatched.
