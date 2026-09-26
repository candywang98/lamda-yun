package com.company.cloudctl.companion.network

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HeartbeatDiagnosticPolicyTest {
    @Test fun `diagnostic allows only the exact heartbeat post`() {
        assertTrue(HeartbeatDiagnosticPolicy.permitsRequest(true, "POST", "/companion/v2/devices/heartbeat"))
        listOf(
            "GET" to "/companion/v2/devices/heartbeat",
            "POST" to "/companion/v2/tasks/claim",
            "POST" to "/companion/v2/im/messages",
            "GET" to "/companion/v2/live/session",
            "GET" to "/companion/v2/apk/candidates",
            "GET" to "/companion/v2/recipes/active",
            "POST" to "/companion/v2/devices/heartbeat?preview=true",
            "POST" to "/companion/v2/devices/heartbeat/../tasks/claim",
        ).forEach { (method, path) ->
            assertFalse(HeartbeatDiagnosticPolicy.permitsRequest(true, method, path), "$method $path")
        }
    }

    @Test fun `normal builds retain existing transport routes`() {
        assertTrue(HeartbeatDiagnosticPolicy.permitsRequest(false, "POST", "/companion/v2/tasks/claim"))
        assertTrue(HeartbeatDiagnosticPolicy.permitsRequest(false, "GET", "/companion/v2/recipes/active"))
    }
}
