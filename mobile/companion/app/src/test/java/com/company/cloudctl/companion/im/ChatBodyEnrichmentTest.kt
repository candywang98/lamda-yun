package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.NodeCondition
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * im-live slice 2, gap 2: push notifications carry only a placeholder body, so
 * the open conversation page must be read for the newest inbound bubble and the
 * corrected body queued through the ordinary ImMonitor path without ever
 * blocking the task.
 */
class ChatBodyEnrichmentTest {
    private val fixedNow = Instant.parse("2026-09-14T08:00:00Z")

    private fun bubble(text: String, centerX: Float, width: Int = 300, height: Int = 80) =
        ChatBubble(text = text, centerX = centerX, width = width, height = height)

    @Test
    fun latestInboundPrefersTheLastLeftAlignedPlausibleBubble() {
        val bubbles = listOf(
            bubble("早上好", centerX = 120f),
            bubble("在的，您说", centerX = 820f),
            bubble("这个还有货吗", centerX = 120f),
            bubble("超高气泡不是消息", centerX = 120f, height = 500),
            bubble("太窄不算", centerX = 120f, width = 20),
            bubble("超长文本不符合气泡阈值".repeat(60), centerX = 120f),
        )

        assertEquals("这个还有货吗", ChatPageReading.latestInbound(bubbles))
        assertNull(ChatPageReading.latestInbound(emptyList()))
    }

    @Test
    fun freshInboundDropsAnsweredTexts() {
        val bubbles = listOf(
            bubble("可以便宜点吗", centerX = 120f),
            bubble("可以便宜点吗", centerX = 820f), // our own reply repeats the question
            bubble("明天发货吗", centerX = 120f),
        )

        assertEquals(listOf("明天发货吗"), ChatPageReading.freshInbound(bubbles))
    }

    @Test
    fun peerNameOfRecognizesOnlyTheXianyuReplyTaskShape() {
        assertEquals("小白", ImReplyTaskShape.peerNameOf(replyTask(peer = "小白", body = "好的")))

        // Two TapText steps are not the reply shape.
        assertNull(
            ImReplyTaskShape.peerNameOf(
                replyTask(peer = "小白", body = "好的").copy(
                    steps = replyTask(peer = "小白", body = "好的").steps +
                        AutomationStep.TapText("second-tap", 1_000, "另一个会话"),
                ),
            ),
        )
        // No chat-input step at all is not the reply shape.
        assertNull(
            ImReplyTaskShape.peerNameOf(
                replyTask(peer = "小白", body = "好的").copy(
                    steps = replyTask(peer = "小白", body = "好的").steps.filterNot {
                        (it is AutomationStep.Input && it.locatorRef == ImReplyTaskShape.CHAT_INPUT_LOCATOR) ||
                            (it is AutomationStep.Wait && it.locatorRef == ImReplyTaskShape.CHAT_INPUT_LOCATOR)
                    },
                ),
            ),
        )
        // A non-xianyu target is never the reply shape.
        assertNull(
            ImReplyTaskShape.peerNameOf(
                replyTask(peer = "小白", body = "好的").copy(
                    targetPackage = TargetLocatorRegistry.COMPANION_PACKAGE,
                ),
            ),
        )
    }

    @Test
    fun replyTextOfReturnsTheTypedChatInput() {
        assertEquals("好的，明天发货", ImReplyTaskShape.replyTextOf(replyTask(peer = "小白", body = "好的，明天发货")))
        assertNull(ImReplyTaskShape.replyTextOf(replyTask(peer = "小白", body = null)))
    }

    @Test
    fun enrichQueuesTheCorrectedBodyAndDedupesRepeats() {
        val queued = mutableListOf<ImEvent>()
        val enricher = ImBodyEnricher(
            deviceId = { "device-1" },
            clock = { fixedNow },
            accept = { _, event ->
                queued += event
                true
            },
        )
        val bubbles = listOf(
            bubble("发来一条新消息", centerX = 120f), // stale placeholder somewhere on the page
            bubble("这个还有货吗", centerX = 120f),
        )

        assertTrue(enricher.enrich("小白", bubbles))
        val event = queued.single()
        assertEquals(ImMonitorConfig.PLATFORM_XIANYU, event.platform)
        assertEquals("小白", event.peerName)
        assertEquals("这个还有货吗", event.text)
        assertEquals(fixedNow, event.occurredAt)

        // The same peer + body must not be queued twice.
        assertFalse(enricher.enrich("小白", bubbles))
        assertEquals(1, queued.size)

        // A new inbound body for the same peer is a fresh correction.
        assertTrue(enricher.enrich("小白", listOf(bubble("那拍下了", centerX = 120f))))
        assertEquals(2, queued.size)
        assertEquals("那拍下了", queued.last().text)
    }

    @Test
    fun enrichKeepsTheSummaryWhenTheDeviceOrPageIsUnavailable() {
        val queued = mutableListOf<ImEvent>()
        val noDevice = ImBodyEnricher(
            deviceId = { null },
            clock = { fixedNow },
            accept = { _, event ->
                queued += event
                true
            },
        )
        val bubbles = listOf(bubble("这个还有货吗", centerX = 120f))

        // Unknown device id: keep the delivered summary, queue nothing.
        assertFalse(noDevice.enrich("小白", bubbles))
        assertTrue(queued.isEmpty())

        // Blank peer or unreadable page: same contract.
        val readable = ImBodyEnricher(
            deviceId = { "device-1" },
            clock = { fixedNow },
            accept = { _, event ->
                queued += event
                true
            },
        )
        assertFalse(readable.enrich("  ", bubbles))
        assertFalse(readable.enrich("小白", emptyList()))
        assertTrue(queued.isEmpty())
    }

    private fun replyTask(peer: String, body: String?): AutomationTask {
        val steps = buildList {
            add(AutomationStep.Find("find-messages-tab", 1_000, "xianyu_messages_tab"))
            add(AutomationStep.TapText("open-conversation", 1_000, peer))
            add(
                AutomationStep.Wait(
                    "wait-chat-input", 1_000, ImReplyTaskShape.CHAT_INPUT_LOCATOR, NodeCondition.EXISTS, 100,
                ),
            )
            body?.let {
                add(
                    AutomationStep.Input(
                        "fill-reply", 1_000, ImReplyTaskShape.CHAT_INPUT_LOCATOR, it, false,
                    ),
                )
            }
            add(AutomationStep.Tap("send-reply", 1_000, "xianyu_chat_send", null))
        }
        return AutomationTask(
            taskId = "task-1",
            deviceId = "device-1",
            targetPackage = TargetLocatorRegistry.XIANYU_PACKAGE,
            issuedAt = fixedNow.minusSeconds(60),
            expiresAt = fixedNow.plusSeconds(600),
            maxRunSeconds = 60,
            steps = steps,
        )
    }
}
