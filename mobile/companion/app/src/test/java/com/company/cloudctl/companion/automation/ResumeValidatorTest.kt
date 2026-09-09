package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import org.json.JSONObject

class ResumeValidatorTest {
    @Test
    fun refusesUnverifiedResumeWithoutInspectingThePage() {
        val ui = FakeUi()
        val failure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(ui, sampleTask(), checkpoint(), payload(), pageVerified = false)
        }
        assertEquals("RESUME_PAGE_UNVERIFIED", failure.code)
        assertEquals(0, ui.inspectCount)
    }

    @Test
    fun refusesWhenCurrentPageDoesNotMatchCheckpoint() {
        val ui = FakeUi()
        val failure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(ui, sampleTask(), checkpoint(loopCursor = 0), payload(), pageVerified = true)
        }
        assertEquals("RESUME_PAGE_MISMATCH", failure.code)
        assertEquals(1, ui.inspectCount)
    }

    @Test
    fun continuesWhenVerifiedPageMatchesTapPostcondition() {
        val ui = FakeUi(visible = setOf("username"))
        ResumeValidator.guard(ui, sampleTask(), checkpoint(loopCursor = 1), payload(), pageVerified = true)
        assertEquals(1, ui.inspectCount)
        assertEquals("username", ResumeValidator.expectedLocator(sampleTask(), 1))
    }

    @Test
    fun refusesWhenAccountOrBindingChanged() {
        val accountFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                FakeUi(visible = setOf("username")),
                sampleTask(),
                checkpoint(loopCursor = 1),
                payload().put("accountId", "account-b"),
                pageVerified = true,
            )
        }
        assertEquals("RESUME_ACCOUNT_CHANGED", accountFailure.code)

        val bindingFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                FakeUi(visible = setOf("username")),
                sampleTask(),
                checkpoint(loopCursor = 1),
                payload().put("bindingVersion", 2),
                pageVerified = true,
            )
        }
        assertEquals("RESUME_BINDING_CHANGED", bindingFailure.code)

        val recipeFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                FakeUi(visible = setOf("username")),
                sampleTask(),
                checkpoint(loopCursor = 1),
                payload().put("recipeHash", "other-recipe"),
                pageVerified = true,
            )
        }
        assertEquals("RESUME_RECIPE_INCOMPATIBLE", recipeFailure.code)
    }

    @Test
    fun recipeAwareGuardInspectsLocatorEvenWhenTaskStepsAreEmpty() {
        val ui = FakeUi(visible = setOf("locator_b"))
        ResumeValidator.guard(
            ui,
            emptyStepsTask(),
            checkpoint(),
            payload(),
            pageVerified = true,
            recipe = twoTapRecipe(),
            resumeFromStateId = "tapB",
        )
        assertEquals(1, ui.inspectCount)
        assertEquals("locator_b", ui.inspected.last())
    }

    @Test
    fun recipeAwareGuardRefusesMissingOrInvisibleLocator() {
        val missing = FakeUi()
        val missingFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                missing,
                emptyStepsTask(),
                checkpoint(),
                payload(),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_PAGE_MISMATCH", missingFailure.code)
        assertEquals(1, missing.inspectCount)

        val hidden = FakeUi(presentButHidden = setOf("locator_b"))
        val hiddenFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                hidden,
                emptyStepsTask(),
                checkpoint(),
                payload(),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_PAGE_MISMATCH", hiddenFailure.code)
        assertEquals(1, hidden.inspectCount)
    }

    @Test
    fun recipeAwareGuardRefusesUnknownStateWithoutInspecting() {
        val ui = FakeUi(visible = setOf("locator_b"))
        val failure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                ui,
                emptyStepsTask(),
                checkpoint(),
                payload(),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "missing",
            )
        }
        assertEquals("RESUME_UNKNOWN_STATE", failure.code)
        assertEquals(0, ui.inspectCount)
    }

    @Test
    fun recipeAwareGuardRefusesUnverifiedPageWithoutInspecting() {
        val ui = FakeUi(visible = setOf("locator_b"))
        val failure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                ui,
                emptyStepsTask(),
                checkpoint(),
                payload(),
                pageVerified = false,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_PAGE_UNVERIFIED", failure.code)
        assertEquals(0, ui.inspectCount)
    }

    @Test
    fun recipeAwareGuardRefusesIdentityMismatchWithoutInspecting() {
        val accountUi = FakeUi(visible = setOf("locator_b"))
        val accountFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                accountUi,
                emptyStepsTask(),
                checkpoint(),
                payload().put("accountId", "account-b"),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_ACCOUNT_CHANGED", accountFailure.code)
        assertEquals(0, accountUi.inspectCount)

        val bindingUi = FakeUi(visible = setOf("locator_b"))
        val bindingFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                bindingUi,
                emptyStepsTask(),
                checkpoint(),
                payload().put("bindingVersion", 2),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_BINDING_CHANGED", bindingFailure.code)
        assertEquals(0, bindingUi.inspectCount)

        val recipeUi = FakeUi(visible = setOf("locator_b"))
        val recipeFailure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                recipeUi,
                emptyStepsTask(),
                checkpoint(),
                payload().put("recipeHash", "other-recipe"),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_RECIPE_INCOMPATIBLE", recipeFailure.code)
        assertEquals(0, recipeUi.inspectCount)
    }

    @Test
    fun recipeAwareGuardFailsClosedWhenStateHasNoLocator() {
        val ui = FakeUi(visible = setOf("locator_b"))
        val failure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                ui,
                emptyStepsTask(),
                checkpoint(),
                payload(),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "fill",
            )
        }
        assertEquals("RESUME_LOCATOR_UNCHECKABLE", failure.code)
        assertEquals(0, ui.inspectCount)
    }

    @Test
    fun recipeAwareGuardRefusesTargetPackageMismatchWithoutInspecting() {
        val ui = FakeUi(visible = setOf("locator_b"))
        val failure = assertFailsWith<ExecutorFailure> {
            ResumeValidator.guard(
                ui,
                emptyStepsTask(targetPackage = "com.xingin.xhs"),
                checkpoint(),
                payload(),
                pageVerified = true,
                recipe = twoTapRecipe(),
                resumeFromStateId = "tapB",
            )
        }
        assertEquals("RESUME_TARGET_MISMATCH", failure.code)
        assertEquals(0, ui.inspectCount)
    }

    private fun sampleTask() = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = TargetLocatorRegistry.COMPANION_PACKAGE,
        issuedAt = java.time.Instant.parse("2026-09-01T08:00:00Z"),
        expiresAt = java.time.Instant.parse("2026-09-01T08:10:00Z"),
        maxRunSeconds = 60,
        steps = listOf(
            AutomationStep.Find("1", 1_000, "login"),
            AutomationStep.Tap("2", 1_000, "login", "username"),
            AutomationStep.Input("3", 1_000, "username", "operator", sensitive = true),
        ),
    )

    private fun emptyStepsTask(
        targetPackage: String = TargetLocatorRegistry.XIANYU_PACKAGE,
    ) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = targetPackage,
        issuedAt = java.time.Instant.parse("2026-09-01T08:00:00Z"),
        expiresAt = java.time.Instant.parse("2026-09-01T08:10:00Z"),
        maxRunSeconds = 60,
        steps = emptyList(),
    )

    private fun twoTapRecipe() = RecipePackage(
        id = "recipe-xianyu-publish-1",
        hash = "recipe",
        minEngineVersion = 1,
        app = TargetLocatorRegistry.XIANYU_PACKAGE,
        commandTypes = setOf("xianyu.publish_listing.v1"),
        startStateId = "tapA",
        maxIterations = 12,
        maxDurationMs = 90_000,
        states = mapOf(
            "tapA" to RecipeState("tapA", "tap", "locator_a", "tapB", "FAILED", false),
            "tapB" to RecipeState("tapB", "tap", "locator_b", "SUCCEEDED", "FAILED", false),
            "fill" to RecipeState("fill", "checkpoint", null, "SUCCEEDED", null, true),
        ),
    )

    private fun checkpoint(loopCursor: Int = 0) = JSONObject()
        .put("accountId", "account-a")
        .put("bindingVersion", 1)
        .put("recipeHash", "recipe")
        .put("loopCursor", loopCursor)

    private fun payload() = JSONObject()
        .put("accountId", "account-a")
        .put("bindingVersion", 1)
        .put("recipeHash", "recipe")

    private class FakeUi(
        private val visible: Set<String> = emptySet(),
        private val presentButHidden: Set<String> = emptySet(),
    ) : LocalAutomationUi {
        var inspectCount = 0
        val inspected = mutableListOf<String>()

        override fun ensureReady(targetPackage: String) = Unit

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? {
            inspectCount += 1
            inspected += locatorRef
            return when {
                locatorRef in visible -> LocalNodeState(
                    enabled = true,
                    visible = true,
                    clickable = true,
                    editable = false,
                    text = null,
                )
                locatorRef in presentButHidden -> LocalNodeState(
                    enabled = true,
                    visible = false,
                    clickable = false,
                    editable = false,
                    text = null,
                )
                else -> null
            }
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit
        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))
        override fun log(level: LogLevel, messageCode: String) = Unit
    }
}
