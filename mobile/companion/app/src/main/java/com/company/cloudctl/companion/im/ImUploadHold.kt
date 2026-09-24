package com.company.cloudctl.companion.im

import android.content.Intent
import android.util.Log
import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.data.ImOutboxStore

/** Only the controlled acceptance build can enable a persisted upload hold. */
object ImUploadHold {
    const val ACTION = "com.company.cloudctl.companion.action.IM_OUTBOX_HOLD"
    const val EXTRA_HELD = "held"

    fun apply(store: ImOutboxStore, held: Boolean, allowed: Boolean = BuildConfig.IM_UPLOAD_HOLD_ALLOWED): Boolean {
        if (held && !allowed) {
            Log.w(TAG, "IM_OUTBOX_HOLD refused")
            return false
        }
        store.setUploadHeld(held)
        return store.uploadHeld() == held
    }

    /** @return true when [intent] was this action and the flag now matches it. */
    fun applyIntent(store: ImOutboxStore, intent: Intent?, allowed: Boolean = BuildConfig.IM_UPLOAD_HOLD_ALLOWED): Boolean {
        if (intent?.action != ACTION || !intent.hasExtra(EXTRA_HELD)) return false
        return apply(store, intent.getBooleanExtra(EXTRA_HELD, false), allowed)
    }

    private const val TAG = "ImOutbox"
}
