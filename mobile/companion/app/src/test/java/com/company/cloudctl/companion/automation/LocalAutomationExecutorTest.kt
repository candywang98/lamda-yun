package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class LocalAutomationExecutorTest {
    private val fixedNow = Instant.parse("2026-09-01T08:00:00Z")

    @Test
    fun executesEveryStructuredActionAndJournalsOnlyCompletedSteps() = runBlocking {
        val ui = FakeUi().apply {
            nodes["login"] = node(clickable = true)
            nodes["ready"] = node(enabled = true)
            tapCreates = "username" to node(editable = true, text = "")
        }
        val task = task(
            AutomationStep.Find("1", 1_000, "login"),
            AutomationStep.Tap("2", 1_000, "login", "username"),
            AutomationStep.Input("3", 1_000, "username", "operator", sensitive = true),
            AutomationStep.Wait("4", 1_000, "ready", NodeCondition.ENABLED, 100),
            AutomationStep.Screenshot("5", 1_000, "after_login"),
            AutomationStep.Assert("6", 1_000, "username", NodeCondition.EXISTS),
            AutomationStep.Log("7", 1_000, LogLevel.INFO, "LOGIN_READY"),
        )
        val journal = mutableListOf<String>()

        executor(ui).execute(task) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals((1..7).flatMap { listOf("$it:STARTED", "$it:SUCCEEDED") }, journal)
        assertEquals(listOf("login"), ui.taps)
        assertEquals("operator", ui.nodes.getValue("username").text)
        assertTrue(ui.logs.contains(LogLevel.INFO to "SCREENSHOT_CAPTURED"))
        assertTrue(ui.logs.contains(LogLevel.INFO to "LOGIN_READY"))
        assertTrue(ui.logs.none { it.second.contains("operator") })
    }

    @Test
    fun failsClosedWhenAccessibilityOrWindowReadinessChanges() = runBlocking {
        val ui = FakeUi().apply { readyFailure = ExecutorFailure("WRONG_ACTIVE_PACKAGE", "wrong window") }
        val step = AutomationStep.Find("1", 1_000, "login")
        val journal = mutableListOf<String>()

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(step)) { value, state -> journal += "${value.stepId}:$state" }
        }

        assertEquals("WRONG_ACTIVE_PACKAGE", failure.code)
        assertEquals(listOf("1:STARTED"), journal)
        assertTrue(ui.logs.contains(LogLevel.ERROR to "WRONG_ACTIVE_PACKAGE"))
    }

    @Test
    fun rejectsUnsafeControlsAndIncompleteScreenshotEvidence() = runBlocking {
        val unsafeUi = FakeUi().apply { nodes["publish"] = node(enabled = false, clickable = true) }
        val clickFailure = assertFailsWith<ExecutorFailure> {
            executor(unsafeUi).execute(task(AutomationStep.Tap("1", 1_000, "publish", "done"))) { _, _ -> }
        }
        assertEquals("NODE_NOT_CLICKABLE", clickFailure.code)
        assertTrue(unsafeUi.taps.isEmpty())

        val screenshotUi = FakeUi().apply { screenshot = ScreenshotEvidence("", 0, "invalid") }
        val screenshotFailure = assertFailsWith<ExecutorFailure> {
            executor(screenshotUi).execute(task(AutomationStep.Screenshot("1", 1_000, "proof"))) { _, _ -> }
        }
        assertEquals("SCREENSHOT_INVALID", screenshotFailure.code)
    }

    @Test
    fun enforcesAssertionsExpiryAndVerifiedReplacement() = runBlocking {
        val assertionFailure = assertFailsWith<ExecutorFailure> {
            executor(FakeUi()).execute(task(AutomationStep.Assert("1", 1_000, "missing", NodeCondition.EXISTS))) { _, _ -> }
        }
        assertEquals("ASSERTION_FAILED", assertionFailure.code)

        val inputUi = FakeUi().apply {
            nodes["field"] = node(editable = true, text = "old")
            applyInput = false
        }
        val inputFailure = assertFailsWith<ExecutorFailure> {
            executor(inputUi).execute(task(AutomationStep.Input("1", 100, "field", "new", false))) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", inputFailure.code)

        val expired = task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "NEVER_RUN")).copy(expiresAt = fixedNow)
        val expiryFailure = assertFailsWith<ExecutorFailure> {
            executor(FakeUi()).execute(expired) { _, _ -> }
        }
        assertEquals("TASK_EXPIRED", expiryFailure.code)
    }

    @Test
    fun executesIdlefishTextPublishFormAndStopsBeforeMediaOrSubmit() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            nodes["xianyu_home_sell"] = node(clickable = true)
            tapCreates = "xianyu_publish_entry" to node(clickable = true)
            followUpTapCreates = "xianyu_publish_page" to node()
        }
        val journal = mutableListOf<String>()
        val task = task(
            TargetLocatorRegistry.XIANYU_PACKAGE,
            AutomationStep.Find("find-home-sell", 1_000, "xianyu_home_sell"),
            AutomationStep.Tap("open-sell", 1_000, "xianyu_home_sell", "xianyu_publish_entry"),
            AutomationStep.Tap("open-publish", 1_000, "xianyu_publish_entry", "xianyu_publish_page"),
            AutomationStep.Wait("wait-publish-page", 1_000, "xianyu_publish_page", NodeCondition.EXISTS, 100),
            AutomationStep.Input("fill-description", 1_000, "xianyu_description", "自用闲置", false),
            AutomationStep.Input("fill-price", 1_000, "xianyu_price", "128", false),
            AutomationStep.Screenshot("capture-form", 1_000, "xianyu_publish_form"),
            AutomationStep.Log("mark-ready", 1_000, LogLevel.INFO, "XIANYU_PUBLISH_FORM_READY"),
        ).also {
            ui.nodes["xianyu_description"] = node(editable = true, text = "")
            ui.nodes["xianyu_price"] = node(editable = true, text = "")
        }

        executor(ui).execute(task) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(
            listOf("xianyu_home_sell", "xianyu_publish_entry"),
            ui.taps,
        )
        assertEquals("自用闲置", ui.nodes.getValue("xianyu_description").text)
        assertEquals("128", ui.nodes.getValue("xianyu_price").text)
        assertTrue(journal.last() == "mark-ready:SUCCEEDED")
        assertTrue(ui.logs.contains(LogLevel.INFO to "XIANYU_PUBLISH_FORM_READY"))
        assertTrue("xianyu_add_image" !in ui.taps)
        assertTrue("xianyu_publish_button" !in ui.taps)
    }

    private fun executor(ui: FakeUi) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { 1_000L },
        sleep = { delay(1) },
    )

    private fun task(vararg steps: AutomationStep) = task(TargetLocatorRegistry.COMPANION_PACKAGE, *steps)

    private fun task(targetPackage: String, vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = targetPackage,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    private fun node(
        enabled: Boolean = true,
        visible: Boolean = true,
        clickable: Boolean = false,
        editable: Boolean = false,
        text: String? = null,
    ) = LocalNodeState(enabled, visible, clickable, editable, text)

    private class FakeUi : LocalAutomationUi {
        val nodes = mutableMapOf<String, LocalNodeState>()
        val taps = mutableListOf<String>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        var readyFailure: ExecutorFailure? = null
        var applyInput = true
        var allowedPackage = TargetLocatorRegistry.COMPANION_PACKAGE
        var tapCreates: Pair<String, LocalNodeState>? = null
        var followUpTapCreates: Pair<String, LocalNodeState>? = null
        var screenshot = ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun ensureReady(targetPackage: String) {
            readyFailure?.let { throw it }
            check(targetPackage == allowedPackage)
        }

        override fun inspect(targetPackage: String, locatorRef: String) = nodes[locatorRef]

        override suspend fun tap(targetPackage: String, locatorRef: String) {
            taps += locatorRef
            val created = if (taps.size == 1) tapCreates else followUpTapCreates ?: tapCreates
            created?.let { nodes[it.first] = it.second }
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            if (applyInput) nodes[locatorRef] = nodes.getValue(locatorRef).copy(text = value)
        }

        override suspend fun screenshot(taskId: String, label: String) = screenshot

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
}
