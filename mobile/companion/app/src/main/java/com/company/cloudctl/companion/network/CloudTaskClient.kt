package com.company.cloudctl.companion.network

import org.json.JSONObject
import java.net.URI
import java.io.File
import com.company.cloudctl.companion.media.MediaManifest
import com.company.cloudctl.companion.media.MediaManifestParser

data class CloudConnection(val baseUrl: String, val bearerToken: String, val certificateSha256: String)
data class CloudBinaryResponse(val status: Int, val headers: Map<String, String>, val body: ByteArray)
data class ClaimedTask(val taskPayload: String, val taskId: String, val deviceId: String, val leaseId: String, val lastSequence: Int)
class CloudHttpException(val status: Int, val responseBody: String) : IllegalStateException(
    "Cloud request failed with HTTP $status",
) {
    val retryable: Boolean
        get() = status in setOf(408, 425, 429) || status >= 500

    val authenticationRejected: Boolean
        get() = status == 401 || status == 403
}

class CloudTaskClient(private val connection: CloudConnection) {
    init {
        val uri = URI(connection.baseUrl)
        require(uri.scheme == "https" && uri.host != null && uri.userInfo == null)
        require(Regex("^[a-f0-9]{64}$").matches(connection.certificateSha256))
    }

    fun requestTextPublish(
        description: String,
        price: String,
        autoPublish: Boolean = true,
        mediaAssetIds: List<String>? = null,
        deliveryId: String? = null
    ): JSONObject {
        val payload = JSONObject()
            .put("description", description)
            .put("price", price)
            .put("autoPublish", autoPublish)
        
        if (mediaAssetIds != null && mediaAssetIds.isNotEmpty()) {
            payload.put("mediaAssetIds", org.json.JSONArray(mediaAssetIds))
        }
        if (deliveryId != null) {
            payload.put("deliveryId", deliveryId)
        }
        
        return request("/companion/v2/tasks/publish-listing", payload) ?: JSONObject()
    }

    fun claim(): ClaimedTask? {
        val response = request("/companion/v2/tasks/claim", JSONObject().put("leaseSeconds", 60)) ?: return null
        val task = buildClaimedTaskPayload(response)
        return ClaimedTask(
            task.toString(), response.getString("taskId"), response.getString("deviceId"),
            response.getString("leaseId"), response.optInt("lastSequence", 0),
        )
    }

    fun heartbeat(taskId: String, leaseId: String, stepIndex: Int?) {
        request(
            "/companion/v2/tasks/$taskId/heartbeat",
            JSONObject().put("leaseId", leaseId).put("currentStep", stepIndex).put("leaseSeconds", 60),
        )
    }

    fun deviceHeartbeat(payload: JSONObject): JSONObject {
        return request("/companion/v2/devices/heartbeat", payload) ?: JSONObject()
    }

    fun uploadPreview(payload: JSONObject): JSONObject {
        return request("/companion/v2/devices/preview", payload) ?: JSONObject()
    }

    fun requestMediaManifest(deliveryId: String, assetIds: List<String>): MediaManifest {
        val response = request("/companion/v2/media/manifest", JSONObject()
            .put("deliveryId", deliveryId)
            .put("assetIds", org.json.JSONArray(assetIds))) ?: error("Empty media manifest")
        return MediaManifestParser.parse(response.toString())
    }

    fun downloadMedia(path: String, maxBytes: Long): CloudBinaryResponse {
        require(path.startsWith("/companion/v2/media/")) { "Invalid media download path" }
        val response = PinnedHttpsTransport.requestBytes(connection.baseUrl, path, connection.certificateSha256,
            "GET", mapOf("Accept" to "application/octet-stream", "Authorization" to "Bearer ${connection.bearerToken}"),
            null, 10_000, 35_000, maxBytes)
        if (response.body.size.toLong() > maxBytes) throw IllegalStateException("Media response exceeds limit")
        if (response.status !in 200..299) throw CloudHttpException(response.status, response.body.toString(Charsets.UTF_8))
        return CloudBinaryResponse(response.status, response.headers, response.body)
    }

    fun downloadMediaToFile(path: String, maxBytes: Long, outputFile: File): Map<String, String> {
        require(path.startsWith("/companion/v2/media/")) { "Invalid media download path" }
        val response = PinnedHttpsTransport.requestToFile(connection.baseUrl, path, connection.certificateSha256,
            "GET", mapOf("Accept" to "application/octet-stream", "Authorization" to "Bearer ${connection.bearerToken}"),
            null, 10_000, 35_000, maxBytes, outputFile)
        if (response.status !in 200..299) throw CloudHttpException(response.status, "")
        return response.headers
    }

    fun post(path: String, payload: String) {
        request(path, JSONObject(payload))
    }

    private fun request(path: String, body: JSONObject): JSONObject? {
        val payload = body.toString().toByteArray(Charsets.UTF_8)
        val (status, response) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = path,
            pin = connection.certificateSha256,
            method = "POST",
            headers = mapOf(
                "Accept" to "application/json",
                "Authorization" to "Bearer ${connection.bearerToken}",
                "Content-Type" to "application/json; charset=utf-8",
            ),
            body = payload,
            connectTimeoutMs = 10_000,
            readTimeoutMs = 35_000,
        )
        if (status == 204) return null
        if (status !in 200..299) throw CloudHttpException(status, response)
        return if (response.isBlank()) JSONObject() else JSONObject(response)
    }
}

internal fun buildClaimedTaskPayload(response: JSONObject): JSONObject = JSONObject()
    .put("protocolVersion", response.getString("protocolVersion"))
    .put("taskId", response.getString("taskId"))
    .put("deviceId", response.getString("deviceId"))
    .put("targetPackage", response.getString("targetPackage"))
    .put("issuedAt", response.getString("issuedAt"))
    .put("expiresAt", response.getString("expiresAt"))
    .put("maxRunSeconds", response.getInt("maxRunSeconds"))
    .put("steps", response.getJSONArray("steps"))
    .also { task -> response.optJSONObject("mediaDelivery")?.let { task.put("mediaDelivery", JSONObject(it.toString())) } }
