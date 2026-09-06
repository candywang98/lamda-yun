package com.company.cloudctl.companion.service

import android.content.Intent

internal object ServiceLaunchPolicy {
    const val ACTION_RESTART_SYNC = "com.company.cloudctl.companion.RESTART_SYNC"
    const val ACTION_QUICKBOOT_POWERON = "android.intent.action.QUICKBOOT_POWERON"

    private val supportedActions = setOf(
        Intent.ACTION_BOOT_COMPLETED,
        Intent.ACTION_MY_PACKAGE_REPLACED,
        Intent.ACTION_USER_UNLOCKED,
        ACTION_QUICKBOOT_POWERON,
        ACTION_RESTART_SYNC,
    )

    fun shouldStart(action: String?, hasBinding: Boolean): Boolean =
        hasBinding && action in supportedActions
}

internal object BatteryOptimizationPolicy {
    fun shouldPrompt(bound: Boolean, ignoring: Boolean): Boolean = bound && !ignoring
}

internal object ForegroundRestartPolicy {
    const val DELAY_MILLIS = 15_000L

    fun shouldSchedule(hasBinding: Boolean): Boolean = hasBinding
}
