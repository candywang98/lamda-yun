package com.company.cloudctl.companion.ime

import android.view.inputmethod.EditorInfo

/**
 * Stable identity of the editor a session is bound to, built only from public
 * EditorInfo fields (volatile hint/initial text deliberately excluded).
 *
 * Generation alone cannot distinguish "same field, Flutter restarted the editor"
 * from "user focused a different field": both bump the generation. Every
 * re-capture after a rejected generation must compare field identity too, and a
 * mismatch must fail closed instead of typing into the new field.
 */
object ImeSessionIdentity {
    data class FieldIdentity(
        val packageName: String,
        val inputType: Int,
        val imeOptions: Int,
        val fieldId: Int,
        val fieldName: String?,
    ) {
        /** Opaque comparable form for pinning across calls (e.g. ChatInputCommit.Port). */
        val fingerprint: String
            get() = "$packageName|$inputType|$imeOptions|$fieldId|${fieldName.orEmpty()}"
    }

    fun of(editorInfo: EditorInfo?): FieldIdentity? {
        if (editorInfo == null) return null
        val packageName = editorInfo.packageName?.toString() ?: return null
        return FieldIdentity(
            packageName = packageName,
            inputType = editorInfo.inputType,
            imeOptions = editorInfo.imeOptions,
            fieldId = editorInfo.fieldId,
            fieldName = editorInfo.fieldName?.toString(),
        )
    }

    /** Both sides must be known and identical; an unknown side is never "same field". */
    fun sameField(pinned: FieldIdentity?, live: FieldIdentity?): Boolean =
        pinned != null && live != null && pinned == live
}
