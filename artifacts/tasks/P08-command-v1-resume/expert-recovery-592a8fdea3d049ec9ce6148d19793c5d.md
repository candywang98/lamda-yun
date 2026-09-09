CARD_ID: P08-command-v1-resume
RUN_ID: 17ddf1edd8ce4f36985df7607049483e
RECOVERY_ID: 592a8fdea3d049ec9ce6148d19793c5d
VERDICT: PARTIAL_REPAIR_VERIFIED_NOT_FULLY_ACCEPTED

# Expert recovery report — 2026-09-09

DIAGNOSIS:

- Current captain filesystem and command tools executed real operations. The dedicated write probe already existed with SHA-256 `1f634dc3bd7b6515095bd4f2d87bc9a23abb805760ffca111fd37953051eaf84`; this recovery then applied source patches and produced Gradle/XML/APK artifacts. `Operation not permitted` did not recur.
- The stopped worker result file has SHA-256 `c03a99cf65c87ce3910f49f01a441fea5f355d85e80c943e1a01d96efe2a5dba` and states that `CompanionSyncService.kt` remained at SHA-256 `488f0b62ecea1d998efe633ab3252ba404f4da6ab0b36a5843b1eb2016a9e6b1` with no service patch. This is direct evidence of no landed worker edit; the later stop order does not explain the earlier unchanged file.
- Oversized batched reads in this recovery returned truncated tool output at approximately 14k–17k tokens, while exact bounded `nl | sed` ranges returned the required service/engine/store code completely. This reproduces the operational failure mode of losing relevant context through repeated broad reads. No current evidence established an HTTP 524, model-internal defect, missing device, missing token, or missing business approval.
- The pre-repair service used the legacy empty-step resume guard, omitted `resumeFromStateId` when calling `RecipeEngine.execute`, mapped all non-`STARTED` journal states to `STEP_SUCCEEDED`, and saved `open-only/-1` instead of the next unexecuted recipe state and last genuinely successful state.
- Existing storage columns are sufficient: `task_checkpoint.state_id` now carries the next unexecuted recipe state and `item_id` carries the last genuinely successful recipe state. No database schema change was required.
- The first real focused Gradle run exposed a Kotlin compile error at `CompanionSyncService.kt:651`: nullable `JSONObject?` was passed to the recipe-aware guard. It was fixed with an explicit non-null resume checkpoint. The first log wrapper also used zsh's read-only variable name `status`; the rerun used `rc`. These were observable implementation/script errors, not permission failures.

IMPLEMENTATION:

- `CompanionSyncService.kt` now constructs `RecipeResumeProgress`, rejects a missing/incomplete/mismatched resume checkpoint before page inspection, invokes the recipe-aware `ResumeValidator.guard(..., recipe, resumeFromStateId)`, and passes that same state to `RecipeEngine.execute`.
- Recipe journal handling now distinguishes `STARTED`, `SUCCEEDED`, `FAILED`, and `WAITING_USER`. `STARTED` does not advance completed state; `WAITING_USER` remains the current unexecuted state and is recorded as pause rather than success; safe-boundary callbacks observe pause/cancel control.
- `persistRecipePaused` saves the actual `command.attemptId`, snapshot SHA, recipe SHA, account, binding, next state, and last successful state. Resume rejection leaves the existing checkpoint intact and returns the task to paused state instead of silently restarting.
- Added `RecipeResumeProgress.kt` to derive checkpoint movement from the journaled execution path. A failed action follows its actual `onFailure` edge without being marked successful.
- `RecipeEngine.kt` received one focused event-semantic change: non-`UNKNOWN_PAGE` action failures with an `onFailure` edge emit `FAILED`, not `SUCCEEDED`. Prior resume behavior remains intact. `ResumeValidator.kt` was not modified and retains SHA-256 `b66c543debb303c19a80ed8ebbec317d32cb54dac4a09242d0cc33fa6cce397b`.

VERIFICATION:

- Network was not used. Both Gradle commands used `--offline`.
- Focused recovery command passed with exit code 0: `RecipeResumeProgressTest`, `RecipeEngineTest`, and `ResumeValidatorTest`. Log: `gradle-focused-expert-recovery-592a8fdea3d049ec9ce6148d19793c5d.log`, SHA-256 `bb6a36663e244a0d5ef845572558339f2bf5ccbd3be81684711194d1ce8dee1a`.
- Final offline test/build command passed with exit code 0: the same three suites plus `AutomationStoreTest`, followed by `:app:assembleDebug`. Log: `gradle-tests-build-expert-recovery-592a8fdea3d049ec9ce6148d19793c5d.log`, SHA-256 `69f97b3eeacee45446426f067c8995fef0a30d8d1e4cf995fb2139e3b4b85631`.
- Parsed JUnit results: `RecipeResumeProgressTest` 3 tests, `RecipeEngineTest` 4, `ResumeValidatorTest` 11, `AutomationStoreTest` 12; total 30 tests, 0 failures, 0 errors, 0 skipped. Recovery-bound XML copies are stored beside this report.
- The new integration test executes a two-state recipe, pauses on the second state, persists/reloads the same task checkpoint (`stateId=tapB`, `itemId=tapA`), resumes at `tapB`, and verifies that completed `tapA` is not replayed. It also checks missing/incompatible identity rejection and verifies that an `onFailure` transition does not falsely advance last-successful state.
- `assembleDebug` produced `mobile/companion/app/build/outputs/apk/debug/app-debug.apk`, SHA-256 `4ba8407925ade1d1927b3f63123be1c9c2808ccd361897de4b17fbe47132dd27`.
- Final source SHA-256: `CompanionSyncService.kt` `62c090d81dfcba3ed0374277f98a10ac4e06f3a7195ab9ab9f107dcfdd955bea`; `RecipeResumeProgress.kt` `b62ee6a42d31610bf5ed967f49184b1caf59373a22acace6f41253114a7d8227`; `RecipeEngine.kt` `858bf8bc7a1fc420453fedb3dcf54edb8b2d79889237d4655fda1b0c1d8f9d38`; `RecipeResumeProgressTest.kt` `572d900ed71c8747ba3d7a865f7b8be23195e3ff1c4c27f8e62b8aca921c99b3`.
- `git diff --check` passes when scoped to this recovery's tracked source files. Repository-wide `git diff --check` still reports pre-existing unrelated trailing whitespace at `apps/web/src/views/OperationsView.vue:178`; this recovery did not modify that file.
- No device probe, deployment, publish, payment, user-data deletion, signature bypass, model/seat change, P14 work, old failure rewrite, or automatic resume was performed. Unit/build evidence is not device-pass evidence.

HANDOFF:

- Full P08 is not accepted by captain self-review. Give ga exactly one fresh-session worker opportunity without resetting the existing six attempts or action allowances.
- Single next slice: independently review only the diffs in `CompanionSyncService.kt`, `RecipeResumeProgress.kt`, `RecipeEngine.kt`, and `RecipeResumeProgressTest.kt`; rerun the same four offline test suites plus `:app:assembleDebug`; verify from XML that all 30 tests have zero failures/errors and verify the integration assertion that checkpoint reload resumes `tapB` with `itemId=tapA` and does not replay `tapA`.
- If independent regression fails, fix only the demonstrated failure inside this service/checkpoint slice and rerun once. Do not expand into P14, deployment, device probing, signatures, publishing, unrelated dirty files, or a new card. Write a new run-bound result with exact command exits/XML and remaining gaps; do not claim full acceptance from worker prose alone.
