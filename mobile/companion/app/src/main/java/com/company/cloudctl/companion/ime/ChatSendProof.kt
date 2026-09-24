package com.company.cloudctl.companion.ime

import com.company.cloudctl.companion.automation.ExecutorFailure

/**
 * One chat-input proof, held only until the matching send tap consumes it.
 *
 * Page text, [waitForText] and clipboard contents are not a proof and never
 * enter this slot. A description replace does not call [hold].
 */
internal class ChatSendProof {
    private var held: InputProof? = null

    fun hold(proof: InputProof) {
        if (proof.locatorRef != CHAT_INPUT) {
            throw ExecutorFailure("INPUT_REJECTED", "Only a chat input proof can authorize a send")
        }
        if (proof.taskId.isNullOrBlank() || proof.peerName.isNullOrBlank() || proof.expiresAtElapsedMs == null) {
            throw ExecutorFailure("INPUT_REJECTED", "A chat proof must name its task, peer and monotonic TTL")
        }
        held = proof
    }

    fun peek(): InputProof? = held

    /**
     * True when [proof] is still the held proof and its monotonic deadline has
     * not passed. A clock that moved backwards is treated as expired.
     */
    fun live(proof: InputProof, nowElapsedMs: Long): Boolean {
        val deadline = proof.expiresAtElapsedMs ?: return false
        if (nowElapsedMs < 0L || deadline < nowElapsedMs) return false
        return held === proof || held == proof
    }

    /** Drops the proof. A second send has nothing left to consume. */
    fun consume(): InputProof? = held.also { held = null }

    fun clear() {
        held = null
    }

    companion object {
        const val CHAT_INPUT = "xianyu_chat_input"
    }
}

/**
 * Everything a chat replace leaves behind on the accessibility service:
 * the not-yet-consumed send proof, the task/peer/TTL captured just before
 * the replace, and the per-locator strings remembered for a later poll.
 *
 * [clear] is what [android.accessibilityservice.AccessibilityService.onUnbind]
 * and [android.accessibilityservice.AccessibilityService.onDestroy] must call.
 * A rebound service must not inherit any of the three.
 */
internal class ChatInputLifecycle {
    private val chatProof = ChatSendProof()
    var pendingBind: ChatInputBind? = null
        private set
    private val committedFields = mutableMapOf<String, String>()

    data class ChatInputBind(
        val taskId: String,
        val peerName: String,
        val expiresAtElapsedMs: Long,
    )

    fun begin(taskId: String, peerName: String?, ttlMs: Long, nowElapsedMs: Long) {
        val peer = peerName?.trim()?.takeIf { it.isNotEmpty() }
        pendingBind = if (taskId.isBlank() || peer == null || ttlMs <= 0L || nowElapsedMs < 0L) {
            null
        } else {
            val deadline = nowElapsedMs + ttlMs
            if (deadline < nowElapsedMs) null else ChatInputBind(taskId, peer, deadline)
        }
    }

    /** Drops the pending bind without touching a proof already held. */
    fun takeBind(): ChatInputBind? = pendingBind.also { pendingBind = null }

    fun hold(proof: InputProof) {
        chatProof.hold(proof)
    }

    fun peek(): InputProof? = chatProof.peek()

    fun consume(): InputProof? = chatProof.consume()

    fun remember(locatorRef: String, value: String) {
        committedFields[locatorRef] = value
    }

    fun committed(locatorRef: String): String? = committedFields[locatorRef]

    fun clear() {
        pendingBind = null
        chatProof.clear()
        committedFields.clear()
    }

    fun pendingTaskId(): String? = pendingBind?.taskId

    fun rememberedLocators(): Set<String> = committedFields.keys.toSet()
}
