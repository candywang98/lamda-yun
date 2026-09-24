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
    fun pausesDuringWaitWithoutCompletingTheGesture() = runBlocking {
        val ui = FakeUi()
        val control = ExecutionControl()
        val journal = mutableListOf<String>()
        val paused = assertFailsWith<TaskPausedException> {
            executor(ui).execute(
                task(AutomationStep.Wait("1", 1_000, "login", NodeCondition.EXISTS, 100)),
                control,
            ) { step, state ->
                journal += "${step.stepId}:$state"
                if (state == "STARTED") control.requestPause("operator taking over")
            }
        }
        assertEquals(null, paused.lastCompletedStepId)
        assertEquals(-1, paused.lastCompletedStepIndex)
        assertEquals(listOf("1:STARTED"), journal)
        assertTrue(ui.taps.isEmpty())
    }

    @Test
    fun pausesBetweenCompletedStepsWithoutStartingTheNextGesture() = runBlocking {
        val ui = FakeUi().apply {
            nodes["login"] = node(clickable = true)
            tapCreates = "username" to node(editable = true, text = "")
        }
        val control = ExecutionControl()
        val journal = mutableListOf<String>()
        val paused = assertFailsWith<TaskPausedException> {
            executor(ui).execute(
                task(
                    AutomationStep.Find("1", 1_000, "login"),
                    AutomationStep.Tap("2", 1_000, "login", "username"),
                    AutomationStep.Input("3", 1_000, "username", "operator", sensitive = true),
                ),
                control,
            ) { step, state ->
                journal += "${step.stepId}:$state"
                if (step.stepId == "1" && state == "SUCCEEDED") control.requestPause("operator taking over")
            }
        }
        assertEquals("1", paused.lastCompletedStepId)
        assertEquals(0, paused.lastCompletedStepIndex)
        assertEquals(listOf("1:STARTED", "1:SUCCEEDED"), journal)
        assertTrue(ui.taps.isEmpty())
    }

    @Test
    fun resumesAfterCompletedIndexWithoutReplayingEarlierGestures() = runBlocking {
        val ui = FakeUi().apply {
            nodes["login"] = node(clickable = true)
            tapCreates = "username" to node(editable = true, text = "")
        }
        val journal = mutableListOf<String>()
        executor(ui).execute(
            task(
                AutomationStep.Find("1", 1_000, "login"),
                AutomationStep.Tap("2", 1_000, "login", "username"),
                AutomationStep.Input("3", 1_000, "username", "operator", sensitive = true),
            ),
            startAfterIndex = 0,
        ) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(listOf("2:STARTED", "2:SUCCEEDED", "3:STARTED", "3:SUCCEEDED"), journal)
        assertEquals(listOf("login"), ui.taps)
        assertEquals("operator", ui.nodes.getValue("username").text)
    }

    @Test
    fun pauseDuringLaterWaitKeepsPreviousCompletedIndex() = runBlocking {
        val ui = FakeUi().apply {
            nodes["login"] = node(clickable = true)
            tapCreates = "username" to node(editable = true, text = "")
        }
        val control = ExecutionControl()
        val paused = assertFailsWith<TaskPausedException> {
            executor(ui).execute(
                task(
                    AutomationStep.Find("1", 1_000, "login"),
                    AutomationStep.Tap("2", 1_000, "login", "username"),
                    AutomationStep.Wait("3", 1_000, "missing", NodeCondition.EXISTS, 50),
                ),
                control,
            ) { step, state ->
                if (step.stepId == "3" && state == "STARTED") control.requestPause("operator taking over")
            }
        }
        assertEquals("2", paused.lastCompletedStepId)
        assertEquals(1, paused.lastCompletedStepIndex)
        assertEquals(listOf("login"), ui.taps)
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

    @Test
    fun acceptsFlutterDescriptionAfterHintNodeDisappears() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            dropLocatorAfterInput = true
            nodes["xianyu_description"] = node(editable = true, text = "")
        }
        executor(ui).execute(
            task(
                TargetLocatorRegistry.XIANYU_PACKAGE,
                AutomationStep.Input("fill-description", 1_000, "xianyu_description", "联调测试", false),
            ),
        ) { _, _ -> }
        assertTrue("xianyu_description" !in ui.nodes)
        // The node is gone. Only the string replaceText recorded for this
        // locator, equal in full, authorizes the step. Page text does not.
        assertEquals("联调测试", ui.committedFieldText("xianyu_description"))
    }

    @Test
    fun aLongerOldDraftThatContainsTheExpectedDescriptionIsRejected() = runBlocking {
        val expected = "联调测试"
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            applyInput = false
            // The field still shows the old draft. The expected sentence is a
            // substring of it. replaceText's strict proof is not this poll, and
            // "expected in a longer haystack" must not pass.
            nodes["xianyu_description"] = node(editable = true, text = "旧草稿前缀${expected}还没删掉的后半段")
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-description", 80, "xianyu_description", expected, false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
        assertTrue(ui.nodes.getValue("xianyu_description").text != expected)
    }

    @Test
    fun aDisappearedDescriptionNodeWithALongerRecordedDraftIsRejected() = runBlocking {
        val expected = "联调测试"
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            applyInput = false
            dropLocatorAfterInput = true
            recordLongerThanExpected = true
            nodes["xianyu_description"] = node(editable = true, text = "")
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-description", 80, "xianyu_description", expected, false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
        assertTrue(expected in (ui.committedFieldText("xianyu_description") ?: ""))
        assertTrue(ui.committedFieldText("xianyu_description") != expected)
    }

    @Test
    fun neighbouringSemanticTextDoesNotAuthorizeTheDescription() = runBlocking {
        val expected = "自用闲置，支持当面交易"
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            applyInput = false
            nodes["xianyu_description"] = node(editable = true, text = "描述一下宝贝的品牌型号")
            // A sibling semantic node carries the expected sentence. It is not
            // the description field, so the step must time out.
            nodes["xianyu_title"] = node(text = expected)
            pageHaystack = "想跟TA说点什么…$expected"
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-description", 80, "xianyu_description", expected, false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
        assertEquals("描述一下宝贝的品牌型号", ui.nodes.getValue("xianyu_description").text)
    }

    @Test
    fun failsWhenFlutterDescriptionNeverAppearsOnScreen() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            applyInput = false
            dropLocatorAfterInput = true
            nodes["xianyu_description"] = node(editable = true, text = "")
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-description", 100, "xianyu_description", "联调测试", false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
    }

    @Test
    fun priceElsewhereOnThePageDoesNotAuthorizeThePriceField() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            // The price node stays empty. A title elsewhere contains 199, and the
            // page haystack would match the substring. Neither authorizes price.
            nodes["xianyu_price"] = node(editable = true, text = "")
            nodes["xianyu_title"] = node(text = "199元包邮")
            pageHaystack = "别处的199"
            // The replace "succeeds" only as page text. The price node stays empty,
            // which is what an unauthorized page-wide match used to accept.
            applyInput = false
            recordCommittedOnly = true
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-price", 80, "xianyu_price", "199", false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
    }

    @Test
    fun accumulatedPriceTokenDoesNotPass() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            nodes["xianyu_price"] = node(editable = true, text = "¥10199")
            applyInput = false
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-price", 80, "xianyu_price", "199", false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
    }

    @Test
    fun descriptionOnAnotherNodeDoesNotAuthorizeThisField() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            nodes["xianyu_description"] = node(editable = true, text = "")
            nodes["xianyu_title"] = node(text = "自用闲置")
            applyInput = false
        }
        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(
                    TargetLocatorRegistry.XIANYU_PACKAGE,
                    AutomationStep.Input("fill-description", 80, "xianyu_description", "自用闲置", false),
                ),
            ) { _, _ -> }
        }
        assertEquals("STEP_TIMEOUT", failure.code)
    }

    private fun executor(ui: FakeUi, gate: CommitGate? = null) = LocalAutomationExecutor(
        ui = ui,
        now = { fixedNow },
        elapsedMs = { 1_000L },
        sleep = { delay(1) },
        commitGate = gate,
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
        var dropLocatorAfterInput = false
        var pageHaystack: String? = null
        var recordCommittedOnly = false
        /** Records a longer draft that merely contains the expected text. */
        var recordLongerThanExpected = false
        var allowedPackage = TargetLocatorRegistry.COMPANION_PACKAGE
        var tapCreates: Pair<String, LocalNodeState>? = null
        var followUpTapCreates: Pair<String, LocalNodeState>? = null
        var screenshot = ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))
        private var committedVisible: String? = null
        private val committedByLocator = mutableMapOf<String, String>()

        override fun ensureReady(targetPackage: String) {
            readyFailure?.let { throw it }
            check(targetPackage == allowedPackage)
        }

        override fun inspect(targetPackage: String, locatorRef: String) = nodes[locatorRef]

        override fun visibleTextContains(expected: String) =
            nodes.values.any { expected in (it.text ?: "") } ||
                committedVisible?.let { FlutterTextCommit.accepted(it, expected) } == true ||
                pageHaystack?.let { expected in it } == true

        override suspend fun tap(targetPackage: String, locatorRef: String) {
            taps += locatorRef
            val created = if (taps.size == 1) tapCreates else followUpTapCreates ?: tapCreates
            created?.let { nodes[it.first] = it.second }
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            val recorded = if (recordLongerThanExpected) "旧草稿前缀${value}还没删掉的后半段" else value
            if (applyInput || recordCommittedOnly || recordLongerThanExpected) {
                committedVisible = recorded
                committedByLocator[locatorRef] = recorded
            }
            if (dropLocatorAfterInput) {
                nodes.remove(locatorRef)
                return
            }
            if (applyInput) nodes[locatorRef] = nodes.getValue(locatorRef).copy(text = value)
        }

        override fun committedFieldText(locatorRef: String): String? = committedByLocator[locatorRef]

        override suspend fun screenshot(taskId: String, label: String) = screenshot

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
    @Test
    fun publishTapRoutesThroughGateAndStopsTheRun() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            nodes["xianyu_publish_button"] = node(clickable = true)
        }
        var gateCalls = 0
        val gate = CommitGate { _, _ -> gateCalls += 1 }
        val task = task(
            TargetLocatorRegistry.XIANYU_PACKAGE,
            AutomationStep.Find("1", 1_000, "xianyu_publish_button"),
            AutomationStep.Tap("2", 1_000, "xianyu_publish_button", null),
            AutomationStep.Log("3", 1_000, LogLevel.INFO, "AFTER_COMMIT_MUST_NOT_RUN"),
        )
        val journal = mutableListOf<String>()

        executor(ui, gate).execute(task) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(1, gateCalls)
        assertTrue(ui.taps.isEmpty())
        assertEquals(listOf("1:STARTED", "1:SUCCEEDED", "2:STARTED", "2:SUCCEEDED"), journal)
    }

    @Test
    fun nonPublishTapsBypassTheCommitGate() = runBlocking {
        val ui = FakeUi().apply {
            allowedPackage = TargetLocatorRegistry.XIANYU_PACKAGE
            nodes["xianyu_composer_done"] = node(clickable = true)
        }
        var gateCalls = 0
        executor(ui, CommitGate { _, _ -> gateCalls += 1 }).execute(
            task(TargetLocatorRegistry.XIANYU_PACKAGE, AutomationStep.Tap("1", 1_000, "xianyu_composer_done", null)),
        ) { _, _ -> }
        assertEquals(0, gateCalls)
        assertEquals(listOf("xianyu_composer_done"), ui.taps)
    }

}
