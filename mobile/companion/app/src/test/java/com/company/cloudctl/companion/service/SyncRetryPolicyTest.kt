package com.company.cloudctl.companion.service

import android.content.Intent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SyncRetryPolicyTest {
    @Test
    fun exponentialBackoffIsBoundedAndResettable() {
        val policy = SyncRetryPolicy(
            initialDelayMillis = 1_000,
            maximumDelayMillis = 8_000,
            jitter = { 1.0 },
        )

        assertEquals(listOf(1_000L, 2_000L, 4_000L, 8_000L, 8_000L),
            List(5) { policy.nextDelayMillis() })

        policy.reset()
        assertEquals(1_000L, policy.nextDelayMillis())
    }

    @Test
    fun bootLaunchRequiresSupportedBroadcastAndExistingBinding() {
        assertTrue(ServiceLaunchPolicy.shouldStart(Intent.ACTION_BOOT_COMPLETED, true))
        assertTrue(ServiceLaunchPolicy.shouldStart(Intent.ACTION_MY_PACKAGE_REPLACED, true))
        assertTrue(ServiceLaunchPolicy.shouldStart(Intent.ACTION_USER_UNLOCKED, true))
        assertTrue(ServiceLaunchPolicy.shouldStart(ServiceLaunchPolicy.ACTION_QUICKBOOT_POWERON, true))
        assertTrue(ServiceLaunchPolicy.shouldStart(ServiceLaunchPolicy.ACTION_RESTART_SYNC, true))
        assertFalse(ServiceLaunchPolicy.shouldStart(Intent.ACTION_BOOT_COMPLETED, false))
        assertFalse(ServiceLaunchPolicy.shouldStart("android.intent.action.USB_STATE", true))
        assertFalse(ServiceLaunchPolicy.shouldStart(null, true))
    }

    @Test
    fun batteryOptimizationPromptOnlyWhenBoundAndNotIgnoring() {
        assertTrue(BatteryOptimizationPolicy.shouldPrompt(true, false))
        assertFalse(BatteryOptimizationPolicy.shouldPrompt(true, true))
        assertFalse(BatteryOptimizationPolicy.shouldPrompt(false, false))
    }

    @Test
    fun foregroundRestartIsScheduledOnlyWhenBound() {
        assertTrue(ForegroundRestartPolicy.shouldSchedule(true))
        assertFalse(ForegroundRestartPolicy.shouldSchedule(false))
        assertEquals(15_000L, ForegroundRestartPolicy.DELAY_MILLIS)
    }
}
