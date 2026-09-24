package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.ime.CloudCtlInputMethod
import kotlinx.coroutines.delay

/**
 * One write per fill; a transport acknowledgement is never proof of text acceptance.
 * The write is pinned to (editor generation, target field identity): either going
 * stale — the editor restarted, or the user switched fields — fails closed instead
 * of replaying input onto whatever field happens to be focused now.
 */
/**
 * The two consecutive full-text reads [ChatInputCommit] already required before
 * it returned. The proof is this result — a later [Port.readText] after the IME
 * has been restored is not a substitute.
 *
 * [text] is the full field both times. [generation] is the editor generation of
 * those two reads (it may differ from the generation that received the single
 * write, when Flutter rebuilt the connection after the commit). [fingerprint]
 * is the public EditorInfo identity captured on the second stable read, while
 * CloudCtl is still the selected IME.
 */
internal data class ChatInputReadback(
    val text: String,
    val generation: Long,
    val fingerprint: String?,
)

internal class ChatInputCommit(private val port: Port) {
    interface Port {
        fun imeSelected(): Boolean
        suspend fun activate(): Boolean
        fun focused(): Boolean
        fun session(): Long?
        fun replace(session: Long, value: String): Boolean
        fun readText(session: Long): String?
        /**
         * False on API 30–32 until the temporary switch has selected CloudCtl.
         * The default keeps older tests, which select the IME up front.
         */
        fun armed(): Boolean = true

        /**
         * True only when a complete read of the live field is empty or already
         * equal to [value]. Default refuses: a port that cannot read the draft
         * must not overwrite it.
         */
        fun fieldClearFor(value: String): Boolean = false
        fun event(code: String)
        suspend fun pause() { delay(150) }

        /**
         * Opaque identity of the field the session must stay bound to (the live IME
         * editor fingerprint by default). A null identity degrades to session-only
         * pinning; a MISMATCH never degrades — it fails closed with INPUT_TARGET_CHANGED.
         */
        fun fieldIdentity(): String? =
            CloudCtlInputMethod.currentEditorIdentity()?.fingerprint

        /** Clipboard snapshot exposed only so authorization proofs can IGNORE it. */
        fun clipboardContents(): String? = null
    }

    suspend fun execute(value: String): ChatInputReadback {
        if (!port.armed()) fail("INPUT_IME_REQUIRED")
        if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
        if (value.isBlank()) fail("INPUT_REJECTED")
        if (!port.activate()) fail("INPUT_REJECTED")
        port.event("CHAT_IME_WAIT_CONNECTION")
        var session: Long? = null
        for (attempt in 0 until 20) {
            if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
            // The session itself proves the editor belongs to the target package; the
            // focused accessibility node often lives in the IME window, not the app
            // subtree, so subtree focus must not gate the bind.
            session = port.session()
            if (session != null) break
            // Tapping an already-focused Flutter field can DISMISS the keyboard and
            // kill the editor session. Periodically re-open it; only replace() writes.
            if (attempt in 3..18 && (attempt - 3) % 5 == 0) {
                port.event("CHAT_IME_REOPEN_KEYBOARD")
                port.activate()
            }
            port.pause()
        }
        // Flutter restarts its chat editor roughly every second; a session bound the
        // instant before its scheduled restart swallows the commit. Require the bound
        // session to survive a short stability window before the single write.
        var bound = session ?: fail("INPUT_REJECTED")
        var boundField = port.fieldIdentity()
        var stable = 0
        for (attempt in 0 until 20) {
            if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
            val liveField = port.fieldIdentity()
            if (targetChanged(boundField, liveField)) fail("INPUT_TARGET_CHANGED")
            val current = port.session() ?: fail("INPUT_REJECTED")
            if (current == bound) {
                if (++stable >= 2) break
            } else {
                // The editor restarted. Re-capture the generation and re-verify the
                // field identity before trusting the new connection: the new session
                // may be a DIFFERENT field the user just focused.
                bound = current
                boundField = liveField ?: boundField
                stable = 0
            }
            port.pause()
        }
        if (stable < 2) fail("INPUT_REJECTED")
        // Final guard right before the single write. A non-empty draft that is not
        // already the expected reply is the user's text and is never cleared.
        if (targetChanged(boundField, port.fieldIdentity())) fail("INPUT_TARGET_CHANGED")
        if (!port.fieldClearFor(value)) fail("FIELD_DIRTY_BY_USER")
        port.event("CHAT_IME_COMMIT_ONCE")
        if (!port.replace(bound, value)) fail("INPUT_REJECTED")
        // Two consecutive exact reads of the same live session are the proof.
        // One matching sample is not enough: a transient paint can agree once.
        // The clipboard is deliberately not consulted — see SendAuthorization.
        var confirmed: String? = null
        repeat(20) {
            if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
            val live = port.session() ?: fail("INPUT_REJECTED")
            if (targetChanged(boundField, port.fieldIdentity())) fail("INPUT_TARGET_CHANGED")
            // The editor may restart after the single commit. Re-read that new
            // session; never issue another replace.
            val readback = port.readText(live)
            if (readback != null && SendAuthorization.authorized(readback, value, port.clipboardContents())) {
                // Same session and same full text, twice in a row. The fingerprint
                // is taken now, before the caller restores another keyboard.
                if (confirmed == readback && live == bound) {
                    port.event("CHAT_IME_VERIFIED")
                    return ChatInputReadback(
                        text = readback,
                        generation = live,
                        fingerprint = port.fieldIdentity(),
                    )
                }
                confirmed = readback
                bound = live
            } else {
                confirmed = null
            }
            port.pause()
        }
        fail("INPUT_REJECTED")
    }

    /** A known identity that differs from the pinned one is a field switch: refuse. */
    private fun targetChanged(pinned: String?, live: String?): Boolean =
        pinned != null && live != null && pinned != live

    private fun fail(code: String): Nothing {
        port.event("CHAT_$code")
        throw ExecutorFailure(code, when (code) {
            "INPUT_IME_REQUIRED" -> "Select CloudCtl Input in Companion before running chat replies"
            "INPUT_TARGET_CHANGED" -> "Target field changed during the chat commit; input refused"
            "FIELD_DIRTY_BY_USER" -> "The chat field contains an existing draft; input was not overwritten"
            else -> "Chat input session or exact reply readback was not confirmed"
        })
    }
}

/**
 * Send/publish-class actions key exclusively off the verified live readback of the
 * field this flow committed. Clipboard contents are deliberately not an input: a
 * polluted clipboard (even one holding exactly the expected text) must never
 * authorize a send, and clipboard contents must never substitute for a readback.
 */
internal object SendAuthorization {
    fun authorized(readback: String?, expected: String, clipboard: String?): Boolean =
        readback != null && readback == expected
}
