package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import java.time.Instant

/**
 * A read-only bubble snapshot of an open conversation page (im-live slice 2, gap 2).
 * Geometry thresholds mirror the on-device verified duty-mode reading rules.
 */
data class ChatBubble(
    val text: String,
    val centerX: Float,
    val width: Int,
    val height: Int,
) {
    /** Inbound bubbles hug the left edge; our own replies sit on the right. */
    val inbound: Boolean get() = centerX < ChatPageReading.INBOUND_CENTER_X_MAX

    fun plausible(): Boolean = text.length in ChatPageReading.MIN_TEXT..ChatPageReading.MAX_TEXT &&
        height in ChatPageReading.MIN_HEIGHT..ChatPageReading.MAX_HEIGHT &&
        width in ChatPageReading.MIN_WIDTH..ChatPageReading.MAX_WIDTH
}

object ChatPageReading {
    const val INBOUND_CENTER_X_MAX = 540f
    const val MIN_TEXT = 2
    const val MAX_TEXT = 500
    const val MIN_HEIGHT = 30
    const val MAX_HEIGHT = 260
    const val MIN_WIDTH = 60
    const val MAX_WIDTH = 900

    /** The newest inbound bubble text on the page, or null when nothing is readable. */
    fun latestInbound(bubbles: List<ChatBubble>): String? = bubbles
        .filter { it.inbound && it.plausible() }
        .map { it.text.trim() }
        .lastOrNull { it.isNotEmpty() }

    /** Inbound texts that were never answered by an outbound bubble. */
    fun freshInbound(bubbles: List<ChatBubble>): List<String> {
        val outbound = bubbles
            .filter { !it.inbound && it.plausible() }
            .map { it.text.trim() }
            .toSet()
        return bubbles
            .filter { it.inbound && it.plausible() }
            .map { it.text.trim() }
            .filter { it.isNotEmpty() && it !in outbound }
    }
}

/**
 * Identifies the cloud-issued xianyu IM reply task shape (im_service._reply_steps):
 * a messages-tab find/tap, a tapText on the peer name, chat-input wait/input, send.
 */
object ImReplyTaskShape {
    const val CHAT_INPUT_LOCATOR = "xianyu_chat_input"

    /** The peer name tapped by the reply task, or null when the task is not that shape. */
    fun peerNameOf(task: AutomationTask): String? {
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) return null
        val taps = task.steps.filterIsInstance<AutomationStep.TapText>()
        if (taps.size != 1) return null
        if (task.steps.none { it.locatorRefOrNull() == CHAT_INPUT_LOCATOR }) return null
        return taps.single().value.trim().takeIf { it.isNotEmpty() }
    }

    /** The reply text the task typed into the chat input, when present. */
    fun replyTextOf(task: AutomationTask): String? = task.steps
        .filterIsInstance<AutomationStep.Input>()
        .singleOrNull { it.locatorRefOrNull() == CHAT_INPUT_LOCATOR }
        ?.value

    private fun AutomationStep.locatorRefOrNull(): String? = when (this) {
        is AutomationStep.Find -> locatorRef
        is AutomationStep.Tap -> locatorRef
        is AutomationStep.Input -> locatorRef
        is AutomationStep.Wait -> locatorRef
        is AutomationStep.Assert -> locatorRef
        else -> null
    }
}

/**
 * Backfills the real conversation body (im-live slice 2, gap 2): xianyu push
 * notifications carry only a placeholder such as 「发来一条新消息」, so once a
 * reply task leaves the conversation page open we read the newest inbound
 * bubble and queue it through the ordinary ImMonitor -> sendImMessages path.
 * Failures keep the already-delivered notification summary; enrichment must
 * never block or fail a task.
 */
class ImBodyEnricher(
    private val deviceId: () -> String?,
    private val clock: () -> Instant = Instant::now,
    private val accept: (String, ImEvent) -> Boolean = ImMonitor::accept,
) {
    private val recent = LinkedHashMap<String, Boolean>()

    /** @return true when a corrected body was queued for the cloud. */
    @Synchronized
    fun enrich(peerName: String, bubbles: List<ChatBubble>): Boolean {
        if (peerName.isBlank()) return false
        val text = ChatPageReading.latestInbound(bubbles) ?: return false
        val device = deviceId() ?: return false
        val bounded = text.take(MAX_ENRICHED_TEXT)
        val key = "${peerName.trim()}|$bounded"
        if (recent.containsKey(key)) return false
        recent[key] = true
        if (recent.size > RECENT_LIMIT) recent.remove(recent.keys.first())
        return accept(
            device,
            ImEvent(
                platform = ImMonitorConfig.PLATFORM_XIANYU,
                peerName = peerName.trim().take(128),
                text = bounded,
                occurredAt = clock(),
            ),
        )
    }

    private companion object {
        const val MAX_ENRICHED_TEXT = 2_000
        const val RECENT_LIMIT = 64
    }
}
