# P08-command-v1-resume result

CARD_ID: P08-command-v1-resume
RUN_ID: 0b35a7123ece463ba64c3b25c16675ed
VERDICT: ACCEPTED

Independent verification of the expert-592a8f four-file CommandV1 checkpoint-resume slice. This run did **not** rewrite source. No P14 / deploy / device / signature / claim / process-kill actions.

## Scope kept

Reviewed only:

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/RecipeResumeProgress.kt`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/RecipeEngine.kt`
- `mobile/companion/app/src/test/java/com/company/cloudctl/companion/service/RecipeResumeProgressTest.kt`

SHA-256 of the four files (unchanged vs expert 592a8fdea3d049ec9ce6148d19793c5d):

| File | SHA-256 |
| --- | --- |
| CompanionSyncService.kt | `62c090d81dfcba3ed0374277f98a10ac4e06f3a7195ab9ab9f107dcfdd955bea` |
| RecipeResumeProgress.kt | `b62ee6a42d31610bf5ed967f49184b1caf59373a22acace6f41253114a7d8227` |
| RecipeEngine.kt | `858bf8bc7a1fc420453fedb3dcf54edb8b2d79889237d4655fda1b0c1d8f9d38` |
| RecipeResumeProgressTest.kt | `572d900ed71c8747ba3d7a865f7b8be23195e3ff1c4c27f8e62b8aca921c99b3` |

Old result files were not rewritten:

- `result-P08-command-v1-resume-17ddf1edd8ce4f36985df7607049483e.md` `c03a99cf65c87ce3910f49f01a441fea5f355d85e80c943e1a01d96efe2a5dba`
- `result-P08-command-v1-resume-2ac2bac297b24795b0699ad694c13606.md` `c9bf1535dd454da38e0b2eced8c89ecf44bdb9ffbb19039a74efe6a4128cb126`
- `result-P08-command-v1-resume-f997be98713f49eda69251239aba57dd.md` `0b449cfaabde479d352061dde63ed1de9fe09c3f2bfb1c6ab4082ce39f25e090`

`artifacts/tasks/P14-recipe-publish` newest files remain `2026-09-09 09:23` (untouched this run).

## Changes reviewed (not rewritten)

1. `RecipeResumeProgress` persists `nextStateId` as checkpoint `stateId` and last successful state as `itemId`. Reload `resume(recipe, command, checkpoint)` refuses blank / terminal / unknown / identity-mismatched checkpoints (`RESUME_LAST_SUCCESS_UNKNOWN` when `itemId` is not in the signed recipe).
2. `RecipeEngine.execute(..., resumeFromStateId)` starts at the next-unexecuted state; blank / terminal / unknown ids are rejected before any action.
3. `CompanionSyncService` reload path: `resumeFromStateId = progress.nextStateId.takeIf { resume != null }`, then `engine.execute(recipe, command, resumeFromStateId = resumeFromStateId)`. Pause/reload does not replay completed taps.
4. Integration test `same task reload resumes pending state without replaying completed tap` closes store, reopens, reads checkpoint, resumes from `tapB`.

## Tests

First Gradle invocation in this run was cache-only (`UP-TO-DATE`, ~3s) and was **discarded**. Independent rerun used `--rerun-tasks`.

Command (cwd `mobile/companion`):

```
JAVA_HOME=/opt/homebrew/opt/openjdk@21
ANDROID_HOME=/Users/wangziheng/CloudCtlExternal/android-sdk
./gradlew :app:testDebugUnitTest \
  --tests com.company.cloudctl.companion.service.RecipeResumeProgressTest \
  --tests com.company.cloudctl.companion.automation.RecipeEngineTest \
  --tests com.company.cloudctl.companion.automation.ResumeValidatorTest \
  --tests com.company.cloudctl.companion.data.AutomationStoreTest \
  :app:assembleDebug \
  --rerun-tasks \
  --console=plain
```

