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

data class ResumeCommand(
    val taskId: String,
    val leaseId: String,
    val controlEpoch: Int?,
    val pageVerified: Boolean,
    val reason: String?,
) {
    companion object {
        fun fromHeartbeat(response: JSONObject): ResumeCommand? {
            if (response.isNull("resume")) return null
            val resume = response.optJSONObject("resume") ?: return null
            val taskId = resume.optString("taskId")
            val leaseId = resume.optString("leaseId")
            if (taskId.isBlank() || leaseId.isBlank()) return null
            return ResumeCommand(
                taskId = taskId,
                leaseId = leaseId,
                controlEpoch = if (resume.has("controlEpoch") && !resume.isNull("controlEpoch")) {
                    resume.optInt("controlEpoch")
                } else {
                    null
                },
                pageVerified = resume.optBoolean("pageVerified", false),
                reason = resume.optString("reason").takeIf { it.isNotBlank() },
            )
        }
    }
}
