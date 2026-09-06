package com.company.cloudctl.companion.service

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

object CompanionServiceStarter {
    fun startIfBound(context: Context): Boolean {
        val applicationContext = context.applicationContext
        if (!hasBinding(applicationContext)) return false
        ContextCompat.startForegroundService(
            applicationContext,
            Intent(applicationContext, CompanionSyncService::class.java),
        )
        return true
    }

    fun scheduleRestartIfBound(context: Context, delayMillis: Long = ForegroundRestartPolicy.DELAY_MILLIS): Boolean {
        val applicationContext = context.applicationContext
        if (!ForegroundRestartPolicy.shouldSchedule(hasBinding(applicationContext))) return false
        val alarm = applicationContext.getSystemService(AlarmManager::class.java) ?: return false
        val pending = PendingIntent.getBroadcast(
            applicationContext,
            RESTART_REQUEST_CODE,
            Intent(applicationContext, BootReceiver::class.java).setAction(ServiceLaunchPolicy.ACTION_RESTART_SYNC),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        alarm.setAndAllowWhileIdle(
            AlarmManager.RTC_WAKEUP,
            System.currentTimeMillis() + delayMillis,
            pending,
        )
        return true
    }

    fun hasBinding(context: Context): Boolean =
        !context.getSharedPreferences(BINDING_PREFERENCES, Context.MODE_PRIVATE)
            .getString(BINDING_KEY, null)
            .isNullOrBlank()

    private const val BINDING_PREFERENCES = "cloudctl_binding"
    private const val BINDING_KEY = "binding"
    private const val RESTART_REQUEST_CODE = 1002
}
