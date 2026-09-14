package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/**
 * im-live slice 2, gap 3: conversation lists longer than the first screen must
 * scroll forward until the tapText value becomes visible, with a bounded scroll
 * budget and no scrolling on ambiguous matches or dead lists.
 */
class TapTextScrollTest {
    private val fixedNow = Instant.parse("2026-09-14T08:00:00Z")

    @Test
    fun scrollsUntilTheValueBecomesVisible() = runBlocking {
        val ui = scrollFakeUi(scrollsNeeded = 3)
        val journal = mutableListOf<String>()

        executor(ui).execute(task(AutomationStep.TapText("open-conversation", 1_000, "长列表会话"))) { step, state ->
            journal += "${step.stepId}:$state"
        }

        assertEquals(3, ui.scrolls)
        assertEquals(listOf("长列表会话"), ui.tapTextTargets)
        assertEquals(listOf("open-conversation:STARTED", "open-conversation:SUCCEEDED"), journal)
    }

    @Test
    fun failsWithoutScrollingWhenTheListCannotScroll() = runBlocking {
        val ui = scrollFakeUi(scrollsNeeded = 1, scrollable = false)

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(AutomationStep.TapText("open-conversation", 1_000, "买家"))) { _, _ -> }
        }

        assertEquals("TAP_TEXT_NOT_FOUND", failure.code)
        assertEquals(0, ui.scrolls)
    }

    @Test
    fun ambiguousMatchesFailWithoutScrolling() = runBlocking {
        val ui = scrollFakeUi(scrollsNeeded = 1).apply { ambiguity = true }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(AutomationStep.TapText("open-conversation", 1_000, "买家"))) { _, _ -> }
        }

        assertEquals("TAP_TEXT_NOT_UNIQUE", failure.code)
        assertEquals(0, ui.scrolls)
    }

    @Test
    fun scrollBudgetIsBounded() = runBlocking {
        val ui = scrollFakeUi(scrollsNeeded = 100)

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(AutomationStep.TapText("open-conversation", 1_000, "买家"))) { _, _ -> }
        }

        assertEquals("TAP_TEXT_NOT_FOUND", failure.code)
        assertEquals(10, ui.scrolls)
    }

    @Test
    fun stepDeadlineStopsScrolling() = runBlocking {
        val ui = scrollFakeUi(scrollsNeeded = 100)
        var clock = 0L

        val failure = assertFailsWith<ExecutorFailure> {
            LocalAutomationExecutor(
                ui = ui,
                now = { fixedNow },
                elapsedMs = { clock += 300L; clock },
                sleep = { delay(1) },
            ).execute(task(AutomationStep.TapText("open-conversation", 1_000, "买家"))) { _, _ -> }
        }

        assertEquals("TAP_TEXT_NOT_FOUND", failure.code)
        assertEquals(1, ui.scrolls)
    }

    private fun executor(ui: ScrollFakeUi) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { 1_000L },
        sleep = { delay(1) },
    )

    private fun task(vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    private fun scrollFakeUi(scrollsNeeded: Int, scrollable: Boolean = true) =
        ScrollFakeUi(scrollsNeeded, scrollable)

    private class ScrollFakeUi(
        private val scrollsNeeded: Int,
        private val scrollable: Boolean,
    ) : LocalAutomationUi {
        var scrolls = 0
        var ambiguity = false
        val tapTextTargets = mutableListOf<String>()

        override fun ensureReady(targetPackage: String) = Unit

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = null

        override suspend fun tapText(targetPackage: String, value: String) {
            if (scrolls >= scrollsNeeded) {
                tapTextTargets += value
                return
            }
            throw ExecutorFailure(
                if (ambiguity) "TAP_TEXT_NOT_UNIQUE" else "TAP_TEXT_NOT_FOUND",
                "Expected exactly one visible '$value' node, found ${if (ambiguity) 2 else 0}",
            )
        }

        override fun canScrollTextList(targetPackage: String): Boolean = scrollable

        override suspend fun scrollTextListForward(targetPackage: String) {
            scrolls += 1
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) = Unit

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = Unit

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) = Unit
    }
}
