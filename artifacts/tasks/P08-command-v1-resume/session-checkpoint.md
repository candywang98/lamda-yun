# P08 CommandV1 checkpoint resume — session checkpoint

Date: 2026-09-09
HEAD at start of this run: b394475 (verify before overwrite; do not assume dirty files unchanged)
Scope: CommandV1 same-taskId resume after WAITING_USER. Not P14. Not next card.
RUN_ID: a0c3f7009eeb4ec492a89dbebce9c4b8
CARD_ID: P08-command-v1-resume

## Gaps (verified in source, still present at this run start)

1. `RecipeEngine.execute` always starts at `recipe.startStateId`. No `resumeFromStateId`. Resume path in `runCommandV1` never passes checkpoint cursor/stateId into execute.
2. `ResumeValidator.guard` for CommandV1 is called with `AutomationTask(steps = emptyList())`, then `if (task.steps.isEmpty()) return` — skips page inspect.
3. WAITING_USER persist is hardcoded `TaskPausedException("open-only", -1, ...)`. STARTED is treated as if nothing completed; last completed is not the real prior SUCCEEDED state.
4. `RecipeState` has no `onPause`. Parse ignores JSON `onPause`.
5. `execute` returns bare `String` so service cannot persist lastCompleted from the engine.

## Intended fix (this run)

- `RecipeState.onPause`; parse it.
- `RecipeExecutionResult(outcome, lastCompletedStateId, lastCompletedIndex)`.
- `execute(..., resumeFromStateId)` starts at that state; does not replay completed states.
- UNKNOWN_PAGE / onPause → WAITING_USER with last **completed** (SUCCEEDED) state, not the STARTED current state.
- Missing/unknown resumeFromStateId fail closed.
- `ResumeValidator.guard(..., recipe)` inspects locator of the next state after last completed (or start state if none).
- `CompanionSyncService`: pass recipe into guard; compute resumeFrom from checkpoint lastCompleted/onSuccess; persist engine lastCompleted, not open-only/-1.
- Tests: resume skips completed tap; pause does not mark current STARTED as completed; recipe-aware page inspect; empty-steps CommandV1 no longer skips inspect.
- Focused unit tests + local companion test/build evidence. No device-pass claim. No P14. No unrelated dirty-file edits. No auto-publish.

## Files to change

- mobile/companion/.../automation/RecipeEngine.kt
- mobile/companion/.../automation/ResumeValidator.kt
- mobile/companion/.../service/CompanionSyncService.kt
- tests: RecipeEngineTest.kt, ResumeValidatorTest.kt
- artifacts/tasks/P08-command-v1-resume/ (knife, this checkpoint, result-P08-command-v1-resume-a0c3f7009eeb4ec492a89dbebce9c4b8.md)

## Do not

- Repeat P14 probe / real publish / pay / delete
- Close signatures or expand auth
- Modify unrelated user working-tree files
- Self-ACCEPT as captain; write result and stop


---

## Recovery checkpoint — 2026-09-09 (run a0c3f7009eeb4ec492a89dbebce9c4b8)

- CARD_ID: P08-command-v1-resume
- RUN_ID: a0c3f7009eeb4ec492a89dbebce9c4b8
- STATUS: STOPPED_BY_CAPTAIN — no implementation this turn; sources left unchanged
- Action this turn: append-only recovery note. No source edits, no tests, no gradle, no probe/network/device, no process kill.

### Unchanged source facts (captain-verified hashes; local re-read matched)

Four target files still original; no patch landed, no test output produced.

1. `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/RecipeEngine.kt`
   - `RecipeState` has no `onPause`
   - `execute(recipe, command, journal): String` always starts at `recipe.startStateId`
   - UNKNOWN_PAGE journals `WAITING_USER` and returns that string; no resume cursor
2. `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/ResumeValidator.kt`
   - `guard(ui, task, checkpoint, payload, pageVerified)` only
   - empty `task.steps` returns before inspect; CommandV1 resume therefore skips page check
3. `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt`
   - `engine.execute(recipe, command) { ... }` — no resumeFromStateId
   - `WAITING_USER` → `persistPaused(..., TaskPausedException("open-only", -1, ...))`
   - `persistPaused` cursor = `paused.lastCompletedStepIndex` or previous loopCursor
4. Tests still call old signatures:
   - `RecipeEngineTest`: `engine.execute(recipe, command(recipe.hash), journal = { _, _ -> })`
   - `ResumeValidatorTest`: `guard(ui, sampleTask(), checkpoint(), payload(), pageVerified = ...)`

### Identified gaps (NOT implemented)

- Resume position not passed into RecipeEngine
- Checkpoint vs page verification not applied on CommandV1 empty-step path
- WAITING_USER checkpoint hardcodes open-only / -1 (STARTED ≠ completed)
- Missing/incompatible checkpoints should fail closed; current missing-resume path persistPaused and returns true

### In-flight / prior tool and HTTP errors this run

- Prior controller attempt on this CARD ended HTTP 524 (retry-after > 60s) around user_prompt `...1788923142959687000.md`
- This run: repeated read/plan loop (~50 turns) with truncated tool stdout; Python extractors succeeded but no write to the four sources
- No gradle/test invocation; no device/adb/network probes this recovery turn
- Artifacts already present and preserved: `_src_dump/`, `pre-edit-git-status.txt`, this `session-checkpoint.md`

### Next controller (captain-narrowed)

Do **not** implement all four modules at once. Next attempt: RecipeEngine optional validated resume state + one no-replay unit test only.

### Stop

Executor stopped writing. Awaiting project retry from captain.
