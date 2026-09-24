package com.company.cloudctl.companion.live

import android.app.Notification
import android.app.Service

/** Debug does not declare the projection service. */
internal object ProjectionForeground {
    @Suppress("UNUSED_PARAMETER")
    fun start(service: Service, notificationId: Int, notification: Notification) {
        error("DEBUG_PROJECTION_SERVICE_ABSENT")
    }
}
