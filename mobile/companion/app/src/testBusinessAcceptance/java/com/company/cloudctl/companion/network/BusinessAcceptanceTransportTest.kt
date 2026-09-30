package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.im.ImMonitor
import com.company.cloudctl.companion.im.ImMonitorConfig
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Exercises the business-variant entrypoints without sending a network request. */
class BusinessAcceptanceTransportTest {
    @Test
    fun keepsOriginalIdentityWithoutDiagnosticOrHoldSwitches() {
        assertEquals("com.company.cloudctl.companion", BuildConfig.APPLICATION_ID)
        assertEquals(9, BuildConfig.VERSION_CODE)
        assertFalse(BuildConfig.DEBUG)
        assertFalse(BuildConfig.HEARTBEAT_DIAGNOSTIC)
        assertFalse(BuildConfig.IM_UPLOAD_HOLD_ALLOWED)
        assertEquals("{}", BuildConfig.RECIPE_SIGNING_PUBLIC_KEYS)
        assertTrue(BuildConfig.VERSION_NAME.endsWith("-business-acceptance.9"))
    }

    @Test
    fun businessRequestsReachHttpsValidationRatherThanDiagnosticTransport() {
        listOf(
            "/companion/v2/tasks/claim",
            "/companion/v2/devices/heartbeat",
            "/companion/v2/im/events",
        ).forEach { path ->
            assertFailsWith<IllegalArgumentException> {
                PinnedHttpsTransport.request(
                    baseUrl = "invalid-endpoint",
                    path = path,
                    pin = "",
                    method = "POST",
                    headers = emptyMap(),
                    body = null,
                    connectTimeoutMs = 1,
                    readTimeoutMs = 1,
                )
            }
        }
    }

    @Test
    fun configuredInboundCollectionIsNotDisabledByDiagnosticPolicy() {
        try {
            ImMonitor.applyConfig(ImMonitorConfig(enabled = true, platforms = setOf("xianyu")))
            assertTrue(ImMonitor.isPackageEnabled("com.taobao.idlefish"))
            assertFalse(ImMonitor.isPackageEnabled("com.xingin.xhs"))
        } finally {
            ImMonitor.applyConfig(ImMonitorConfig())
        }
    }
}
