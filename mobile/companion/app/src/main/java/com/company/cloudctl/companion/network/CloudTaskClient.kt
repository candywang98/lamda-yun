package com.company.cloudctl.companion.network

import org.json.JSONObject
import java.net.URI
import java.io.File
import com.company.cloudctl.companion.media.MediaManifest
import com.company.cloudctl.companion.media.MediaManifestParser

data class CloudConnection(val baseUrl: String, val bearerToken: String, val certificateSha256: String)
data class CloudBinaryResponse(val status: Int, val headers: Map<String, String>, val body: ByteArray)
data class ClaimedTask(val taskPayload: String, val taskId: String, val deviceId: String, val leaseId: String, val lastSequence: Int)
data class TaskHeartbeat(
    val businessState: String? = null,
    val controlMode: String? = null,
    val stallReason: String? = null,
    val status: String? = null,
    val currentStep: Int? = null,
)
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

    fun heartbeat(taskId: String, leaseId: String, stepIndex: Int?): TaskHeartbeat {
        val response = request(
            "/companion/v2/tasks/$taskId/heartbeat",
            JSONObject().put("leaseId", leaseId).put("currentStep", stepIndex).put("leaseSeconds", 60),
        ) ?: JSONObject()
        return parseTaskHeartbeat(response)
    }

    fun deviceHeartbeat(payload: JSONObject): JSONObject {
        return request("/companion/v2/devices/heartbeat", payload) ?: JSONObject()
    }

    /** pa-im slice 2: device-scoped monitor configuration (GET). */
    fun fetchImConfig(): JSONObject? {
        val (status, response) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = "/companion/v2/im/config",
            pin = connection.certificateSha256,
            method = "GET",
            headers = mapOf(
                "Accept" to "application/json",
                "Authorization" to "Bearer ${connection.bearerToken}",
            ),
            body = ByteArray(0),
            connectTimeoutMs = 10_000,
            readTimeoutMs = 15_000,
        )
        if (status !in 200..299) return null
        val raw = JSONObject(response)
        return if (raw.has("platforms")) raw else null
    }

    /** pa-im/20260913.1: batch push of monitored IM notifications. */
    fun sendImMessages(payload: JSONObject): JSONObject {
        return request("/companion/v2/im/messages", payload) ?: JSONObject()
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

    fun listActiveRecipes(): JSONObject {
        val (status, response) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = "/companion/v2/recipes/active",
            pin = connection.certificateSha256,
            method = "GET",
            headers = mapOf(
                "Accept" to "application/json",
                "Authorization" to "Bearer ${connection.bearerToken}",
            ),
            body = null,
            connectTimeoutMs = 10_000,
            readTimeoutMs = 35_000,
        )
        if (status !in 200..299) throw CloudHttpException(status, response)
        return if (response.isBlank()) JSONObject() else JSONObject(response)
    }

    fun downloadRecipe(versionId: String, maxBytes: Long = 256 * 1024L): CloudBinaryResponse {
        require(Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$").matches(versionId)) { "Invalid recipe versionId" }
        val response = PinnedHttpsTransport.requestBytes(
            connection.baseUrl,
            "/companion/v2/recipes/$versionId",
            connection.certificateSha256,
            "GET",
            mapOf("Accept" to "application/json", "Authorization" to "Bearer ${connection.bearerToken}"),
            null,
            10_000,
            35_000,
            maxBytes,
        )
        if (response.body.size.toLong() > maxBytes) throw IllegalStateException("Recipe response exceeds limit")
        if (response.status !in 200..299) throw CloudHttpException(response.status, response.body.toString(Charsets.UTF_8))
        return CloudBinaryResponse(response.status, response.headers, response.body)
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

internal fun buildClaimedTaskPayload(response: JSONObject): JSONObject {
    val protocol = response.getString("protocolVersion")
    val command = response.optJSONObject("command")
    val legacySteps = command?.optBoolean("legacyStepsEnabled", false) == true
    val task = JSONObject()
        .put("protocolVersion", protocol)
        .put("taskId", response.getString("taskId"))
        .put("deviceId", response.getString("deviceId"))
        .put("targetPackage", response.getString("targetPackage"))
    command?.let { task.put("command", JSONObject(it.toString())) }
    optionalNonBlank(response, "commandType")?.let { task.put("commandType", it) }
    optionalNonBlank(response, "accountId")?.let { task.put("accountId", it) }
    if (response.has("bindingVersion") && !response.isNull("bindingVersion")) {
        task.put("bindingVersion", response.getInt("bindingVersion"))
    }
    optionalNonBlank(response, "attemptId")?.let { task.put("attemptId", it) }
    response.optJSONObject("mediaDelivery")?.let { task.put("mediaDelivery", JSONObject(it.toString())) }
    if (protocol == "cloudctl.mobile/v1" || legacySteps) {
        task.put("issuedAt", response.getString("issuedAt"))
        task.put("expiresAt", response.getString("expiresAt"))
        task.put("maxRunSeconds", response.getInt("maxRunSeconds"))
        task.put("steps", response.getJSONArray("steps"))
    } else {
        if (response.has("issuedAt")) task.put("issuedAt", response.getString("issuedAt"))
        if (response.has("expiresAt")) task.put("expiresAt", response.getString("expiresAt"))
        if (response.has("maxRunSeconds")) task.put("maxRunSeconds", response.getInt("maxRunSeconds"))
        command?.optJSONObject("recipe")?.optString("sha256")?.takeIf { it.isNotBlank() }?.let {
            task.put("recipeHash", it)
        }
    }
    return task
}

internal fun optionalNonBlank(value: JSONObject, key: String): String? {
    if (!value.has(key) || value.isNull(key)) return null
    return (value.opt(key) as? String)?.takeIf { it.isNotBlank() }
}

internal fun parseTaskHeartbeat(response: JSONObject): TaskHeartbeat = TaskHeartbeat(
    businessState = response.optString("businessState").takeIf { it.isNotBlank() },
    controlMode = response.optString("controlMode").takeIf { it.isNotBlank() },
    stallReason = response.optString("stallReason").takeIf { it.isNotBlank() },
    status = response.optString("status").takeIf { it.isNotBlank() },
    currentStep = if (response.has("currentStep") && !response.isNull("currentStep")) {
        response.optInt("currentStep")
    } else {
        null
    },
)
