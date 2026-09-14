package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay

/** One write per fill; a transport acknowledgement is never proof of text acceptance. */
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
    }

    suspend fun execute(value: String) {
        if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
        if (value.isBlank()) fail("INPUT_REJECTED")
        if (!port.activate()) fail("INPUT_REJECTED")
        port.event("CHAT_IME_WAIT_CONNECTION")
        var session: Long? = null
        for (attempt in 0 until 20) {
            if (!port.imeSelected()) fail("INPUT_IME_REQUIRED")
            if (port.focused()) session = port.session()
            if (session != null) break
            // Tapping an already-focused Flutter field can DISMISS the keyboard and
            // kill the editor session. Periodically re-open it; only replace() writes.
            if (attempt in 3..18 && (attempt - 3) % 5 == 0) {
                port.event("CHAT_IME_REOPEN_KEYBOARD")
                port.activate()
            }
            port.pause()
        }
        val bound = session ?: fail("INPUT_REJECTED")
        if (!port.imeSelected() || !port.focused() || port.session() != bound) fail("INPUT_REJECTED")
        port.event("CHAT_IME_COMMIT_ONCE")
        if (!port.replace(bound, value)) fail("INPUT_REJECTED")
        repeat(20) {
            if (!port.imeSelected() || !port.focused() || port.session() != bound) fail("INPUT_REJECTED")
            // Exact equality rejects old drafts, appended garbage and whitespace changes.
            if (port.readText(bound) == value) {
                port.event("CHAT_IME_VERIFIED")
                return
            }
            port.pause()
        }
        fail("INPUT_REJECTED")
    }

    private fun fail(code: String): Nothing {
        port.event("CHAT_$code")
        throw ExecutorFailure(code, if (code == "INPUT_IME_REQUIRED") {
            "Select CloudCtl Input in Companion before running chat replies"
        } else {
            "Chat input session or exact reply readback was not confirmed"
        })
    }
}
