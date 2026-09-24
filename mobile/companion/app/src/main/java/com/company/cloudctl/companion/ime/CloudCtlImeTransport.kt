package com.company.cloudctl.companion.ime

import android.os.Looper
import android.view.inputmethod.InputConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * CloudCtl IME read/write used while that IME is actually selected (API 29–32).
 *
 * The pre-API-33 [InputConnection] does not expose a trustworthy selection, so
 * this transport never invents a caret-at-end. Proof is the full text plus the
 * session generation and field identity. Commit still runs only for an empty
 * field whose complete read is empty or already the expected text.
 */
internal class CloudCtlImeTransport(
    private val targetPackage: String,
    private val sessionOf: () -> Long? = { CloudCtlInputMethod.chatSession(targetPackage) },
    private val readOf: (Long) -> String? = { CloudCtlInputMethod.readChatText(targetPackage, it) },
    private val connectionOf: (Long) -> InputConnection? = { session ->
        if (CloudCtlInputMethod.chatSession(targetPackage) == session) {
            CloudCtlInputMethod.active?.currentInputConnection
        } else {
            null
        }
    },
    private val identityOf: () -> ImeSessionIdentity.FieldIdentity? = { CloudCtlInputMethod.currentEditorIdentity() },
    private val onMain: Boolean = true,
) : EditorTransport {
    private var commits = 0

    override fun commitCount(): Int = commits

    override suspend fun snapshot(): EditorSnapshot? = onImeThread {
        val identity = identityOf()?.takeIf { it.packageName == targetPackage } ?: return@onImeThread null
        if (EditorPrivacy.password(identity.inputType)) return@onImeThread null
        val session = sessionOf() ?: return@onImeThread null
        val text = readOf(session) ?: return@onImeThread null
        val truncated = text.length > CompleteEditorText.MAX_LENGTH
        val body = if (truncated) "" else text
        EditorSnapshot(
            generation = session,
            field = identity.fingerprint,
            text = body,
            selectionStart = 0,
            selectionEnd = 0,
            composing = false,
            offsetKnown = !truncated,
            offset = 0,
            truncated = truncated,
            selectionKnown = false,
        )
    }

    override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean = onImeThread {
        // Empty only. A non-empty field — even one that already equals the
        // expected text — is verified by the caller and never rewritten.
        if (snapshot.text.isNotEmpty() || text.isEmpty()) return@onImeThread false
        val identity = identityOf() ?: return@onImeThread false
        if (identity.packageName != targetPackage || identity.fingerprint != snapshot.field) return@onImeThread false
        if (EditorPrivacy.password(identity.inputType)) return@onImeThread false
        val session = sessionOf() ?: return@onImeThread false
        if (session != snapshot.generation) return@onImeThread false
        val connection = connectionOf(session) ?: return@onImeThread false
        val current = readOf(session)
        // The write-time read is the safety fact. A missing read, or any
        // non-empty draft, refuses instead of selecting-to-end and overwriting.
        if (current == null || current.isNotEmpty()) return@onImeThread false
        val accepted = runCatching { connection.commitText(text, 1) }.getOrDefault(false)
        if (accepted) commits += 1
        accepted
    }

    private suspend fun <T> onImeThread(block: () -> T): T {
        if (!onMain || Looper.myLooper() == Looper.getMainLooper()) return block()
        return withContext(Dispatchers.Main.immediate) { block() }
    }
}
