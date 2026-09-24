package com.company.cloudctl.companion.ime

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.InputMethod
import android.os.Build
import android.text.InputType
import android.text.Spanned
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.SurroundingText
import androidx.annotation.RequiresApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal object EditorPrivacy {
    fun password(inputType: Int): Boolean {
        val type = inputType and InputType.TYPE_MASK_CLASS
        val variation = inputType and InputType.TYPE_MASK_VARIATION
        return (type == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD) ||
            (type == InputType.TYPE_CLASS_TEXT && variation in setOf(
                InputType.TYPE_TEXT_VARIATION_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
            ))
    }

    fun composing(text: CharSequence): Boolean = text is Spanned &&
        text.getSpans(0, text.length, Any::class.java).any { text.getSpanFlags(it) and Spanned.SPAN_COMPOSING != 0 }
}

/**
 * API 33 accessibility editor. Lifecycle callbacks stay on the main thread;
 * [getSurroundingText] can block for two seconds, so it runs on IO and the
 * result is discarded unless the captured generation is still current.
 *
 * [onUpdateSelection]'s old-selection arguments are not consulted: Android 15
 * does not reliably populate them.
 */
@RequiresApi(Build.VERSION_CODES.TIRAMISU)
internal class AccessibilityEditor(service: AccessibilityService) : InputMethod(service) {
    private var generation = 0L
    private var field: ImeSessionIdentity.FieldIdentity? = null
    private var password = false
    private var selectionComposing = false

    override fun onStartInput(attribute: EditorInfo, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        generation++
        val identity = ImeSessionIdentity.of(attribute)
        password = identity?.let { EditorPrivacy.password(it.inputType) } == true
        field = identity?.takeUnless { password }
        selectionComposing = false
    }

    override fun onFinishInput() {
        generation++
        field = null
        password = false
        selectionComposing = false
        super.onFinishInput()
    }

    override fun onUpdateSelection(
        oldSelStart: Int,
        oldSelEnd: Int,
        newSelStart: Int,
        newSelEnd: Int,
        candidatesStart: Int,
        candidatesEnd: Int,
    ) {
        super.onUpdateSelection(oldSelStart, oldSelEnd, newSelStart, newSelEnd, candidatesStart, candidatesEnd)
        selectionComposing = candidatesStart >= 0 && candidatesEnd >= candidatesStart
    }

    fun boundTo(targetPackage: String): Boolean =
        !password && field?.packageName == targetPackage && currentInputConnection != null

    /** False while a password editor is bound, even if the package matches. */
    fun passwordBound(): Boolean = password

    private var commits = 0

    fun commitCount(): Int = commits

    fun transport(targetPackage: String): EditorTransport = object : EditorTransport {
        override fun commitCount(): Int = commits

        override suspend fun snapshot(): EditorSnapshot? {
            val captured = withContext(Dispatchers.Main.immediate) {
                if (password) return@withContext null
                val identity = field?.takeIf { it.packageName == targetPackage } ?: return@withContext null
                val connection = currentInputConnection ?: return@withContext null
                Triple(generation, identity.fingerprint, connection)
            } ?: return null
            val around = withContext(Dispatchers.IO) {
                runCatching {
                    captured.third.getSurroundingText(
                        CompleteEditorText.WINDOW,
                        CompleteEditorText.WINDOW,
                        0,
                    )
                }.getOrNull()
            } ?: return null
            return withContext(Dispatchers.Main.immediate) {
                publish(captured.first, captured.second, around, targetPackage)
            }
        }

        override suspend fun commit(snapshot: EditorSnapshot, text: String): Boolean =
            withContext(Dispatchers.Main.immediate) {
                if (password || snapshot.generation != generation || snapshot.field != field?.fingerprint ||
                    selectionComposing || !boundTo(targetPackage)
                ) {
                    return@withContext false
                }
                // Only an empty field is committed. A field that already equals the
                // expected text is left untouched; anything else is the user's draft.
                if (snapshot.text.isNotEmpty()) return@withContext false
                val connection = currentInputConnection ?: return@withContext false
                runCatching {
                    connection.commitText(text, 1, null)
                    commits += 1
                    true
                }.getOrDefault(false)
            }
    }

    private fun publish(capturedGeneration: Long, fingerprint: String, around: SurroundingText, targetPackage: String): EditorSnapshot? {
        val text = around.text?.toString() ?: return null
        if (capturedGeneration != generation || fingerprint != field?.fingerprint || !boundTo(targetPackage)) {
            return null
        }
        val truncated = text.length > CompleteEditorText.MAX_LENGTH
        return EditorSnapshot(
            generation = generation,
            field = fingerprint,
            text = if (truncated) "" else text,
            selectionStart = around.selectionStart,
            selectionEnd = around.selectionEnd,
            composing = selectionComposing || EditorPrivacy.composing(around.text),
            offsetKnown = true,
            offset = around.offset,
            truncated = truncated,
        )
    }
}
