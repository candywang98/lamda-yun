package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.automation.AutomationTask

/**
 * I10 reply boundary (fail-closed): an outbound IM reply may only be typed and
 * sent into the ONE conversation that the authorized inbound triggered.
 *
 * Division of labour with the existing machinery (all reused read-only):
 *  - automation/ChatInputCommit + SendAuthorization already fail the FIELD
 *    level: one write per fill, exact full-length readback authorizes the send
 *    (INPUT_TARGET_CHANGED on focus drift, INPUT_* otherwise).
 *  - cloud im_service.reply already fails the REQUEST level: thread must have
 *    an inbound, DEVICE_BUSY single-writer, 60s per-thread cooldown.
 *  - this object is the CONVERSATION-level decision for the device send seam:
 *    which chat is open, whether the triggering inbound is visible in it, and
 *    whether the session is even an authorized buyer conversation. Anything it
 *    cannot prove is refused with a stable code — it never degrades to allow.
 *
 * Refused classes (task card I10): 错会话 -> WRONG_CONVERSATION; 焦点变化 ->
 * TARGET_CHANGED (conversation identity drift; field drift stays INPUT_TARGET_CHANGED);
 * 转转/错发（内容属于另一个会话）-> WRONG_CONVERSATION; 主动群发（无可追溯入站触发）
 * -> NO_INBOUND_TRIGGER; 系统通知/营销会话 -> SYSTEM_SESSION; 买家骚扰类标记会话
 * -> HARASSMENT_SESSION. Unverifiable state -> CONVERSATION_UNVERIFIED.
 *
 * Pure Kotlin, JVM unit-testable.
 */
object ImReplyBoundary {

    /** Stable refusal codes surfaced in device logs and the operator UI. */
    enum class Refusal(val code: String) {
        WRONG_CONVERSATION("REPLY_WRONG_CONVERSATION"),
        CONVERSATION_UNVERIFIED("REPLY_CONVERSATION_UNVERIFIED"),
        TARGET_CHANGED("REPLY_CHAT_TARGET_CHANGED"),
        NO_INBOUND_TRIGGER("REPLY_NO_INBOUND_TRIGGER"),
        SYSTEM_SESSION("REPLY_SYSTEM_SESSION"),
        HARASSMENT_SESSION("REPLY_HARASSMENT_SESSION"),
    }

    sealed interface Verdict {
        /** The open conversation is provably the authorized one: the reply may go out. */
        data object Allow : Verdict

        data class Refuse(val refusal: Refusal, val detail: String) : Verdict {
            val code: String get() = refusal.code
        }
    }

    /**
     * What the open chat page verifiably shows at the moment a send is about to
     * fire. Nulls/false mean "cannot prove" — never "assume the best".
     *
     * @param openPeerName identity of the conversation the chat page actually
     *   shows (title/peer node), null when it cannot be resolved.
     * @param chatInputVisible the chat input of THAT conversation is on screen.
     * @param triggeringInboundVisible the inbound this reply answers is visible
     *   as a left-side bubble in THIS conversation (traceable trigger).
     * @param inboundFlaggedHarassment the triggering inbound carries a
     *   harassment mark (operator flag / calibrated spam classifier).
     */
    data class ChatEvidence(
        val openPeerName: String?,
        val chatInputVisible: Boolean,
        val triggeringInboundVisible: Boolean,
        val inboundFlaggedHarassment: Boolean = false,
    )

    /**
     * The conversation-level send decision for a cloud-issued reply task.
     * Non-reply tasks are out of scope and pass through untouched.
     */
    fun check(task: AutomationTask, evidence: ChatEvidence): Verdict {
        val peer = ImReplyTaskShape.peerNameOf(task) ?: return Verdict.Allow
        if (isSystemOrMarketingSource(peer)) {
            return Verdict.Refuse(Refusal.SYSTEM_SESSION, "peer「$peer」is a system/official sender")
        }
        if (evidence.inboundFlaggedHarassment) {
            return Verdict.Refuse(Refusal.HARASSMENT_SESSION, "triggering inbound carries a harassment mark")
        }
        val open = evidence.openPeerName?.trim()
        if (open.isNullOrEmpty()) {
            return Verdict.Refuse(
                Refusal.CONVERSATION_UNVERIFIED,
                "open conversation identity could not be resolved; fail closed",
            )
        }
        if (!open.equals(peer.trim(), ignoreCase = false)) {
            // 错会话/转转: the content belongs to another conversation.
            return Verdict.Refuse(
                Refusal.WRONG_CONVERSATION,
                "open=「$open」 expected=「${peer.trim()}」",
            )
        }
        if (!evidence.chatInputVisible) {
            return Verdict.Refuse(
                Refusal.CONVERSATION_UNVERIFIED,
                "chat input not visible in the authorized conversation",
            )
        }
        if (!evidence.triggeringInboundVisible) {
            return Verdict.Refuse(
                Refusal.NO_INBOUND_TRIGGER,
                "no traceable inbound from「$open」on the page; unsolicited send refused",
            )
        }
        return Verdict.Allow
    }

    /**
     * Focus drift between the conversation identity pinned when the reply
     * started and the live one at send time — mirrors (and is checked before)
     * ChatInputCommit's field-level INPUT_TARGET_CHANGED rule: known identities
     * that differ refuse; unknown (null) never authorizes an override.
     */
    fun conversationChanged(pinnedPeer: String?, livePeer: String?): Boolean =
        pinnedPeer != null && livePeer != null && pinnedPeer.trim() != livePeer.trim()

    /**
     * Full input proof for the audit line before the single send: the reply
     * content bound to its task and target conversation.
     */
    data class ReplyProof(val taskId: String, val peerName: String, val replyText: String?) {
        override fun toString(): String =
            "taskId=$taskId peer=${peerName.take(32)} chars=${replyText?.length ?: 0}"
    }

    fun proofOf(task: AutomationTask): ReplyProof? {
        val peer = ImReplyTaskShape.peerNameOf(task) ?: return null
        return ReplyProof(
            taskId = task.taskId,
            peerName = peer,
            replyText = ImReplyTaskShape.replyTextOf(task),
        )
    }

    /** A system/official sender identity never becomes a replyable conversation. */
    fun isSystemOrMarketingSource(peerName: String): Boolean {
        val name = peerName.trim()
        if (name.isEmpty()) return false
        val sources = ImFeedNoiseFilter.BUILTIN_SYSTEM_SOURCE_TITLES +
            ImFeedNoiseFilter.profile().systemSources.map { it.trim() }.filter { it.isNotEmpty() }
        return sources.any { it.equals(name, ignoreCase = true) }
    }
}
