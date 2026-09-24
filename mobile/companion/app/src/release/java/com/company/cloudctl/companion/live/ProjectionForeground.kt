package com.company.cloudctl.companion.live

import android.app.Notification
import android.app.Service
import android.content.pm.ServiceInfo
import android.os.Build

/** Release declares the projection service with its foreground type. */
internal object ProjectionForeground {
    fun start(service: Service, notificationId: Int, notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            service.startForeground(
                notificationId,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            service.startForeground(notificationId, notification)
        }
    }
}
