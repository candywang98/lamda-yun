package com.company.cloudctl.companion.ime

import android.view.inputmethod.ExtractedTextRequest
import android.view.inputmethod.InputConnection

/**
 * No queued text, context menus, clipboard or unbounded deletion.
 *
 * Flutter text fields frequently do not implement getExtractedText (or report the
 * platform-default partial offsets of 0 instead of the documented -1 sentinel), so
 * the snapshot path must degrade to exact cursor-window reads instead of failing.
 *
 * [replace] is the legacy whole-field write. Chat on API 30–32 must not use it:
 * a non-empty different draft is the user's text. Use [commitIfEmpty] after a
 * complete [read], and never invent a selection to justify the write.
 */
internal object ImeTextReplacement {
    private const val CURSOR_WINDOW = 10_000

    /**
     * Empty field: commit once at the cursor. Already equal: do not write.
     * Anything else, or a read that is not the whole field: refuse.
     */
    fun commitIfEmpty(connection: InputConnection, text: String): Boolean {
        if (text.isEmpty()) return false
        val current = read(connection) ?: return false
        if (current == text) return true
        if (current.isNotEmpty()) return false
        if (!connection.finishComposingText()) return false
        return connection.commitText(text, 1)
    }

    fun read(connection: InputConnection): String? {
        val extracted = runCatching { connection.getExtractedText(ExtractedTextRequest(), 0) }.getOrNull()
        if (extracted?.text != null && extracted.startOffset == 0) {
            // With startOffset 0 and a non-null text the snapshot spans the whole field;
            // partial offset values vary by implementation and are not authoritative.
            return extracted.text?.toString()
        }
        val before = runCatching { connection.getTextBeforeCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return null
        val after = runCatching { connection.getTextAfterCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return null
        // A window that comes back full may be clipped. Refuse it instead of
        // treating a prefix as the whole field.
        if (before.length >= CURSOR_WINDOW || after.length >= CURSOR_WINDOW) return null
        return "$before$after"
    }

    fun replace(connection: InputConnection, text: String): Boolean {
        if (!connection.finishComposingText()) return false
        val before = runCatching { connection.getTextBeforeCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return false
        val after = runCatching { connection.getTextAfterCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return false
        if (before.isEmpty() && after.isEmpty()) {
            // An empty focused composer commits at the cursor; a selection change here is
            // what provokes the Flutter editor restart that swallows the text.
            return connection.commitText(text, 1)
        }
        connection.beginBatchEdit()
        return try {
            if (!connection.setSelection(0, before.length + after.length)) false
            else connection.commitText(text, 1)
        } finally {
            connection.endBatchEdit()
        }
    }
}
