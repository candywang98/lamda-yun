package com.company.cloudctl.companion.network

import org.json.JSONObject

data class PreviewGrant(
    val sessionId: String,
    val expiresAt: String,
    val captureIntervalMs: Long,
) {
    companion object {
        fun fromHeartbeat(response: JSONObject): PreviewGrant? {
            if (response.isNull("preview")) return null
            val preview = response.optJSONObject("preview") ?: return null
            val sessionId = preview.optString("sessionId")
            if (sessionId.length != 36) return null
            return PreviewGrant(
                sessionId = sessionId,
                expiresAt = preview.optString("expiresAt"),
                captureIntervalMs = preview.optLong("captureIntervalMs", 2_000L).coerceIn(1_000L, 10_000L),
            )
        }
    }
}

data class PreviewFrame(val jpeg: ByteArray, val width: Int, val height: Int)
