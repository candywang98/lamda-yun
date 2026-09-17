package com.company.cloudctl.companion.control

import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.PinnedHttpsTransport
import org.json.JSONObject

/**
 * B17 seam over the three control-plane endpoints (contract §2). The HTTP
 * layer is injected so the sync engine is pure-JVM testable with a fake.
 */
interface ControlPlaneTransport {
    /** §2.1 GET /companion/v2/control?after=&limit= — throws [ControlCursorTooOldException] on 410. */
    fun fetchControlEvents(after: Long, limit: Int): ControlBatchResponse

    /** §2.2 GET /companion/v2/reconcile-snapshot. */
    fun fetchReconcileSnapshot(): ReconcileSnapshotResponse

    /** §4 POST /companion/v2/control/ack. */
    fun postControlAck(taskId: String, taskRevision: Long, result: String, reason: String?): JSONObject
}

/** Production transport on the pinned HTTPS stack; device-token auth, never claim-dependent. */
class PinnedControlPlaneTransport(private val connection: CloudConnection) : ControlPlaneTransport {
    private fun headers(): Map<String, String> = mapOf(
        "Accept" to "application/json",
        "Authorization" to "Bearer ${connection.bearerToken}",
    )

    override fun fetchControlEvents(after: Long, limit: Int): ControlBatchResponse {
        require(after >= 0) { "after must be >= 0" }
        require(limit in 1..50) { "limit must be within 1..50 (contract §2.1)" }
        val (status, body) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = "/companion/v2/control?after=$after&limit=$limit",
            pin = connection.certificateSha256,
            method = "GET",
            headers = headers(),
            body = ByteArray(0),
            connectTimeoutMs = 10_000,
            readTimeoutMs = 15_000,
        )
        ControlPlaneJson.parseCursorTooOld(status, body)?.let { throw it }
        if (status !in 200..299) throw ControlPlaneHttpException(status, body)
        return ControlPlaneJson.parseControlBatch(body)
    }

    override fun fetchReconcileSnapshot(): ReconcileSnapshotResponse {
        val (status, body) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = "/companion/v2/reconcile-snapshot",
            pin = connection.certificateSha256,
            method = "GET",
            headers = headers(),
            body = ByteArray(0),
            connectTimeoutMs = 10_000,
            readTimeoutMs = 15_000,
        )
        if (status !in 200..299) throw ControlPlaneHttpException(status, body)
        return ControlPlaneJson.parseReconcileSnapshot(body)
    }

    override fun postControlAck(taskId: String, taskRevision: Long, result: String, reason: String?): JSONObject {
        val payload = ControlPlaneJson.buildControlAckPayload(taskId, taskRevision, result, reason)
        val (status, body) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = "/companion/v2/control/ack",
            pin = connection.certificateSha256,
            method = "POST",
            headers = headers() + ("Content-Type" to "application/json; charset=utf-8"),
            body = payload.toString().toByteArray(Charsets.UTF_8),
            connectTimeoutMs = 10_000,
            readTimeoutMs = 15_000,
        )
        if (status !in 200..299) throw ControlPlaneHttpException(status, body)
        return if (body.isBlank()) JSONObject() else JSONObject(body)
    }
}
