package com.company.cloudctl.companion.service

import android.app.Notification
import android.app.Service
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.ServiceCompat

/** Release still promotes the sync service. Debug has no such service. */
internal object SyncForeground {
    fun start(service: Service, notificationId: Int, notification: Notification) {
        ServiceCompat.startForeground(
            service,
            notificationId,
            notification,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            } else {
                0
            },
        )
    }
}
