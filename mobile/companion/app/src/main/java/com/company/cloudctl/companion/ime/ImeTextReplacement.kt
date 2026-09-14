package com.company.cloudctl.companion.ime

import android.view.inputmethod.ExtractedTextRequest
import android.view.inputmethod.InputConnection

/**
 * No queued text, context menus, clipboard or unbounded deletion.
 *
 * Flutter text fields frequently do not implement getExtractedText (or report the
 * platform-default partial offsets of 0 instead of the documented -1 sentinel), so
 * the snapshot path must degrade to exact cursor-window reads instead of failing.
 */
internal object ImeTextReplacement {
    private const val CURSOR_WINDOW = 10_000

    fun read(connection: InputConnection): String? {
        val extracted = runCatching { connection.getExtractedText(ExtractedTextRequest(), 0) }.getOrNull()
        if (extracted?.text != null && extracted.startOffset == 0) {
            // With startOffset 0 and a non-null text the snapshot spans the whole field;
            // partial offset values vary by implementation and are not authoritative.
            return extracted.text?.toString()
        }
        val before = runCatching { connection.getTextBeforeCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return null
        val after = runCatching { connection.getTextAfterCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return null
        return "$before$after"
    }

    fun replace(connection: InputConnection, text: String): Boolean {
        if (!connection.finishComposingText()) return false
        val before = runCatching { connection.getTextBeforeCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return false
        val after = runCatching { connection.getTextAfterCursor(CURSOR_WINDOW, 0) }.getOrNull() ?: return false
        connection.beginBatchEdit()
        return try {
            if (!connection.setSelection(0, before.length + after.length)) false
            else connection.commitText(text, 1)
        } finally {
            connection.endBatchEdit()
        }
    }
}
