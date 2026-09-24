package com.company.cloudctl.companion.im

import org.json.JSONObject
import java.time.Instant

/**
 * One durable inbound row. [text] is already canonical. [deviceId] is stored
 * only so the local SHA-256 can be checked and so a row captured before a
 * binding existed can be sealed to that binding later. It is never written
 * into the upload JSON.
 */
data class ImInboundEvent(
    val id: Long,
    val dedupeKey: String,
    val deviceId: String,
    val platform: String,
    val peerKey: String,
    val peerName: String,
    val text: String,
    val occurredAt: Instant,
    val attemptCount: Int,
    val nextAttemptAt: Instant,
    val lastError: String?,
    val permanentFailureAt: Instant?,
    val confirmedAt: Instant?,
) {
    val pending: Boolean get() = confirmedAt == null && permanentFailureAt == null

    fun toUploadJson(): JSONObject = JSONObject()
        .put("platform", platform)
        .put("peerKey", peerKey)
        .put("peerName", peerName)
        .put("text", text)
        .put("occurredAt", occurredAt.toString())
}

enum class ImEnqueueResult {
    ENQUEUED,
    DUPLICATE,
    REJECTED,
    OVERFLOW,
}

data class ImEnqueueOutcome(
    val result: ImEnqueueResult,
    val dedupeKey: String?,
    val event: ImInboundEvent? = null,
)
