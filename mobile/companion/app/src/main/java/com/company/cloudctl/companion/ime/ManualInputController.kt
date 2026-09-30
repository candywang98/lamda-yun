package com.company.cloudctl.companion.ime

import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection

internal class ManualInputController(
    private val connectionOf: () -> InputConnection?,
    private val blocked: () -> Boolean,
    private val onAction: () -> Unit,
    private val switchKeyboard: () -> Boolean,
    private val hideKeyboard: () -> Unit,
) {
    sealed interface Action {
        data class Text(val value: String) : Action
        data object Delete : Action
        data object Newline : Action
        data object Layout : Action
        data object Switch : Action
        data object Hide : Action
    }

    var binding = 0L
        private set
    private var connection: InputConnection? = null
    private var hasSelection: Boolean? = null
    private var multiline = false
    private var suspended = true

    fun reset() {
        binding++
        connection = null
        hasSelection = null
        multiline = false
        suspended = true
    }

    fun bind(editor: EditorInfo?) {
        reset()
        if (editor == null) return
        suspended = false
        connection = runCatching(connectionOf).getOrNull()
        updateSelection(editor.initialSelStart, editor.initialSelEnd)
        multiline = editor.inputType and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_TEXT &&
            editor.inputType and InputType.TYPE_TEXT_FLAG_MULTI_LINE != 0 &&
            editor.imeOptions and EditorInfo.IME_MASK_ACTION != EditorInfo.IME_ACTION_SEND
    }

    fun updateSelection(start: Int, end: Int) {
        hasSelection = if (start >= 0 && end >= 0) start != end else null
    }

    fun refresh() {
        binding++
    }

    fun suspendInput() {
        refresh()
        suspended = true
    }

    fun resumeInput() {
        refresh()
        val live = runCatching(connectionOf).getOrNull()
        if (live !== connection) hasSelection = null
        connection = live
        suspended = false
    }

    fun canType(): Boolean = !suspended && !blocked() && connection != null

    fun canNewline(): Boolean = canType() && multiline

    fun perform(capturedBinding: Long, action: Action): Boolean {
        if (capturedBinding != binding) return false
        if (action == Action.Switch || action == Action.Hide) {
            onAction()
            binding++
            return runCatching {
                if (action == Action.Switch) switchKeyboard() else {
                    hideKeyboard()
                    true
                }
            }.getOrDefault(false)
        }
        if (suspended || blocked()) return false
        onAction()
        val live = runCatching(connectionOf).getOrNull()
        if (live == null || live !== connection) {
            reset()
            return false
        }
        if (action == Action.Delete && hasSelection == null) return false
        val accepted = runCatching {
            when (action) {
                is Action.Text -> {
                    if (action.value.isEmpty() || action.value.any { it !in ' '..'~' }) false
                    else commit(live, action.value)
                }
                Action.Delete -> {
                    when (hasSelection) {
                        null -> false
                        true -> commit(live, "")
                        false -> live.deleteSurroundingTextInCodePoints(1, 0)
                    }
                }
                Action.Newline -> multiline && commit(live, "\n")
                Action.Layout -> true
                else -> false
            }
        }.getOrDefault(false)
        if (!accepted) reset()
        return accepted
    }

    private fun commit(live: InputConnection, text: String): Boolean = live.commitText(text, 1).also { accepted ->
        if (accepted) hasSelection = false
    }
}
