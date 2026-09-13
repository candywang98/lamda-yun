package com.company.cloudctl.companion.ime

import android.content.Context
import android.inputmethodservice.InputMethodService
import android.provider.Settings
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.widget.FrameLayout

/**
 * Signed, companion-owned IME used only to commit automation text into Flutter fields
 * that ignore accessibility ACTION_SET_TEXT.
 */
class CloudCtlInputMethod : InputMethodService() {
    @Volatile
    private var pendingText: String? = null

    override fun onCreate() {
        super.onCreate()
        active = this
        Log.i(TAG, "IME created")
    }

    override fun onDestroy() {
        if (active === this) active = null
        super.onDestroy()
        Log.i(TAG, "IME destroyed")
    }

    override fun onCreateInputView(): View = FrameLayout(this).apply {
        layoutParams = FrameLayout.LayoutParams(0, 0)
        visibility = View.GONE
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        flushPending()
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        flushPending()
    }

    override fun onWindowShown() {
        super.onWindowShown()
        flushPending()
    }

    fun commitNow(text: String): Boolean {
        pendingText = text
        return flushPending()
    }

    private fun flushPending(): Boolean {
        val text = pendingText ?: return currentInputConnection != null
        val connection = currentInputConnection ?: return false
        connection.finishComposingText()
        connection.beginBatchEdit()
        runCatching { connection.performContextMenuAction(android.R.id.selectAll) }
        connection.deleteSurroundingText(10_000, 10_000)
        val committed = connection.commitText(text, 1)
        connection.endBatchEdit()
        if (committed) {
            pendingText = null
            Log.i(TAG, "IME committed ${text.length} chars")
        } else {
            Log.w(TAG, "IME commitText returned false")
        }
        return committed
    }

    companion object {
        private const val TAG = "CloudCtlIme"

        @Volatile
        var active: CloudCtlInputMethod? = null
            private set

        fun isEnabled(context: Context): Boolean =
            ImeAvailability.listed(
                Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_INPUT_METHODS),
                context.packageName,
            )

        fun isSelected(context: Context): Boolean {
            val selected = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.DEFAULT_INPUT_METHOD,
            )
            return ImeAvailability.listed(selected, context.packageName)
        }

        fun isCurrent(context: Context): Boolean = isSelected(context) && active != null

        fun hasInputConnection(): Boolean = active?.currentInputConnection != null

        fun requestCommit(text: String): Boolean {
            val ime = active ?: return false
            val connection: InputConnection = ime.currentInputConnection ?: return false
            Log.i(TAG, "IME requestCommit chars=${text.length} connection=${connection.javaClass.simpleName}")
            return ime.commitNow(text)
        }
    }
}
