package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.im.ImReplyBoundary
import com.company.cloudctl.companion.ime.EditorSnapshot
import com.company.cloudctl.companion.ime.InputProof
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * im-live slice 2, gap 1: fresh tasks must normalize a target app that is
 * parked on an inner page (for example idlefish 「我发布的」) back to a root
 * page before the first step runs, using bounded BACK presses and a forced
 * relaunch as the last resort.
 */
class NavigationResetExecutorTest {
    private val fixedNow = Instant.parse("2026-09-14T08:00:00Z")

    @Test
    fun freshRunWalksBackToRootBeforeSteps() = runBlocking {
        val ui = navFakeUi(startAtRoot = false, rootAfterBacks = 2)
        val journal = mutableListOf<String>()

        executor(ui).execute(task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "AFTER_RESET"))) { step, state ->
            journal += "${step.stepId}:$state"
        }

        assertEquals(2, ui.backs)
        assertEquals(0, ui.restarts)
        assertEquals(listOf("1:STARTED", "1:SUCCEEDED"), journal)
        assertTrue(ui.logs.any { it.second == "NAV_RESET_BACK" })
        assertTrue(ui.logs.none { it.second == "NAV_RESET_RELAUNCH" })
    }

    @Test
    fun backExhaustedFallsBackToForcedRelaunch() = runBlocking {
        val ui = navFakeUi(startAtRoot = false, rootAfterBacks = Int.MAX_VALUE, rootAfterRestart = true)

        executor(ui).execute(task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "AFTER_RESET"))) { _, _ -> }

        assertEquals(5, ui.backs)
        assertEquals(1, ui.restarts)
        assertTrue(ui.logs.any { it.second == "NAV_RESET_RELAUNCH" })
    }

    @Test
    fun resetFailsClosedWhenNeitherBacksNorRelaunchReachRoot() = runBlocking {
        val ui = navFakeUi(startAtRoot = false, rootAfterBacks = Int.MAX_VALUE, rootAfterRestart = false)
        val journal = mutableListOf<String>()

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "NEVER_RUN"))) { step, state ->
                journal += "${step.stepId}:$state"
            }
        }

        assertEquals("NAV_RESET_FAILED", failure.code)
        assertEquals(5, ui.backs)
        assertEquals(1, ui.restarts)
        assertTrue(journal.isEmpty())
    }

    @Test
    fun backgroundTargetSkipsBacksAndRelaunchesDirectly() = runBlocking {
        val ui = navFakeUi(
            startAtRoot = false,
            rootAfterBacks = Int.MAX_VALUE,
            foreground = false,
            rootAfterRestart = true,
        )

        executor(ui).execute(task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "AFTER_RESET"))) { _, _ -> }

        assertEquals(0, ui.backs)
        assertEquals(1, ui.restarts)
    }

    @Test
    fun alreadyAtRootNeverNavigates() = runBlocking {
        val ui = navFakeUi(startAtRoot = true)

        executor(ui).execute(task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "PLAIN"))) { _, _ -> }

        assertEquals(0, ui.backs)
        assertEquals(0, ui.restarts)
        assertTrue(ui.logs.none { it.second.startsWith("NAV_RESET") })
    }

    @Test
    fun resumedRunKeepsItsVerifiedPageState() = runBlocking {
        val ui = navFakeUi(startAtRoot = false, rootAfterBacks = Int.MAX_VALUE, rootAfterRestart = false)

        executor(ui).execute(
            task(
                AutomationStep.Log("1", 1_000, LogLevel.INFO, "DONE_BEFORE_PAUSE"),
                AutomationStep.Log("2", 1_000, LogLevel.INFO, "RESUMED"),
            ),
            startAfterIndex = 0,
        ) { _, _ -> }

        assertEquals(0, ui.backs)
        assertEquals(0, ui.restarts)
    }

    @Test
    fun cancellationDuringResetPropagatesBeforeAnyStep() = runBlocking {
        val ui = navFakeUi(startAtRoot = false, rootAfterBacks = Int.MAX_VALUE, rootAfterRestart = false)
        val control = ExecutionControl().apply { requestCancel("operator taking over") }
        val journal = mutableListOf<String>()

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(
                task(AutomationStep.Log("1", 1_000, LogLevel.INFO, "NEVER_RUN")),
                control,
            ) { step, state -> journal += "${step.stepId}:$state" }
        }

        assertEquals("CANCELLED", failure.code)
        assertTrue(journal.isEmpty())
    }

    @Test
    fun sixStepReplyTaskCompletesAfterNavigationReset() = runBlocking {
        val peer = "lucas"
        val ui = navFakeUi(startAtRoot = false, rootAfterBacks = 2, peerName = peer).apply {
            nodes["xianyu_messages_tab"] = node(clickable = true)
            nodes["xianyu_chat_send"] = node(clickable = true)
        }
        val journal = mutableListOf<String>()
        val task = task(
            TargetLocatorRegistry.XIANYU_PACKAGE,
            AutomationStep.Find("find-messages-tab", 1_000, "xianyu_messages_tab"),
            AutomationStep.Tap("open-messages-tab", 1_000, "xianyu_messages_tab", null),
            AutomationStep.TapText("open-conversation", 1_000, peer),
            AutomationStep.Wait("wait-chat-input", 1_000, "xianyu_chat_input", NodeCondition.EXISTS, 100),
            AutomationStep.Input("fill-reply", 1_000, "xianyu_chat_input", "你好，在的", false),
            AutomationStep.Tap("send-reply", 1_000, "xianyu_chat_send", null),
        )

        executor(ui).execute(task) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(2, ui.backs)
        assertEquals(0, ui.restarts)
        assertEquals(listOf(peer), ui.tapTexts)
        assertEquals(listOf("xianyu_messages_tab", "xianyu_chat_send"), ui.taps)
        assertTrue(ui.visibleTextContains("你好，在的"))
        assertEquals(
            listOf(
                "find-messages-tab", "open-messages-tab", "open-conversation", "wait-chat-input",
                "fill-reply", "send-reply",
            ),
            journal.filter { it.endsWith("STARTED") }.map { it.substringBefore(':') },
        )
        assertEquals("send-reply:SUCCEEDED", journal.last())
    }

    private fun executor(ui: NavFakeUi) = LocalAutomationExecutor(
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

    private fun navFakeUi(
        startAtRoot: Boolean,
        rootAfterBacks: Int = Int.MAX_VALUE,
        rootAfterRestart: Boolean = true,
        foreground: Boolean = true,
        peerName: String = "peer",
    ) = NavFakeUi(startAtRoot, rootAfterBacks, rootAfterRestart, foreground, peerName)

    private class NavFakeUi(
        private val startAtRoot: Boolean,
        private val rootAfterBacks: Int,
        private val rootAfterRestart: Boolean,
        private var foreground: Boolean,
        private val peerName: String,
    ) : LocalAutomationUi {
        val nodes = mutableMapOf<String, LocalNodeState>()
        val taps = mutableListOf<String>()
        val tapTexts = mutableListOf<String>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        var backs = 0
        var restarts = 0
        private var committedVisible: String? = null
        private var held: InputProof? = null
        private var bindTask: String? = null
        private var bindPeer: String? = null
        private var bindExpires: Long? = null

        override fun ensureReady(targetPackage: String) {
            if (!foreground) throw ExecutorFailure("WRONG_ACTIVE_PACKAGE", "target not foreground")
        }

        override fun inspect(targetPackage: String, locatorRef: String) = nodes[locatorRef]

        override fun visibleTextContains(expected: String): Boolean =
            nodes.values.any { expected in (it.text ?: "") } || committedVisible?.let { expected in it } == true

        override suspend fun tapText(targetPackage: String, value: String) {
            tapTexts += value
            if (value == peerName) {
                nodes["xianyu_chat_input"] = LocalNodeState(
                    enabled = true, visible = true, clickable = false, editable = true, text = "",
                )
            }
        }

        // I10 reply-boundary feed: before the conversation opens nothing is
        // readable; after tapText(peer) the fake chat page shows exactly the
        // authorized peer with its input and a traceable inbound bubble.
        override fun imChatEvidence(
            targetPackage: String,
            expectedPeer: String?,
        ): com.company.cloudctl.companion.im.ImReplyBoundary.ChatEvidence? {
            val chatOpen = nodes["xianyu_chat_input"]?.visible == true
            return if (!chatOpen) {
                com.company.cloudctl.companion.im.ImReplyBoundary.ChatEvidence(
                    openPeerName = null,
                    chatInputVisible = false,
                    triggeringInboundVisible = false,
                )
            } else {
                com.company.cloudctl.companion.im.ImReplyBoundary.ChatEvidence(
                    openPeerName = peerName,
                    chatInputVisible = true,
                    triggeringInboundVisible = true,
                )
            }
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) {
            taps += locatorRef
        }

        override fun beginChatInput(taskId: String, peerName: String?, ttlMs: Long, nowElapsedMs: Long) {
            bindTask = taskId
            bindPeer = peerName
            bindExpires = nowElapsedMs + ttlMs
        }

        override fun clearChatSendProof() {
            held = null
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            committedVisible = value
            nodes[locatorRef] = nodes.getValue(locatorRef).copy(text = value)
            if (locatorRef == "xianyu_chat_input") {
                held = InputProof(
                    target = targetPackage,
                    field = "chat-field",
                    generation = 1,
                    expected = value,
                    snapshot = EditorSnapshot(1, "chat-field", value, value.length, value.length, false, true, 0, false),
                    targetPackage = targetPackage,
                    locatorRef = locatorRef,
                    nodeKey = "1:1",
                    taskId = bindTask,
                    peerName = bindPeer,
                    expiresAtElapsedMs = bindExpires,
                )
            }
        }

        override fun currentChatSendProof(): InputProof? = held

        override suspend fun verifyChatSendProof(
            targetPackage: String,
            locatorRef: String,
            proof: InputProof,
            evidence: ImReplyBoundary.ChatEvidence?,
        ): Boolean = held === proof && proof.expected == committedVisible &&
            proof.targetPackage == targetPackage && proof.locatorRef == locatorRef &&
            evidence?.chatInputVisible == true

        override fun consumeChatSendProof() {
            held = null
        }

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }

        override fun isTargetForeground(targetPackage: String): Boolean = foreground

        override fun atRootPage(targetPackage: String): Boolean = when {
            startAtRoot -> true
            rootAfterBacks != Int.MAX_VALUE && backs >= rootAfterBacks -> true
            restarts > 0 && rootAfterRestart -> true
            else -> false
        }

        override suspend fun goBack() {
            backs += 1
        }

        override suspend fun restartTargetApp(targetPackage: String) {
            restarts += 1
            // A forced relaunch brings the target back to the foreground.
            foreground = true
        }
    }
}
