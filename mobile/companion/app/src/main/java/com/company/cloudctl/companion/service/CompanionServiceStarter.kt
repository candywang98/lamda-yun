package com.company.cloudctl.companion.service

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

/** Result of one guarded foreground-start attempt (B11 任务 2 启动异常). */
sealed interface ServiceStartAttempt {
    data object Started : ServiceStartAttempt
    data object NotBound : ServiceStartAttempt
    data class Refused(val reasonCode: String, val error: Exception?) : ServiceStartAttempt
}

object CompanionServiceStarter {
    fun startIfBound(context: Context): Boolean =
        tryStartIfBound(context) is ServiceStartAttempt.Started

    /**
     * Guarded start: a platform refusal (background start restrictions on
     * Android 12+, illegal state, missing permission) is classified and
     * returned instead of crashing the caller — BootReceiver must survive to
     * record the outcome as NEEDS_USER with a queryable reason.
     */
    fun tryStartIfBound(
        context: Context,
        launcher: (Context, Intent) -> Unit = ContextCompat::startForegroundService,
    ): ServiceStartAttempt {
        val applicationContext = context.applicationContext
        if (!hasBinding(applicationContext)) return ServiceStartAttempt.NotBound
        val intent = Intent(applicationContext, CompanionSyncService::class.java)
        return try {
            launcher(applicationContext, intent)
            ServiceStartAttempt.Started
        } catch (error: android.app.ForegroundServiceStartNotAllowedException) {
            ServiceStartAttempt.Refused("START_NOT_ALLOWED", error)
        } catch (error: IllegalStateException) {
            ServiceStartAttempt.Refused("FOREGROUND_START_ILLEGAL_STATE", error)
        } catch (error: SecurityException) {
            ServiceStartAttempt.Refused("FOREGROUND_START_SECURITY", error)
        }
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
