CARD_ID: P08-command-v1-resume
RUN_ID: 17ddf1edd8ce4f36985df7607049483e
VERDICT: NOT_ACCEPTED

# P08 CommandV1 resume — run 17ddf1edd8ce4f36985df7607049483e

Stop reason: captain directed recovery. Source content of CompanionSyncService.kt was unchanged beyond 900s; attempt 6 of authorized max 6. No additional implementation, tests, probe, deployment, or model retries after the stop order.

## Verdict

Full card NOT_ACCEPTED. Engine resume slice and recipe-aware ResumeValidator slice remain from earlier runs; this run did not land service/checkpoint wiring.

## Source hashes at stop (sha256 of file bytes)

- CompanionSyncService.kt = 488f0b62ecea1d998efe633ab3252ba404f4da6ab0b36a5843b1eb2016a9e6b1 (46091 bytes, mtime 1788860253.798579). Unchanged in this run. No service patch was applied.
- RecipeEngine.kt = e356da13d71930f4d0f26f6f2079776ffe6e62895a7b8ceded9f338ed23af4d5 (6191 bytes). Preserved; matches required engine SHA prefix e356da13.
- ResumeValidator.kt = b66c543debb303c19a80ed8ebbec317d32cb54dac4a09242d0cc33fa6cce397b (5148 bytes). Preserved; matches required validator SHA prefix b66c543d.

No other source files were modified in this run. No hypothetical prose patches landed.

## Observed CompanionSyncService wiring (unchanged)

Verified by reading current source, not by claiming a patch:

1. Resume still calls the legacy empty-step guard: `ResumeValidator.guard(service, AutomationTask(..., steps = emptyList()), checkpoint, payload, resume.pageVerified)` — no recipe / resumeFromStateId overload.
2. Engine execute is still `engine.execute(recipe, command) { stateId, state -> ... }` — no `resumeFromStateId=` from `checkpoint.stateId`.
3. WAITING_USER still persists `TaskPausedException("open-only", -1, "OPEN_ONLY waiting for operator")` rather than next-unexecuted vs last-successful identity.
4. Journal still maps any non-STARTED state to `STEP_SUCCEEDED` (`if (state == "STARTED") "STEP_STARTED" else "STEP_SUCCEEDED"`), so WAITING_USER is not a pause event.
5. persistPaused still keys cursor/itemId off `paused.lastCompletedStepIndex` / `paused.lastCompletedStepId` with fallbacks, not next-unexecuted `stateId` + last genuine success `itemId` scoped to same task/recipe/account/binding.
6. Missing identity is not fail-closed before invoking the new guard: the service still does not require complete account/binding/recipeHash before resume.

## Tests / Gradle this run

None. No new focused service/checkpoint tests were added. RecipeEngineTest and ResumeValidatorTest were not re-run in this run. No Gradle XML/log evidence was produced for RUN_ID 17ddf1edd8ce4f36985df7607049483e.

Prior-run engine/validator unit greens (RecipeEngine 4, ResumeValidator 11) are not claimed as this-run evidence.

## Remaining gaps (must still be done on a later authorized run)

- Wire resume to recipe-aware `ResumeValidator.guard(..., recipe, resumeFromStateId)` after requiring complete identity.
- Pass `resumeFromStateId` from checkpoint `stateId` into `engine.execute`.
- Persist next-unexecuted recipe state in checkpoint.stateId and last genuinely successful state in itemId; STARTED must not advance completed checkpoint.
- Map WAITING_USER to pause, not STEP_SUCCEEDED / open-only/-1.
- Same-task pause / checkpoint reload / resume test proving completed tap not replayed, plus missing/incompatible/page rejection.
- Focused Gradle CompanionSyncService/checkpoint + existing RecipeEngineTest + ResumeValidatorTest with actual exit/XML evidence.

## Out of scope / preserved

- No P14 probe, deploy, or old failure-task rewrite.
- Signatures, authorization, auto-publish, secrets, payments, user-data deletion untouched.
- Engine and validator slices preserved; unrelated dirty edits not rebuilt.
- No device-pass claim from unit tests.

## Stop

Captain stop: unchanged source beyond 900s, attempt 6/6. Result written and work stopped.
