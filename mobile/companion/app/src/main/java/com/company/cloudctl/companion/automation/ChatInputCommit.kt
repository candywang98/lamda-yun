package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.ime.CloudCtlInputMethod
import kotlinx.coroutines.delay

/**
 * One write per fill; a transport acknowledgement is never proof of text acceptance.
 * The write is pinned to (editor generation, target field identity): either going
 * stale — the editor restarted, or the user switched fields — fails closed instead
 * of replaying input onto whatever field happens to be focused now.
 */
internal class ChatInputCommit(private val port: Port) {
    interface Port {
        fun imeSelected(): Boolean
        suspend fun activate(): Boolean
        fun focused(): Boolean
        fun session(): Long?
        fun replace(session: Long, value: String): Boolean
        fun readText(session: Long): String?
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

    suspend fun execute(value: String) {
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
        // Final guard right before the single write.
        if (targetChanged(boundField, port.fieldIdentity())) fail("INPUT_TARGET_CHANGED")
        port.event("CHAT_IME_COMMIT_ONCE")
        if (!port.replace(bound, value)) fail("INPUT_REJECTED")
        repeat(20) {
            if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
            if (port.session() == null) fail("INPUT_REJECTED")
            if (targetChanged(boundField, port.fieldIdentity())) fail("INPUT_TARGET_CHANGED")
            // Exact equality (full length and content) rejects old drafts, appended
            // garbage, whitespace changes, truncated prefixes and emoji loss. The
            // clipboard is deliberately not consulted — see SendAuthorization.
            if (SendAuthorization.authorized(port.readText(bound), value, port.clipboardContents())) {
                port.event("CHAT_IME_VERIFIED")
                return
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
