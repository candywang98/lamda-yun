package com.company.cloudctl.companion.ime

import android.inputmethodservice.InputMethodService
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
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
        connection.deleteSurroundingText(10_000, 10_000)
        val committed = connection.commitText(text, 1)
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

        fun requestCommit(text: String): Boolean {
            val ime = active ?: return false
            return ime.commitNow(text)
        }
    }
}
