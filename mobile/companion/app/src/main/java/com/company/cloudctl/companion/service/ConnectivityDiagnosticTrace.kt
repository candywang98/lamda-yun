package com.company.cloudctl.companion.service

import android.app.KeyguardManager
import android.content.Context
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import com.company.cloudctl.companion.BuildConfig

internal data class DiagnosticClockSample(val elapsed: Long, val uptime: Long) {
    fun sleepMillisSince(previous: DiagnosticClockSample): Long =
        ((elapsed - previous.elapsed) - (uptime - previous.uptime)).coerceAtLeast(0)
}

/** Metadata only: never record tokens, request bodies, peer names or screen contents. */
internal object ConnectivityDiagnosticTrace {
    private var previous: DiagnosticClockSample? = null
    private var power: PowerManager? = null
    private var keyguard: KeyguardManager? = null

    fun initialize(context: Context) {
        if (!BuildConfig.HEARTBEAT_DIAGNOSTIC) return
        power = context.applicationContext.getSystemService(PowerManager::class.java)
        keyguard = context.applicationContext.getSystemService(KeyguardManager::class.java)
    }

    @Synchronized
    fun record(stage: String, detail: String = "") {
        if (!BuildConfig.HEARTBEAT_DIAGNOSTIC) return
        val sample = DiagnosticClockSample(SystemClock.elapsedRealtime(), SystemClock.uptimeMillis())
        val before = previous
        previous = sample
        Log.i(
            "ConnectivityDiag",
            "stage=$stage wall=${System.currentTimeMillis()} elapsed=${sample.elapsed} uptime=${sample.uptime}" +
                " gap=${before?.let { sample.elapsed - it.elapsed } ?: 0}" +
                " sleep=${before?.let(sample::sleepMillisSince) ?: 0}" +
                " interactive=${power?.isInteractive} idle=${power?.isDeviceIdleMode}" +
                " locked=${keyguard?.isKeyguardLocked} $detail",
        )
    }
}
