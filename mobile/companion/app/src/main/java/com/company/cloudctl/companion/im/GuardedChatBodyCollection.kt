package com.company.cloudctl.companion.im

import kotlinx.coroutines.CancellationException

/** Display-name-level collection guard; not account verification or complete history. */
class GuardedChatBodyCollection(
    private val targetForeground: () -> Boolean,
    private val evidence: () -> ImReplyBoundary.ChatEvidence?,
    private val snapshot: () -> List<ChatBubble>,
    private val swipe: suspend (backward: Boolean) -> Unit = {},
) {
    fun matches(peer: String): Boolean = try {
        val expected = peer.trim()
        if (expected.isEmpty() || !targetForeground()) false else {
            val observed = evidence()
            observed?.chatInputVisible == true &&
                observed.openPeerName?.trim() == expected && targetForeground()
        }
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        false
    }

    /** False means evidence was lost or collection failed; callers must stop navigating. */
    suspend fun collect(
        peer: String,
        maxBackwardSwipes: Int = 0,
        hasBody: (List<ChatBubble>) -> Boolean,
        queue: (List<ChatBubble>) -> Unit,
    ): Boolean {
        try {
            require(maxBackwardSwipes >= 0)
            if (!matches(peer)) return false
            var bubbles = snapshot()
            if (!matches(peer)) return false
            var attempts = 0
            while (attempts < maxBackwardSwipes && !hasBody(bubbles)) {
                if (!matches(peer)) return false
                swipe(true)
                attempts++
                if (!matches(peer)) return false
                if (!matches(peer)) return false
                bubbles = snapshot()
                if (!matches(peer)) return false
            }
            repeat(attempts) {
                if (!matches(peer)) return false
                swipe(false)
                if (!matches(peer)) return false
            }
            val readable = hasBody(bubbles)
            if (!matches(peer)) return false
            if (readable) queue(bubbles)
            return true
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            return false
        }
    }
}
