package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.im.ImMonitor
import com.company.cloudctl.companion.im.ImMonitorConfig
import java.io.File
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Calls the actual diagnostic-variant entrypoints; no socket or business request is sent. */
class HeartbeatDiagnosticTransportTest {
    @Test
    fun variantUsesOriginalPackageAndDiagnosticGate() {
        assertTrue(BuildConfig.HEARTBEAT_DIAGNOSTIC)
        assertFalse(BuildConfig.IM_UPLOAD_HOLD_ALLOWED)
        assertEquals("com.company.cloudctl.companion", BuildConfig.APPLICATION_ID)
    }

    @Test
    fun businessRoutesAreRejectedBeforeEndpointParsing() {
        listOf(
            "/companion/v2/tasks/claim",
            "/companion/v2/tasks/task-1/events",
            "/companion/v2/im/events",
            "/companion/v2/devices/bind",
            "/companion/v2/devices/unbind",
            "/companion/v2/apk-updates/report-installed",
        ).forEach { path ->
            val failure = assertFailsWith<IllegalStateException> {
                request("POST", path)
            }
            assertEquals("Heartbeat diagnostic build blocks non-heartbeat requests", failure.message)
        }
    }

    @Test
    fun heartbeatWhitelistRejectsMethodAndPathVariants() {
        listOf(
            "GET" to "/companion/v2/devices/heartbeat",
            "DELETE" to "/companion/v2/devices/heartbeat",
            "POST" to "/companion/v2/devices/heartbeat/",
            "POST" to "/companion/v2/devices/heartbeat?other=1",
        ).forEach { (method, path) ->
            assertFailsWith<IllegalStateException> { request(method, path) }
        }
    }

    @Test
    fun exactHeartbeatPassesPolicyButStillRequiresHttps() {
        // Invalid endpoint deliberately stops at URI validation, before socket creation.
        assertFailsWith<IllegalArgumentException> {
            request("POST", "/companion/v2/devices/heartbeat")
        }
    }

    @Test
    fun fileTransferIsRejectedBeforeFileCreation() {
        val output = File(System.getProperty("java.io.tmpdir"), "diagnostic-blocked-${UUID.randomUUID()}.bin")
        val failure = assertFailsWith<IllegalStateException> {
            PinnedHttpsTransport.requestToFile(
                baseUrl = "invalid-endpoint",
                path = "/companion/v2/devices/heartbeat",
                pin = "",
                method = "POST",
                headers = emptyMap(),
                body = null,
                connectTimeoutMs = 1,
                readTimeoutMs = 1,
                maxBodyBytes = 1,
                outputFile = output,
            )
        }
        assertEquals("Heartbeat diagnostic build blocks file transfers", failure.message)
        assertFalse(output.exists())
    }

    @Test
    fun diagnosticDisablesEveryMonitoredPackageEvenWhenConfiguredOn() {
        try {
            ImMonitor.applyConfig(ImMonitorConfig(enabled = true, platforms = setOf("xianyu", "xhs", "douyin", "wechat")))
            listOf("com.taobao.idlefish", "com.xingin.xhs", "com.ss.android.ugc.aweme", "com.tencent.mm").forEach {
                assertFalse(ImMonitor.isPackageEnabled(it))
            }
        } finally {
            ImMonitor.applyConfig(ImMonitorConfig())
        }
    }

    private fun request(method: String, path: String) = PinnedHttpsTransport.request(
        baseUrl = "invalid-endpoint",
        path = path,
        pin = "",
        method = method,
        headers = emptyMap(),
        body = null,
        connectTimeoutMs = 1,
        readTimeoutMs = 1,
    )
}
