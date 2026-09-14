package com.company.cloudctl.companion.ime

import android.view.inputmethod.ExtractedTextRequest
import android.view.inputmethod.InputConnection

/** No queued text, context menus, clipboard or unbounded deletion. */
internal object ImeTextReplacement {
    fun read(connection: InputConnection): String? {
        val extracted = connection.getExtractedText(ExtractedTextRequest(), 0) ?: return null
        if (extracted.startOffset != 0 || extracted.partialStartOffset != -1 || extracted.partialEndOffset != -1) return null
        return extracted.text?.toString()
    }

    fun replace(connection: InputConnection, text: String): Boolean {
        if (!connection.finishComposingText()) return false
        val previous = read(connection) ?: return false
        connection.beginBatchEdit()
        return try {
            if (!connection.setSelection(0, previous.length)) false
            else connection.commitText(text, 1)
        } finally {
            connection.endBatchEdit()
        }
    }
}
