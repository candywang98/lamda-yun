package com.company.cloudctl.companion.network

/** Defense in depth for the explicitly authorized, in-place heartbeat diagnostic build. */
internal object HeartbeatDiagnosticPolicy {
    fun permitsRequest(enabled: Boolean, method: String, path: String): Boolean =
        !enabled || (method == "POST" && path == "/companion/v2/devices/heartbeat")
}
