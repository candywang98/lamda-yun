package com.company.cloudctl.companion.service

import android.app.Notification
import android.app.Service

/**
 * Debug does not declare CompanionSyncService. The method exists so main
 * compiles; a debug process never starts that service, so this is not called.
 */
internal object SyncForeground {
    @Suppress("UNUSED_PARAMETER")
    fun start(service: Service, notificationId: Int, notification: Notification) {
        error("DEBUG_SYNC_SERVICE_ABSENT")
    }
}
