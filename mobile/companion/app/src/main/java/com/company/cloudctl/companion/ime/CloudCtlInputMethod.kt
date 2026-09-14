package com.company.cloudctl.companion.ime

import android.content.Context
import android.inputmethodservice.InputMethodService
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.view.inputmethod.InputMethodManager
import android.widget.FrameLayout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Companion-owned IME. Text requests never survive an input session or a failed call. */
class CloudCtlInputMethod : InputMethodService() {
    private var session: Long? = null

    override fun onCreate() {
        super.onCreate()
        active = this
        Log.i(TAG, "IME created")
    }

    override fun onDestroy() {
        session = null
        if (active === this) active = null
        super.onDestroy()
    }

    override fun onCreateInputView(): View = FrameLayout(this).apply {
        layoutParams = FrameLayout.LayoutParams(0, 0)
        visibility = View.GONE
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        session = ++generation
        Log.i(TAG, "IME_SESSION_STARTED session=$session restarting=$restarting")
    }

    override fun onFinishInput() {
        session = null
        Log.i(TAG, "IME_SESSION_FINISHED")
        super.onFinishInput()
    }

    companion object {
        private const val TAG = "CloudCtlIme"
        private var generation = 0L

        @Volatile
        var active: CloudCtlInputMethod? = null
            private set

        fun isEnabled(context: Context): Boolean {
            val manager = context.getSystemService(InputMethodManager::class.java) ?: return false
            return manager.enabledInputMethodList.any { it.id in ImeAvailability.candidates(context.packageName) }
        }

        fun isSelected(context: Context): Boolean {
            val selected = runCatching {
                Settings.Secure.getString(context.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
            }.getOrNull() ?: return false
            return selected in ImeAvailability.candidates(context.packageName)
        }

        fun isCurrent(context: Context): Boolean = isSelected(context) && active != null

        fun hasInputConnection(): Boolean = active?.currentInputConnection != null

        // Chat calls run on Main, serialized with IME lifecycle callbacks.
        internal fun chatSession(targetPackage: String): Long? {
            check(Looper.myLooper() == Looper.getMainLooper())
            val ime = active ?: return null
            if (!isSelected(ime) || ime.currentInputEditorInfo == null ||
                ime.currentInputEditorInfo?.packageName != targetPackage || ime.currentInputConnection == null
            ) return null
            return ime.session
        }

        private fun chatConnection(targetPackage: String, session: Long): InputConnection? =
            if (chatSession(targetPackage) == session) active?.currentInputConnection else null

        internal fun replaceChatText(targetPackage: String, session: Long, text: String): Boolean {
            val connection = chatConnection(targetPackage, session) ?: return false
            return runCatching { ImeTextReplacement.replace(connection, text) }.getOrDefault(false)
        }

        internal fun readChatText(targetPackage: String, session: Long): String? {
            val connection = chatConnection(targetPackage, session) ?: return null
            return runCatching { ImeTextReplacement.read(connection) }.getOrNull()
        }

        suspend fun requestCommit(text: String): Boolean = withContext(Dispatchers.Main.immediate) {
            val ime = active ?: return@withContext false
            if (!isSelected(ime) || ime.currentInputEditorInfo == null) return@withContext false
            val connection = ime.currentInputConnection ?: return@withContext false
            runCatching { ImeTextReplacement.replace(connection, text) }.getOrDefault(false)
        }
    }
}
