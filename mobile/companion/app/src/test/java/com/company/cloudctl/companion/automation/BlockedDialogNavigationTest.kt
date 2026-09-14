package com.company.cloudctl.companion.automation

import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BlockedDialogNavigationTest {
    private val now = Instant.parse("2026-09-14T08:00:00Z")
    // Independent fixture for the controller-reported XHS 8.50.1 recovery dialog.
    private val title = "\u7ee7\u7eed\u7f16\u8f91\u56fe\u6587\u7b14\u8bb0\u5417\uff1f"
    private val save = "\u5b58\u8349\u7a3f"
    private val edit = "\u53bb\u7f16\u8f91"
    private val discard = "\u653e\u5f03"
    private val pkg = TargetLocatorRegistry.XHS_PACKAGE

    private fun dialog() = listOf(
        BlockedDialogRegistry.Node(title),
        BlockedDialogRegistry.Node(save, clickable = true),
        BlockedDialogRegistry.Node(edit, clickable = true),
    )

    @Test
    fun coldStartDialogSavesDraftThenExecutesTask() = runBlocking {
        val ui = FakeUi().apply { dialogs += dialog() }
        run(ui)
        assertEquals(listOf(save), ui.taps)
        assertEquals(listOf(800L), ui.sleeps)
        assertEquals(listOf("NAV_DIALOG_DISMISSED label=$save", "AFTER_RESET"), ui.events)
        assertEquals(listOf("STARTED", "SUCCEEDED"), ui.journal)
        assertEquals(0, ui.backs)
        assertEquals(0, ui.restarts)
    }

    @Test
    fun consecutiveDialogsAreSettledAndRecheckedSeparately() = runBlocking {
        val ui = FakeUi().apply { dialogs += dialog(); dialogs += dialog() }
        run(ui)
        assertEquals(listOf(save, save), ui.taps)
        assertEquals(listOf(800L, 800L), ui.sleeps)
        assertEquals(2, ui.events.count { it == "NAV_DIALOG_DISMISSED label=$save" })
        assertEquals(0, ui.backs)
    }

    @Test
    fun unknownDialogIsNeverTappedAndResetFailsClosed() = runBlocking {
        val ui = FakeUi().apply {
            dialogs += dialog().map { if (it.text == title) it.copy(text = "Unknown dialog") else it }
        }
        val failure = assertFailsWith<ExecutorFailure> { run(ui) }
        assertEquals("NAV_RESET_FAILED", failure.code)
        assertTrue(ui.taps.isEmpty())
        assertTrue(ui.journal.isEmpty())
        assertEquals(5, ui.backs)
        assertEquals(1, ui.restarts)
        assertEquals(List(12) { 500L }, ui.sleeps)
    }

    @Test
    fun relaunchDialogIsRecoveredBeforeTaskSteps() = runBlocking {
        val ui = FakeUi().apply {
            pageReady = false
            onRestart = { pageReady = true; dialogs += dialog() }
        }
        run(ui)
        assertEquals(5, ui.backs)
        assertEquals(1, ui.restarts)
        assertEquals(listOf(save), ui.taps)
        assertTrue(ui.events.indexOf("NAV_RESET_RELAUNCH") < ui.events.indexOf("NAV_DIALOG_DISMISSED label=$save"))
    }

    @Test
    fun dialogAppearingInLaterRelaunchPollIsRecovered() = runBlocking {
        val ui = FakeUi().apply {
            pageReady = false
            onSleep = { ms -> if (restarts == 1 && ms == 500L) { pageReady = true; dialogs += dialog() } }
        }
        run(ui)
        assertEquals(listOf(500L, 800L), ui.sleeps)
        assertEquals(listOf(save), ui.taps)
    }

    @Test
    fun dialogAppearingAfterBackIsHandledBeforeNextBack() = runBlocking {
        val ui = FakeUi().apply {
            pageReady = false
            onBack = { pageReady = true; dialogs += dialog() }
        }
        run(ui)
        assertEquals(1, ui.backs)
        assertEquals(0, ui.restarts)
        assertEquals(listOf(save), ui.taps)
    }

    @Test
    fun editAndDiscardAreNeverSelectedEvenWhenPresent() = runBlocking {
        val ui = FakeUi().apply { dialogs += dialog() + BlockedDialogRegistry.Node(discard, clickable = true) }
        run(ui)
        assertEquals(listOf(save), ui.taps)
        assertFalse(edit in ui.taps)
        assertFalse(discard in ui.taps)
    }

    @Test
    fun missingSafeButtonNeverFallsBackToEditOrDiscard() = runBlocking {
        val ui = FakeUi().apply {
            dialogs += dialog().filterNot { it.text == save } + BlockedDialogRegistry.Node(discard, clickable = true)
        }
        assertEquals("NAV_RESET_FAILED", assertFailsWith<ExecutorFailure> { run(ui) }.code)
        assertTrue(ui.taps.isEmpty())
    }

    @Test
    fun dismissalBudgetIsThreeAcrossBackAndRelaunchPhases() = runBlocking {
        val ui = FakeUi().apply {
            pageReady = false
            dialogs += dialog()
            onBack = { if (backs == 1) dialogs += dialog() }
            onRestart = { pageReady = true; dialogs += dialog(); dialogs += dialog() }
        }
        assertEquals("NAV_RESET_FAILED", assertFailsWith<ExecutorFailure> { run(ui) }.code)
        assertEquals(List(3) { save }, ui.taps)
        assertEquals(3, ui.sleeps.count { it == 800L })
        assertEquals(1, ui.dialogs.size)
        assertTrue(ui.journal.isEmpty())
    }

    @Test
    fun persistentDialogCannotCauseUnboundedTaps() = runBlocking {
        val ui = FakeUi().apply { dialogs += dialog(); removeOnTap = false }
        assertEquals("NAV_RESET_FAILED", assertFailsWith<ExecutorFailure> { run(ui) }.code)
        assertEquals(3, ui.taps.size)
    }

    @Test
    fun backgroundTargetNeverDismissesOrBacks() = runBlocking {
        val ui = FakeUi().apply {
            foreground = false
            dialogs += dialog()
            onRestart = { foreground = true }
        }
        run(ui)
        assertEquals(0, ui.backs)
        assertEquals(1, ui.restarts)
        assertEquals(listOf(save), ui.taps)
    }

    @Test
    fun cancellationDuringDialogSettlePreventsFurtherGesturesAndSteps() = runBlocking {
        val control = ExecutionControl()
        val ui = FakeUi().apply {
            dialogs += dialog(); dialogs += dialog()
            onSleep = { control.requestCancel("stop") }
        }
        assertEquals("CANCELLED", assertFailsWith<ExecutorFailure> { run(ui, control) }.code)
        assertEquals(listOf(save), ui.taps)
        assertEquals(0, ui.backs)
        assertEquals(0, ui.restarts)
        assertTrue(ui.journal.isEmpty())
    }

    @Test
    fun deadlineDuringDialogSettleStopsReset() = runBlocking {
        val ui = FakeUi().apply {
            dialogs += dialog()
            onSleep = { clock = 60_000L }
        }
        assertEquals("TASK_TIMEOUT", assertFailsWith<ExecutorFailure> { run(ui) }.code)
        assertEquals(0, ui.backs)
        assertTrue(ui.journal.isEmpty())
    }

    @Test
    fun failedGestureDoesNotLogDismissedOrRetry() = runBlocking {
        val ui = FakeUi().apply { dialogs += dialog(); failGesture = true }
        assertEquals("NAV_RESET_FAILED", assertFailsWith<ExecutorFailure> { run(ui) }.code)
        assertEquals(1, ui.taps.size)
        assertTrue(ui.events.isEmpty())
        assertTrue(ui.journal.isEmpty())
    }

    @Test
    fun unverifiedPlatformsHaveNoRecoveryActions() {
        for (target in listOf(TargetLocatorRegistry.DOUYIN_PACKAGE, TargetLocatorRegistry.XIANYU_PACKAGE, "unknown")) {
            assertTrue(BlockedDialogRegistry.rules(target).isEmpty())
            assertNull(BlockedDialogRegistry.match(target, dialog()))
        }
    }

    @Test
    fun ambiguousTitleOrButtonsFailClosed() {
        for (node in dialog()) assertNull(BlockedDialogRegistry.match(pkg, dialog() + node))
    }

    @Test
    fun invisibleAnchorsAndDisabledOrUnclickableSafeButtonsFailClosed() {
        for (index in dialog().indices) {
            val nodes = dialog().toMutableList()
            nodes[index] = nodes[index].copy(visible = false)
            assertNull(BlockedDialogRegistry.match(pkg, nodes))
        }
        assertNull(BlockedDialogRegistry.match(pkg, dialog().map { if (it.text == save) it.copy(enabled = false) else it }))
        assertNull(BlockedDialogRegistry.match(pkg, dialog().map { if (it.text == save) it.copy(clickable = false) else it }))
    }

    @Test
    fun contentDescriptionsAreExactNotSubstringMatches() {
        val descriptions = dialog().map { it.copy(text = null, description = it.text) }
        assertEquals(save, BlockedDialogRegistry.match(pkg, descriptions)?.label)
        assertNull(BlockedDialogRegistry.match(pkg, dialog().map { it.copy(text = "prefix ${it.text}") }))
    }

    private suspend fun run(ui: FakeUi, control: ExecutionControl? = null) {
        LocalAutomationExecutor(ui, now = { now }, elapsedMs = { ui.clock }, sleep = { ms ->
            ui.sleeps += ms
            ui.clock += ms
            ui.onSleep(ms)
        }).execute(AutomationTask(
            taskId = "dialog-task", deviceId = "device", targetPackage = pkg,
            issuedAt = now.minusSeconds(60), expiresAt = now.plusSeconds(600), maxRunSeconds = 60,
            steps = listOf(AutomationStep.Log("after", 1_000, LogLevel.INFO, "AFTER_RESET")),
        ), control) { _, state -> ui.journal += state }
    }

    private inner class FakeUi : LocalAutomationUi {
        val dialogs = mutableListOf<List<BlockedDialogRegistry.Node>>()
        val taps = mutableListOf<String>()
        val events = mutableListOf<String>()
        val sleeps = mutableListOf<Long>()
        val journal = mutableListOf<String>()
        var clock = 0L
        var backs = 0
        var restarts = 0
        var foreground = true
        var pageReady = true
        var removeOnTap = true
        var failGesture = false
        var onBack: () -> Unit = {}
        var onRestart: () -> Unit = {}
        var onSleep: (Long) -> Unit = {}

        override fun atRootPage(targetPackage: String) = foreground && pageReady && dialogs.isEmpty()
        override fun isTargetForeground(targetPackage: String) = foreground
        override suspend fun dismissBlockedDialog(targetPackage: String): String? {
            check(foreground)
            val nodes = dialogs.firstOrNull() ?: return null
            val match = BlockedDialogRegistry.match(targetPackage, nodes) ?: return null
            taps += nodes[match.nodeIndex].text!!
            if (failGesture) throw ExecutorFailure("NAV_RESET_FAILED", "gesture failed")
            if (removeOnTap) dialogs.removeAt(0)
            return match.label
        }
        override suspend fun goBack() { backs++; onBack() }
        override suspend fun restartTargetApp(targetPackage: String) { restarts++; onRestart() }
        override fun log(level: LogLevel, messageCode: String) { events += messageCode }
        override fun ensureReady(targetPackage: String) { check(foreground) }
        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = error("unexpected inspect")
        override suspend fun tap(targetPackage: String, locatorRef: String) = error("unexpected tap")
        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) = error("unexpected input")
        override suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence = error("unexpected screenshot")
    }
}