Result: **BUILD SUCCESSFUL in 26s**, `45 actionable tasks: 45 executed`, `EXIT_CODE=0`, wall `Wed Sep 9 16:29:19–16:29:46 CST 2026`.

XML totals (parsed, not inferred): **tests=30 failures=0 errors=0 skipped=0**.

| Suite | tests | failures | errors | skipped | XML timestamp |
| --- | ---: | ---: | ---: | ---: | --- |
| RecipeResumeProgressTest | 3 | 0 | 0 | 0 | 2026-09-09T08:29:45Z |
| RecipeEngineTest | 4 | 0 | 0 | 0 | 2026-09-09T08:29:45Z |
| ResumeValidatorTest | 11 | 0 | 0 | 0 | 2026-09-09T08:29:45Z |
| AutomationStoreTest | 12 | 0 | 0 | 0 | 2026-09-09T08:29:39Z |

HTML index counters: tests=30, failures=0, ignored=0, duration=6.593s, successRate=100%.

`:app:assembleDebug` produced `app/build/outputs/apk/debug/app-debug.apk` (62512214 bytes, mtime `Sep 9 16:29`), applicationId `com.company.cloudctl.companion`, versionName `0.1.0`. APK was **not** installed or published.

## Integration assertion (source + passing test)

`RecipeResumeProgressTest.same task reload resumes pending state without replaying completed tap`:

- After store close/reopen: `latestCheckpoint.stateId == "tapB"` and `itemId == "tapA"`.
- Resume execute uses `resumeFromStateId = resumedProgress.nextStateId` (`tapB`).
- Outcome `SUCCEEDED`; taps recorded = `["locator_b"]` only — `tapA` / `locator_a` is not replayed.

XML testcase name present with no `<failure>` / `<error>` children.

Failed-transition test also asserts `tapA:FAILED:null:tapB` then only `locator_b` is tapped.

## Evidence

- Gradle log: `artifacts/tasks/P08-command-v1-resume/gradle-tests-build-0b35a7123ece463ba64c3b25c16675ed.log`
- XML:
  - `artifacts/tasks/P08-command-v1-resume/TEST-RecipeResumeProgressTest-0b35a7123ece463ba64c3b25c16675ed.xml`
  - `artifacts/tasks/P08-command-v1-resume/TEST-RecipeEngineTest-0b35a7123ece463ba64c3b25c16675ed.xml`
  - `artifacts/tasks/P08-command-v1-resume/TEST-ResumeValidatorTest-0b35a7123ece463ba64c3b25c16675ed.xml`
  - `artifacts/tasks/P08-command-v1-resume/TEST-AutomationStoreTest-0b35a7123ece463ba64c3b25c16675ed.xml`
- HTML:
  - `artifacts/tasks/P08-command-v1-resume/testDebugUnitTest-html-0b35a7123ece463ba64c3b25c16675ed.html`
  - `artifacts/tasks/P08-command-v1-resume/RecipeResumeProgressTest-html-0b35a7123ece463ba64c3b25c16675ed.html`
  - `artifacts/tasks/P08-command-v1-resume/RecipeEngineTest-html-0b35a7123ece463ba64c3b25c16675ed.html`
  - `artifacts/tasks/P08-command-v1-resume/ResumeValidatorTest-html-0b35a7123ece463ba64c3b25c16675ed.html`
  - `artifacts/tasks/P08-command-v1-resume/AutomationStoreTest-html-0b35a7123ece463ba64c3b25c16675ed.html`
- Assemble metadata: `artifacts/tasks/P08-command-v1-resume/assembleDebug-output-metadata-0b35a7123ece463ba64c3b25c16675ed.json`

## Failure reasons

None. Accept criteria met: four-file slice hashes match expert, independent `--rerun-tasks` XML shows 30/0/0, checkpoint reload resumes `tapB` with `itemId=tapA` and does not replay `tapA`, `assembleDebug` succeeded, P14/deploy/device/signatures untouched.

Stopped for captain review. No next card dispatched.
