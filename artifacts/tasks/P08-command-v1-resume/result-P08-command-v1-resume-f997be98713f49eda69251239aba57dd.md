# P08-command-v1-resume result

CARD_ID: P08-command-v1-resume
RUN_ID: f997be98713f49eda69251239aba57dd
VERDICT: NOT_ACCEPTED

This run is the captain-narrowed slice only: RecipeEngine optional validated resume state + one no-replay unit test. It is **not** the full four-module CommandV1 pause/resume card.

## Scope kept

- Edited: `RecipeEngine.kt`, `RecipeEngineTest.kt`
- Not edited this run: `CompanionSyncService.kt`, `ResumeValidator.kt`, `ResumeValidatorTest.kt`
- No P14 / device / network / claim / process-kill actions
- `execute(...)` still returns `String`; optional `resumeFromStateId` sits **before** the trailing `journal` lambda so existing `engine.execute(recipe, command) { ... }` still compiles

## Changes

File: `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/RecipeEngine.kt`
SHA-256: `e356da13d71930f4d0f26f6f2079776ffe6e62895a7b8ceded9f338ed23af4d5` (135 lines)

```kotlin
suspend fun execute(
    recipe: RecipePackage,
    command: CommandV1,
    resumeFromStateId: String? = null,
    journal: (String, String) -> Unit,
): String
```

- `resumeFromStateId == null` → `recipe.startStateId` (fresh run)
- explicit ID is the **next unexecuted** state, not the last completed state
- `resolveResumeStart` rejects blank / unknown / terminal IDs **before** `ui.ensureReady` / `runAction` / journal
- existing hash + app checks unchanged: `recipe.hash == command.recipeSha256`, `recipe.app == command.targetPackage`

File: `mobile/companion/app/src/test/java/com/company/cloudctl/companion/automation/RecipeEngineTest.kt`
SHA-256: `3b8b494ba605278a1223b916a87a2c1293920783230947761e6e8c69b7f0fa4c` (150 lines)

New test `resumesFromNextUnexecutedStateWithoutReplayingCompletedTap`:
- two-tap graph `tapA(locator_a) → tapB(locator_b) → SUCCEEDED`
- fresh execute taps `[locator_a, locator_b]`
- `resumeFromStateId = "tapB"` taps `[locator_b]` only (no replay of completed tapA)
- invalid IDs (`""`, `"SUCCEEDED"`, `"no-such-state"`) throw `IllegalArgumentException` and produce **zero** taps

## Tests

Command:

```
./gradlew :app:testDebugUnitTest --tests com.company.cloudctl.companion.automation.RecipeEngineTest
```

CWD: `/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source/mobile/companion`

Result: **BUILD SUCCESSFUL in 31s**

XML `testsuite`: tests=4 skipped=0 failures=0 errors=0 timestamp=2026-09-09T04:54:19 time=0.106

| test | time |
|---|---|
| loopLimitAndUnknownPagePause | 0.098 |
| resumesFromNextUnexecutedStateWithoutReplayingCompletedTap | 0.003 |
| completesLocalGraphWithoutCloudClicks | 0.002 |
| rejectsWrongHashAndUnknownAction | 0.003 |

Offline first attempt failed (`No cached version of org.bouncycastle:bcprov-jdk18on:1.85.2`). Online rerun succeeded. Evidence preserved for both.

## Evidence paths

- Gradle online log: `/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source/artifacts/tasks/P08-command-v1-resume/gradle-RecipeEngineTest-online-f997be98713f49eda69251239aba57dd.log`
- Gradle offline fail log: `/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source/artifacts/tasks/P08-command-v1-resume/gradle-RecipeEngineTest-f997be98713f49eda69251239aba57dd.log`
- JUnit XML copy: `/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source/artifacts/tasks/P08-command-v1-resume/TEST-RecipeEngineTest-f997be98713f49eda69251239aba57dd.xml`
- HTML report copy: `/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source/artifacts/tasks/P08-command-v1-resume/RecipeEngineTest-html-f997be98713f49eda69251239aba57dd.html`
- Live XML: `/Users/wangziheng/Desktop/LAMDA云控系统/cloudctl-source/mobile/companion/app/build/test-results/testDebugUnitTest/TEST-com.company.cloudctl.companion.automation.RecipeEngineTest.xml`

## Why NOT_ACCEPTED (full card still open)

Card criterion: pause then continue the **same CommandV1** from a completed checkpoint without replaying consumed side effects.

This slice only proves engine-level start-state selection:

1. `CompanionSyncService` still calls `engine.execute(recipe, command) { stateId, state -> ... }` with default `resumeFromStateId = null`. No checkpoint is passed through.
2. `ResumeValidator` was not wired and was not edited this run.
3. No persistPaused / WAITING_USER resume path / same-command identity check in this slice.
4. Pre-existing uncommitted `CompanionSyncService.kt` working-tree diff (614 insertions / 81 deletions vs HEAD) was **left untouched**.

Unchanged this run:

- CompanionSyncService.kt SHA-256 `488f0b62ecea1d998efe633ab3252ba404f4da6ab0b36a5843b1eb2016a9e6b1`
- ResumeValidator.kt SHA-256 `54ef46093a7977ceea2f67514b230d4661776359dff1943185a3f5c50ff8f878`
- ResumeValidatorTest.kt SHA-256 `b27649caab506001913d069a7a114f3dbe3e10c3641807da3ee66b5c910fd532`

## Stop

Executor stopped after writing this result. Captain reviews. No next card dispatched.
