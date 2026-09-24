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
        session = gate.onEditorStarted()
        Log.i(TAG, "IME_SESSION_STARTED session=$session restarting=$restarting")
    }

    override fun onFinishInput() {
        session = null
        gate.onEditorFinished()
        Log.i(TAG, "IME_SESSION_FINISHED")
        super.onFinishInput()
    }

    companion object {
        private const val TAG = "CloudCtlIme"
        private val gate = ImeSessionGate()

        @Volatile
        var active: CloudCtlInputMethod? = null
            private set

        /** Enabled check uses only the public InputMethodManager API. */
        fun isEnabled(context: Context): Boolean {
            val manager = context.getSystemService(InputMethodManager::class.java) ?: return false
            return manager.enabledInputMethodList.any { it.id in ImeAvailability.candidates(context.packageName) }
        }

        /**
         * Display-only status. Reads the read-allowed Secure default-IME key wrapped in
         * runCatching, so a hostile OEM settings provider cannot crash the app. The
         * operative write paths (chatSession/replaceChatText/readChatText/requestCommit)
         * never consult Secure state: a live IME service bound to the target editor IS
         * the selection proof, because Android only starts the selected input method.
         */
        fun isSelected(context: Context): Boolean {
            val selected = runCatching {
                Settings.Secure.getString(context.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
            }.getOrNull() ?: return false
            return selected in ImeAvailability.candidates(context.packageName)
        }

        fun isCurrent(context: Context): Boolean = isSelected(context) && active != null

        fun hasInputConnection(): Boolean = active?.currentInputConnection != null

        /**
         * Recoverable UI path when binding fails: opens the PUBLIC system picker so the
         * user can select this IME. Enabling never writes restricted Settings.Secure
         * keys, and a framework failure here surfaces false instead of crashing.
         */
        fun requestUserSelection(context: Context): Boolean {
            val manager = context.getSystemService(InputMethodManager::class.java) ?: return false
            return ImeAvailability.pickerRequest { manager.showInputMethodPicker() }
        }

        /** Identity of the editor the IME is currently bound to; null without a live editor. */
        fun currentEditorIdentity(): ImeSessionIdentity.FieldIdentity? =
            active?.currentInputEditorInfo?.let(ImeSessionIdentity::of)

        // Chat calls run on Main, serialized with IME lifecycle callbacks.
        internal fun chatSession(targetPackage: String): Long? {
            check(Looper.myLooper() == Looper.getMainLooper())
            val ime = active ?: return null
            val editor = ime.currentInputEditorInfo ?: return null
            if (editor.packageName != targetPackage) return null
            val bound = ime.session ?: return null
            if (!gate.admits(bound)) return null
            return ime.currentInputConnection?.let { bound }
        }

        private fun chatConnection(targetPackage: String, session: Long): InputConnection? =
            if (chatSession(targetPackage) == session) active?.currentInputConnection else null

        internal fun replaceChatText(targetPackage: String, session: Long, text: String): Boolean {
            val connection = chatConnection(targetPackage, session) ?: return false
            // API 30–32 chat: read the whole field first. A non-empty different
            // draft is never selected-to-end and overwritten.
            return runCatching { ImeTextReplacement.commitIfEmpty(connection, text) }.getOrDefault(false)
        }

        internal fun readChatText(targetPackage: String, session: Long): String? {
            val connection = chatConnection(targetPackage, session) ?: return null
            return runCatching { ImeTextReplacement.read(connection) }.getOrNull()
        }

        /**
         * Description commit. When [pinned] is supplied the live editor must still be
         * that exact field; a generation or field-identity mismatch refuses the write
         * instead of replaying text onto whatever happens to be focused now.
         */
        suspend fun requestCommit(
            text: String,
            pinned: ImeSessionIdentity.FieldIdentity? = null,
        ): Boolean = withContext(Dispatchers.Main.immediate) {
            val ime = active ?: return@withContext false
            val editor = ime.currentInputEditorInfo ?: return@withContext false
            if (pinned != null && !ImeSessionIdentity.sameField(pinned, ImeSessionIdentity.of(editor))) {
                return@withContext false
            }
            val bound = ime.session ?: return@withContext false
            if (!gate.admits(bound)) return@withContext false
            val connection = ime.currentInputConnection ?: return@withContext false
            runCatching { ImeTextReplacement.replace(connection, text) }.getOrDefault(false)
        }
    }
}
