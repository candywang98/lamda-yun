package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.im.ImReplyBoundary
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * I10 wiring (fleet-first-20260916.1) — ImReplyBoundary pulled into the reply
 * task's execution path: the conversation-open guard fires BEFORE the
 * conversation-opening tapText (a provably wrong already-open chat refuses
 * with no open action at all), and the fail-closed send seam fires before
 * the reply text is typed and again before the send tap. Non-reply tasks
 * never touch the boundary.
 */
class ImReplyBoundaryWiringTest {
    private val fixedNow = Instant.parse("2026-09-16T08:00:00Z")
    private val peer = "lucas"

    @Test
    fun wrongConversationEvidenceFailsTaskBeforeAnyOpenAction() = runBlocking {
        // The screen already shows ANOTHER conversation open (stale chat from
        // an earlier task): the boundary refuses before the reply task opens
        // anything — no tapText, no typing, no send.
        val ui = ReplyFakeUi().apply {
            preOpenEvidence = evidence(openPeerName = "别的买家", chatInput = true, inbound = true)
        }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(replyTask()) { _, _ -> }
        }

        assertEquals(ImReplyBoundary.Refusal.WRONG_CONVERSATION.code, failure.code)
        assertTrue(ui.tapTexts.isEmpty())
        assertTrue(ui.replaceTexts.isEmpty())
        assertTrue(ui.taps.isEmpty())
        assertTrue(ui.logs.any { it == LogLevel.ERROR to ImReplyBoundary.Refusal.WRONG_CONVERSATION.code })
    }

    @Test
    fun authorizedEvidenceLetsTheReplyTaskComplete() = runBlocking {
        val ui = ReplyFakeUi().apply {
            // Fresh start: nothing open yet, then the opened chat provably
            // shows the authorized peer, its input and a traceable inbound.
            preOpenEvidence = evidence(openPeerName = null, chatInput = false, inbound = false)
            postOpenEvidence = evidence(openPeerName = peer, chatInput = true, inbound = true)
        }
        val journal = mutableListOf<String>()

        executor(ui).execute(replyTask()) { step, state -> journal += "${step.stepId}:$state" }

        assertEquals(listOf(peer), ui.tapTexts)
        assertEquals(listOf("你好，在的"), ui.replaceTexts.map { it.second })
        assertTrue(ui.taps.contains("xianyu_chat_send"))
        assertEquals("send-reply:SUCCEEDED", journal.last())
    }

    @Test
    fun conversationDriftBeforeSendRefusesWithTargetChanged() = runBlocking {
        val ui = ReplyFakeUi().apply {
            preOpenEvidence = evidence(openPeerName = null, chatInput = false, inbound = false)
            // The conversation identity drifted between the open and the send
            // (notification switch, user tap): conversationChanged fires.
            postOpenEvidence = evidence(openPeerName = "另一个会话", chatInput = true, inbound = true)
        }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(replyTask()) { _, _ -> }
        }

        assertEquals(ImReplyBoundary.Refusal.TARGET_CHANGED.code, failure.code)
        // The reply was never typed into the drifted conversation.
        assertTrue(ui.replaceTexts.isEmpty())
        assertTrue(ui.taps.isEmpty())
    }

    @Test
    fun missingTraceableInboundRefusesAtTheSendSeam() = runBlocking {
        val ui = ReplyFakeUi().apply {
            preOpenEvidence = evidence(openPeerName = null, chatInput = false, inbound = false)
            // Right conversation, input visible, but no inbound bubble on the
            // page: an unsolicited send is refused (NO_INBOUND_TRIGGER).
            postOpenEvidence = evidence(openPeerName = peer, chatInput = true, inbound = false)
        }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(replyTask()) { _, _ -> }
        }

        assertEquals(ImReplyBoundary.Refusal.NO_INBOUND_TRIGGER.code, failure.code)
        assertTrue(ui.replaceTexts.isEmpty())
    }

    @Test
    fun unavailableEvidenceAtTheSendSeamFailsClosed() = runBlocking {
        val ui = ReplyFakeUi().apply {
            preOpenEvidence = evidence(openPeerName = null, chatInput = false, inbound = false)
            postOpenEvidence = null // nothing readable about the open chat
        }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(replyTask()) { _, _ -> }
        }

        assertEquals(ImReplyBoundary.Refusal.CONVERSATION_UNVERIFIED.code, failure.code)
        assertTrue(ui.replaceTexts.isEmpty())
    }

    @Test
    fun unresolvableOpenChatIdentityRefusesTheOpenGuardToo() = runBlocking {
        val ui = ReplyFakeUi().apply {
            // A chat input IS visible but the conversation identity cannot be
            // resolved: refusing to pile navigation on an unidentifiable chat.
            preOpenEvidence = evidence(openPeerName = null, chatInput = true, inbound = true)
        }

        val failure = assertFailsWith<ExecutorFailure> {
            executor(ui).execute(replyTask()) { _, _ -> }
        }

        assertEquals(ImReplyBoundary.Refusal.CONVERSATION_UNVERIFIED.code, failure.code)
        assertTrue(ui.tapTexts.isEmpty())
    }

    @Test
    fun nonReplyTasksNeverTouchTheBoundary() = runBlocking {
        // Two tapText steps: not the reply shape — the default null evidence
        // never fires a guard, the chat-input input runs untouched.
        val ui = ReplyFakeUi().apply {
            nodes["xianyu_chat_input"] = LocalNodeState(
                enabled = true, visible = true, clickable = false, editable = true, text = "",
            )
        }
        val task = task(
            TargetLocatorRegistry.XIANYU_PACKAGE,
            AutomationStep.TapText("open-a", 1_000, "会话甲"),
            AutomationStep.TapText("open-b", 1_000, "会话乙"),
            AutomationStep.Input("fill", 1_000, "xianyu_chat_input", "内容", false),
        )

        executor(ui).execute(task) { _, _ -> }

        assertEquals(listOf("会话甲", "会话乙"), ui.tapTexts)
        assertEquals(listOf("内容"), ui.replaceTexts.map { it.second })
        assertTrue(ui.logs.none { it.second.startsWith("REPLY_") })
    }

    // ------------------------------------------------------------------
    // helpers
    // ------------------------------------------------------------------

    private fun evidence(openPeerName: String?, chatInput: Boolean, inbound: Boolean) =
        ImReplyBoundary.ChatEvidence(
            openPeerName = openPeerName,
            chatInputVisible = chatInput,
            triggeringInboundVisible = inbound,
        )

    private fun executor(ui: ReplyFakeUi): LocalAutomationExecutor {
        // Constant clock (NavigationResetExecutorTest pattern): tapTextWithScroll's
        // deadline guards stay open, so the boundary refusals under test are the
        // only ways these tasks can end.
        return LocalAutomationExecutor(
            ui = ui,
            now = { fixedNow },
            elapsedMs = { 1_000L },
            sleep = { delay(1) },
        )
    }

    private fun replyTask(): AutomationTask = task(
        TargetLocatorRegistry.XIANYU_PACKAGE,
        AutomationStep.TapText("open-conversation", 1_000, peer),
        AutomationStep.Wait("wait-chat-input", 1_000, "xianyu_chat_input", NodeCondition.EXISTS, 100),
        AutomationStep.Input("fill-reply", 1_000, "xianyu_chat_input", "你好，在的", false),
        AutomationStep.Tap("send-reply", 1_000, "xianyu_chat_send", null),
    )

    private fun task(targetPackage: String, vararg steps: AutomationStep) = AutomationTask(
        taskId = "task-1",
        deviceId = "device-1",
        targetPackage = targetPackage,
        issuedAt = fixedNow.minusSeconds(60),
        expiresAt = fixedNow.plusSeconds(600),
        maxRunSeconds = 60,
        steps = steps.toList(),
    )

    /**
     * 阶段化假 UI：open 前（首个 tapText 之前）供 [preOpenEvidence]，open 后供
     * [postOpenEvidence]；tapText(peer) 打开聊天输入节点，模拟会话页就绪。
     */
    private class ReplyFakeUi : LocalAutomationUi {
        var preOpenEvidence: ImReplyBoundary.ChatEvidence? = null
        var postOpenEvidence: ImReplyBoundary.ChatEvidence? = null
        val nodes = mutableMapOf<String, LocalNodeState>()
        val tapTexts = mutableListOf<String>()
        val replaceTexts = mutableListOf<Pair<String, String>>()
        val taps = mutableListOf<String>()
        val logs = mutableListOf<Pair<LogLevel, String>>()
        private var opened = false
        private var committed: String? = null

        override fun ensureReady(targetPackage: String) = Unit

        override fun inspect(targetPackage: String, locatorRef: String): LocalNodeState? = nodes[locatorRef]

        override fun visibleTextContains(expected: String): Boolean =
            nodes.values.any { expected in (it.text ?: "") } || committed?.let { expected in it } == true

        override fun imChatEvidence(
            targetPackage: String,
            expectedPeer: String?,
        ): ImReplyBoundary.ChatEvidence? = if (opened) postOpenEvidence else preOpenEvidence

        override suspend fun tapText(targetPackage: String, value: String) {
            tapTexts += value
            opened = true
            nodes["xianyu_chat_input"]?.let { return }
            nodes["xianyu_chat_input"] = LocalNodeState(
                enabled = true, visible = true, clickable = false, editable = true, text = "",
            )
            nodes["xianyu_chat_send"] = LocalNodeState(
                enabled = true, visible = true, clickable = true, editable = false, text = null,
            )
        }

        override suspend fun tap(targetPackage: String, locatorRef: String) {
            taps += locatorRef
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            replaceTexts += locatorRef to value
            committed = value
            nodes[locatorRef] = nodes.getValue(locatorRef).copy(text = value)
        }

        override suspend fun screenshot(taskId: String, label: String) =
            ScreenshotEvidence("/private/proof.png", 32, "a".repeat(64))

        override fun log(level: LogLevel, messageCode: String) {
            logs += level to messageCode
        }
    }
}
