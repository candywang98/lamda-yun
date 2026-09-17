package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import com.company.cloudctl.companion.updates.ApkDownloadReportResult
import com.company.cloudctl.companion.updates.ApkInstallCandidate
import com.company.cloudctl.companion.updates.ApkInstallReceipt
import com.company.cloudctl.companion.updates.ApkReleaseClient
import com.company.cloudctl.companion.updates.ArtifactTooLargeException
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.io.File
import java.io.IOException
import java.io.OutputStream
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

class CloudTaskClient(private val connection: CloudConnection) : ApkReleaseClient {
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

    fun release(taskId: String, leaseId: String, reason: String) {
        val release = buildTaskReleaseRequest(taskId, leaseId, reason)
        request(release.path, release.body)
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

    /**
     * order-sync/20260915.1 §3: idempotent batch order upload. A 201/200 body
     * carries {"accepted": n, "duplicates": m} (see [parseOrdersBatchResponse]);
     * per-row validation failures surface as CloudHttpException(422, detail).
     * Build the body with [buildOrdersBatchPayload]; the batch is 1..20 rows.
     */
    fun sendOrders(payload: JSONObject): JSONObject {
        return request("/companion/v2/orders/batch", payload) ?: JSONObject()
    }

    /**
     * O10 (fleet-first-20260916.1) per-screen page push: run/account-bound
     * page summary + rows. A 201/200 body carries
     * {"accepted","updated","duplicates","screen","replayed","checkpoint"};
     * binding violations (account/version/run/screen-gap) surface as
     * CloudHttpException(409, detail). Build the body with
     * [buildOrdersScreenPayload].
     */
    fun sendOrdersScreen(payload: JSONObject): JSONObject {
        return request("/companion/v2/orders/screens", payload) ?: JSONObject()
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

    // -- apk-release/v1 (U10 server / U11 device model, WIRE2 wiring) --------

    /** GET /companion/v2/apk/candidates -> this device's install candidates. */
    override fun listCandidates(): List<ApkInstallCandidate> {
        val (status, response) = PinnedHttpsTransport.request(
            baseUrl = connection.baseUrl,
            path = buildApkCandidateListCall().path,
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
        return ApkInstallCandidate.listFrom(response)
    }

    /**
     * Streams the APK bytes from the candidate's `sourceRef` (an absolute
     * https URL) into [sink]. Transport truncations surface as retryable
     * [IOException]s; a body above [maxBytes] surfaces as the coordinator's
     * deterministic [ArtifactTooLargeException].
     */
    override fun downloadApk(candidate: ApkInstallCandidate, sink: OutputStream, maxBytes: Long): Long {
        val (base, path) = splitApkSourceRef(candidate.sourceRef)
        val response = try {
            PinnedHttpsTransport.requestBytes(
                base,
                path,
                connection.certificateSha256,
                "GET",
                mapOf(
                    "Accept" to "application/octet-stream",
                    "Authorization" to "Bearer ${connection.bearerToken}",
                ),
                null,
                10_000,
                60_000,
                maxBytes,
            )
        } catch (error: IllegalArgumentException) {
            throw mapApkTransferLimit(error, maxBytes)
        } catch (error: IllegalStateException) {
            throw mapApkTransferLimit(error, maxBytes)
        }
        if (response.status !in 200..299) {
            // A failing artifact source is a transient download interruption
            // from the coordinator's point of view: the candidate stays eligible.
            throw IOException("apk artifact download failed with HTTP ${response.status}")
        }
        sink.write(response.body)
        return response.body.size.toLong()
    }

    /** POST .../{candidateId}:report-downloaded with the locally verified digest. */
    override fun reportDownloaded(candidateId: String, sha256: String): ApkDownloadReportResult {
        val call = buildApkReportDownloadedCall(candidateId, sha256)
        return try {
            request(call.path, call.body!!)
            ApkDownloadReportResult.Accepted
        } catch (error: CloudHttpException) {
            parseApkDownloadReport(error.status, error.responseBody)
        }
    }

    /**
     * POST .../{candidateId}:report-installed with [receipt]'s wire payload.
     * True = stop retrying: the server accepted the receipt (2xx) or proved it
     * can never accept it (404 — candidate unknown for this binding). False
     * keeps the receipt in the ledger for the next drain.
     */
    override fun reportInstallReceipt(receipt: ApkInstallReceipt): Boolean {
        val call = buildApkReportInstalledCall(receipt)
        return try {
            request(call.path, call.body!!)
            true
        } catch (error: CloudHttpException) {
            parseApkInstallReceiptDelivery(error.status)
        }
    }

    private fun mapApkTransferLimit(error: RuntimeException, maxBytes: Long): RuntimeException =
        if (error.message?.contains("exceeds limit") == true) ArtifactTooLargeException(maxBytes) else error

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

internal data class TaskReleaseRequest(val path: String, val body: JSONObject)

/** Request shape of one apk-release/v1 companion call (WIRE2 golden-test seam). */
internal data class ApkEndpointCall(val method: String, val path: String, val body: JSONObject?)

/** GET /companion/v2/apk/candidates (apk-release/v1 companion surface). */
internal fun buildApkCandidateListCall(): ApkEndpointCall =
    ApkEndpointCall("GET", "/companion/v2/apk/candidates", null)

/**
 * POST /companion/v2/apk/candidates/{candidateId}:report-downloaded with the
 * frozen `ApkDownloadedReport` body (services/control-api/.../apk_releases.py):
 * exactly `{"sha256": "<64 lowercase hex>"}` — nothing else may join.
 */
internal fun buildApkReportDownloadedCall(candidateId: String, sha256: String): ApkEndpointCall {
    require(candidateId.isNotBlank()) { "candidateId must not be blank" }
    require(Regex("^[0-9a-f]{64}$").matches(sha256)) { "Invalid apk sha256" }
    return ApkEndpointCall(
        "POST",
        "/companion/v2/apk/candidates/$candidateId:report-downloaded",
        JSONObject().put("sha256", sha256),
    )
}

/**
 * POST /companion/v2/apk/candidates/{candidateId}:report-installed with the
 * `ApkInstallReceiptReport` body: exactly ApkInstallReceipt.toWireJson()
 * (candidateId/releaseId/packageName/attemptedVersionCode/outcome/
 * installedVersionCode/signatureMatched/message/completedAt — the local-only
 * `delivered` flag must never reach the wire).
 */
internal fun buildApkReportInstalledCall(receipt: ApkInstallReceipt): ApkEndpointCall {
    require(receipt.candidateId.isNotBlank()) { "candidateId must not be blank" }
    return ApkEndpointCall(
        "POST",
        "/companion/v2/apk/candidates/${receipt.candidateId}:report-installed",
        receipt.toWireJson(),
    )
}

/**
 * Splits an apk candidate `sourceRef` into the (baseUrl, requestPath) pair the
 * pinned transport expects. Only absolute https URLs are fetchable; anything
 * else (s3:// etc.) fails closed before a socket is opened.
 */
internal fun splitApkSourceRef(sourceRef: String): Pair<String, String> {
    val uri = URI(sourceRef)
    require(uri.scheme == "https" && uri.host != null && uri.userInfo == null) {
        "apk sourceRef must be an absolute https URL"
    }
    val base = "${uri.scheme}://${uri.authority}"
    val path = (uri.rawPath?.takeIf { it.isNotBlank() } ?: "/") +
        (uri.rawQuery?.let { "?$it" } ?: "")
    return base to path
}

/** Maps a report-downloaded HTTP verdict onto the U11 result type. */
internal fun parseApkDownloadReport(status: Int, body: String): ApkDownloadReportResult {
    val problem = runCatching { JSONObject(body) }.getOrNull()
    return when {
        status in 200..299 -> ApkDownloadReportResult.Accepted
        status == 422 && problem?.optString("code") == "APK_DOWNLOAD_HASH_MISMATCH" ->
            ApkDownloadReportResult.HashMismatch(problem.optString("detail"))
        else -> ApkDownloadReportResult.Error(status, body.take(500))
    }
}

/**
 * Receipt delivery verdict: 2xx accepted; 404 means the server proved this
 * binding owns no such candidate, so the receipt can never be accepted and is
 * dropped instead of retried forever; anything else stays retryable.
 */
internal fun parseApkInstallReceiptDelivery(status: Int): Boolean = when {
    status in 200..299 -> true
    status == 404 -> true
    else -> false
}

/** Collection-protocol version of the O10 screens push; the checkpoint binds it (mismatch => new run). */
internal const val ORDER_SCREENS_SCHEMA_VERSION = 1

/**
 * O10 (fleet-first-20260916.1) request body for POST /companion/v2/orders/screens.
 * The field set is FROZEN against the backend request model
 * services/control-api/src/cloudctl_api/fleet_orders.py::FleetOrderScreenIn
 * (extra="forbid"): runKey/accountKey/schemaVersion/screen/direction/rows/
 * partialRows/collectedAt — nothing else may join. Row items mirror the
 * slice1 /orders/batch row shape (OrderIn) exactly. Unlike the batch, an
 * empty rows list is legal: it records an empty page (empty_page flag).
 */
internal fun buildOrdersScreenPayload(
    runKey: String,
    accountKey: String,
    schemaVersion: Int,
    direction: OrderDirection,
    screen: Int,
    rows: List<OrderRowSnapshot>,
    partialRowIndices: List<Int>,
    collectedAt: String,
): JSONObject {
    require(runKey.isNotBlank()) { "runKey must not be blank" }
    require(accountKey.isNotBlank()) { "accountKey must not be blank" }
    require(schemaVersion in 1..99) { "schemaVersion is outside the backend range" }
    require(screen in 1..50) { "screen is outside the backend range" }
    require(rows.size <= 20) { "screen rows exceed the backend batch limit" }
    require(partialRowIndices.size <= 50) { "partialRows exceed the backend limit" }
    val items = JSONArray()
    rows.forEach { row ->
        val item = JSONObject()
            .put("direction", row.direction.name)
            .put("order_key", row.orderKey.trim().take(128))
        row.itemTitle?.trim()?.takeIf { it.isNotBlank() }?.let { item.put("item_title", it.take(512)) }
        row.buyerName?.trim()?.takeIf { it.isNotBlank() }?.let { item.put("buyer_name", it.take(128)) }
        row.amountCents?.takeIf { it > 0 }?.let { item.put("amount_cents", it) }
        row.statusText?.trim()?.takeIf { it.isNotBlank() }?.let { item.put("status_text", it.take(64)) }
        row.occurredAt?.takeIf { it.isNotBlank() }?.let { item.put("occurred_at", it) }
        if (row.rawLines.isNotEmpty()) item.put("raw", JSONObject().put("lines", JSONArray(row.rawLines)))
        items.put(item)
    }
    return JSONObject()
        .put("runKey", runKey.take(128))
        .put("accountKey", accountKey.take(128))
        .put("schemaVersion", schemaVersion)
        .put("screen", screen)
        .put("direction", direction.name)
        .put("rows", items)
        .put("partialRows", JSONArray(partialRowIndices))
        .put("collectedAt", collectedAt.take(64))
}

internal fun buildTaskReleaseRequest(taskId: String, leaseId: String, reason: String): TaskReleaseRequest {
    require(taskId.isNotBlank()) { "taskId must not be blank" }
    require(leaseId.isNotBlank()) { "leaseId must not be blank" }
    require(reason in setOf("ACCESSIBILITY_NOT_ENABLED", "ACCESSIBILITY_NOT_ACTIVE")) {
        "Unsupported task release reason"
    }
    return TaskReleaseRequest(
        path = "/companion/v2/tasks/$taskId/release",
        body = JSONObject().put("leaseId", leaseId).put("reason", reason),
    )
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
