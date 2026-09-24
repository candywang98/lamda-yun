package com.company.cloudctl.companion.im

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.data.ImOutboxStore

/** Acceptance-only shell switch for the persisted IM upload hold. */
class ImUploadHoldReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != ImUploadHold.ACTION || !intent.hasExtra(ImUploadHold.EXTRA_HELD)) return
        val store = ImOutboxStore(context)
        try {
            val held = intent.getBooleanExtra(ImUploadHold.EXTRA_HELD, false)
            check(ImUploadHold.apply(store, held, BuildConfig.IM_UPLOAD_HOLD_ALLOWED)) {
                "upload hold was not persisted"
            }
        } finally {
            store.close()
        }
    }
}
