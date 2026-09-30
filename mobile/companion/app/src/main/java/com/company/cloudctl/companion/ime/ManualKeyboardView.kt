package com.company.cloudctl.companion.ime

import android.content.Context
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.company.cloudctl.companion.R

internal class ManualKeyboardView(
    context: Context,
    private val controller: ManualInputController,
) : LinearLayout(context) {
    private var shifted = false
    private var symbols = false
    private var moreSymbols = false
    private var render = 0L

    init {
        orientation = VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
        reset()
    }

    fun reset() {
        shifted = false
        symbols = false
        moreSymbols = false
        drawKeys()
    }

    private fun drawKeys() {
        val frame = ++render
        val binding = controller.binding
        removeAllViews()
        addView(TextView(context).apply {
            setText(R.string.ime_recovery_message)
            textSize = 13f
        }, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        val escape = row()
        key(escape, context.getString(R.string.ime_recovery_action), frame, binding, ManualInputController.Action.Switch)
        key(escape, context.getString(R.string.ime_hide), frame, binding, ManualInputController.Action.Hide)
        if (!controller.canType()) return
        val characters = if (symbols) {
            if (moreSymbols) listOf("[]{}<>_~`|", "\"'\\^$%&*+=", "!?.,:;/")
            else listOf("1234567890", "@#$%&*-+=/", "!?.,:;()")
        } else {
            listOf("qwertyuiop", "asdfghjkl", "zxcvbnm").map { if (shifted) it.uppercase() else it }
        }
        characters.forEachIndexed { index, letters ->
            val line = row()
            if (index == 2) {
                key(line, if (symbols) "#+=" else if (shifted) "⇧ ON" else "⇧", frame, binding, ManualInputController.Action.Layout) {
                    if (symbols) moreSymbols = !moreSymbols else shifted = !shifted
                }
            }
            letters.forEach { character ->
                key(line, character.toString(), frame, binding, ManualInputController.Action.Text(character.toString()))
            }
            if (index == 2) key(line, "⌫", frame, binding, ManualInputController.Action.Delete)
        }
        val bottom = row()
        key(bottom, if (symbols) "ABC" else "123 #+", frame, binding, ManualInputController.Action.Layout) {
            symbols = !symbols
        }
        key(bottom, context.getString(R.string.ime_space), frame, binding, ManualInputController.Action.Text(" "), weight = 2f)
        key(bottom, context.getString(R.string.ime_newline), frame, binding, ManualInputController.Action.Newline).isEnabled =
            controller.canNewline()
    }

    private fun row(): LinearLayout = LinearLayout(context).also {
        it.orientation = HORIZONTAL
        addView(it, LayoutParams(LayoutParams.MATCH_PARENT, dp(48)))
    }

    private fun key(
        row: LinearLayout,
        label: String,
        frame: Long,
        binding: Long,
        action: ManualInputController.Action,
        weight: Float = 1f,
        changeLayout: (() -> Unit)? = null,
    ): Button = Button(context).also { button ->
        button.text = label
        button.contentDescription = when (label) {
            "⌫" -> context.getString(R.string.ime_delete)
            "⇧", "⇧ ON" -> context.getString(R.string.ime_shift)
            else -> label
        }
        button.isAllCaps = false
        button.textSize = if (label.length > 2) 14f else 18f
        button.minWidth = 0
        button.minimumWidth = 0
        button.setPadding(0, 0, 0, 0)
        button.setSingleLine()
        button.setOnClickListener {
            if (frame != render || !button.isEnabled) return@setOnClickListener
            val accepted = controller.perform(binding, action)
            if (accepted) changeLayout?.invoke()
            if (!accepted || changeLayout != null || action == ManualInputController.Action.Switch ||
                action == ManualInputController.Action.Hide
            ) drawKeys()
        }
        row.addView(button, LayoutParams(0, LayoutParams.MATCH_PARENT, weight))
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
