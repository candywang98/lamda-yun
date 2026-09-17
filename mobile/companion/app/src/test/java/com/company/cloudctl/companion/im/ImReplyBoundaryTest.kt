package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.NodeCondition
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * I10 reply boundary: only the authorized conversation may receive a reply,
 * everything unverifiable is refused with a stable code (fail-closed).
 */
class ImReplyBoundaryTest {
    private val fixedNow = Instant.ofEpochSecond(1_800_000_000)

    private fun replyTask(peer: String, body: String = "在的，可以拍"): AutomationTask {
        val steps = listOf(
            AutomationStep.Find("find-messages-tab", 1_000, "xianyu_messages_tab"),
            AutomationStep.TapText("open-conversation", 1_000, peer),
            AutomationStep.Wait(
                "wait-chat-input", 1_000, ImReplyTaskShape.CHAT_INPUT_LOCATOR, NodeCondition.EXISTS, 100,
            ),
            AutomationStep.Input("fill-reply", 1_000, ImReplyTaskShape.CHAT_INPUT_LOCATOR, body, false),
            AutomationStep.Tap("send-reply", 1_000, "xianyu_chat_send", null),
        )
        return AutomationTask(
            taskId = "task-reply-1",
            deviceId = "device-1",
            targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
            issuedAt = fixedNow.minusSeconds(60),
            expiresAt = fixedNow.plusSeconds(600),
            maxRunSeconds = 60,
            steps = steps,
        )
    }

    private fun evidence(
        open: String?,
        input: Boolean = true,
        inboundVisible: Boolean = true,
        harassment: Boolean = false,
    ) = ImReplyBoundary.ChatEvidence(
        openPeerName = open,
        chatInputVisible = input,
        triggeringInboundVisible = inboundVisible,
        inboundFlaggedHarassment = harassment,
    )

    private fun refuse(task: AutomationTask, evidence: ImReplyBoundary.ChatEvidence): ImReplyBoundary.Verdict.Refuse =
        assertIs<ImReplyBoundary.Verdict.Refuse>(ImReplyBoundary.check(task, evidence))

    @Test
    fun authorizedConversationWithVisibleTriggerAllowsTheSend() {
        val verdict = ImReplyBoundary.check(replyTask("小白"), evidence("小白"))
        assertEquals(ImReplyBoundary.Verdict.Allow, verdict)
    }

    @Test
    fun wrongConversationIsRefusedWithAClearCode() {
        // 错会话: the task targets 小白 but the open chat is 大白.
        val refuse = refuse(replyTask("小白"), evidence("大白"))
        assertEquals(ImReplyBoundary.Refusal.WRONG_CONVERSATION, refuse.refusal)
        assertEquals("REPLY_WRONG_CONVERSATION", refuse.code)
        assertTrue(refuse.detail.contains("大白"))
        assertTrue(refuse.detail.contains("小白"))
    }

    @Test
    fun unresolvedConversationIdentityFailsClosed() {
        val refuse = refuse(replyTask("小白"), evidence(null))
        assertEquals(ImReplyBoundary.Refusal.CONVERSATION_UNVERIFIED, refuse.refusal)
        // Identity resolved but the chat input of that conversation is gone.
        val noInput = refuse(replyTask("小白"), evidence("小白", input = false))
        assertEquals(ImReplyBoundary.Refusal.CONVERSATION_UNVERIFIED, noInput.refusal)
    }

    @Test
    fun missingTraceableTriggerRefusesUnsolicitedSends() {
        // 主动群发: no inbound of this peer on the page — nothing to answer.
        val refuse = refuse(replyTask("小白"), evidence("小白", inboundVisible = false))
        assertEquals(ImReplyBoundary.Refusal.NO_INBOUND_TRIGGER, refuse.refusal)
        assertEquals("REPLY_NO_INBOUND_TRIGGER", refuse.code)
    }

    @Test
    fun systemAndMarketingSessionsNeverReceiveReplies() {
        for (sender in ImFeedNoiseFilter.BUILTIN_SYSTEM_SOURCE_TITLES) {
            val refuse = refuse(replyTask(sender), evidence(sender))
            assertEquals(ImReplyBoundary.Refusal.SYSTEM_SESSION, refuse.refusal, "sender=$sender")
        }
        // Calibrated marketing source through the profile too.
        ImFeedNoiseFilter.calibrate(ImFeedNoiseFilter.NoiseProfile(systemSources = setOf("闲鱼小蜜")))
        try {
            val refuse = refuse(replyTask("闲鱼小蜜"), evidence("闲鱼小蜜"))
            assertEquals(ImReplyBoundary.Refusal.SYSTEM_SESSION, refuse.refusal)
        } finally {
            ImFeedNoiseFilter.resetCalibration()
        }
    }

    @Test
    fun flaggedHarassmentInboundRefusesTheReply() {
        val refuse = refuse(replyTask("小白"), evidence("小白", harassment = true))
        assertEquals(ImReplyBoundary.Refusal.HARASSMENT_SESSION, refuse.refusal)
        assertEquals("REPLY_HARASSMENT_SESSION", refuse.code)
    }

    @Test
    fun conversationFocusDriftRefusesTheSend() {
        // 焦点变化 at the conversation level: the pinned identity and the live
        // one both resolved but differ — refuse (field level stays
        // INPUT_TARGET_CHANGED in ChatInputCommit).
        assertTrue(ImReplyBoundary.conversationChanged("小白", "大白"))
        assertFalse(ImReplyBoundary.conversationChanged("小白", " 小白 "))
        // Null (unresolvable) never authorizes an override — that path is the
        // fail-closed CONVERSATION_UNVERIFIED refusal, not an allow.
        assertFalse(ImReplyBoundary.conversationChanged("小白", null))
        assertFalse(ImReplyBoundary.conversationChanged(null, "大白"))
        assertFalse(ImReplyBoundary.conversationChanged(null, null))
    }

    @Test
    fun nonReplyTasksPassThroughUntouched() {
        val notAReply = AutomationTask(
            taskId = "task-publish-1",
            deviceId = "device-1",
            targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
            issuedAt = fixedNow.minusSeconds(60),
            expiresAt = fixedNow.plusSeconds(600),
            maxRunSeconds = 60,
            steps = listOf(AutomationStep.Tap("publish", 1_000, "xianyu_publish_button", null)),
        )
        assertEquals(ImReplyBoundary.Verdict.Allow, ImReplyBoundary.check(notAReply, evidence(null)))
        assertNull(ImReplyBoundary.proofOf(notAReply))
    }

    @Test
    fun proofBindsReplyContentToTaskAndConversation() {
        val proof = ImReplyBoundary.proofOf(replyTask("小白", body = "在的，可以拍"))
        assertEquals("task-reply-1", proof!!.taskId)
        assertEquals("小白", proof.peerName)
        assertEquals("在的，可以拍", proof.replyText)
        // The audit line never leaks the reply body itself.
        assertTrue(proof.toString().contains("chars=6"))
        assertFalse(proof.toString().contains("在的"))
    }
}
