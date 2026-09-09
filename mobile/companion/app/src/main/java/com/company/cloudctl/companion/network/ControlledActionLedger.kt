package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.automation.ControlledActionIdentity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URI

/** Responses are observations until resolutionRevision > 0. */
enum class ActionCommitStatus { INTENT, APPLIED, UNKNOWN, NOT_SUBMITTED }
enum class ActionIntentDecision { AUTHORIZED, RECONCILE_REQUIRED }
data class ActionIntentRequest(
    val leaseId: String, val actionId: String, val actionKey: String,
    val parameterHash: String, val beforeEvidence: String,
)
data class ActionOutcomeRequest(
    val leaseId: String, val parameterHash: String, val status: ActionCommitStatus, val evidence: String?,
) {
    init {
        require(status == ActionCommitStatus.APPLIED || status == ActionCommitStatus.UNKNOWN)
        requireEvidence(evidence)
    }
}
data class ActionIntentResponse(val httpStatus: Int, val decision: ActionIntentDecision, val action: ActionCommit)
data class ActionCommit(
    val actionKey: String, val taskId: String, val deviceId: String, val accountId: String,
    val bindingVersion: Int, val recipeVersionId: String, val recipeSha256: String,
    val snapshotSha256: String, val actionId: String, val parameterHash: String,
    val status: ActionCommitStatus, val beforeEvidence: String, val reportedEvidence: String?,
    val resolutionRevision: Long, val resolutionEvidence: String?, val resolvedAt: String?,
    val createdAt: String, val updatedAt: String,
) {
    fun matches(identity: ControlledActionIdentity): Boolean =
        actionKey == identity.actionKey && parameterHash == identity.parameterHash && taskId == identity.taskId &&
            deviceId == identity.deviceId && accountId == identity.accountId && bindingVersion == identity.bindingVersion &&
            recipeVersionId == identity.recipeVersionId && recipeSha256 == identity.recipeSha256 &&
            snapshotSha256 == identity.snapshotSha256 && actionId == identity.actionId

    companion object {
        fun fromJson(json: JSONObject) = ActionCommit(
            json.getString("actionKey"), json.getString("taskId"), json.getString("deviceId"),
            json.getString("accountId"), json.getInt("bindingVersion"), json.getString("recipeVersionId"),
            json.getString("recipeSha256"), json.getString("snapshotSha256"), json.getString("actionId"),
            json.getString("parameterHash"), ActionCommitStatus.valueOf(json.getString("status")),
            json.getString("beforeEvidence"), json.nullableString("reportedEvidence"),
            json.getLong("resolutionRevision"), json.nullableString("resolutionEvidence"),
            json.nullableString("resolvedAt"), json.getString("createdAt"), json.getString("updatedAt"),
        )
    }
}

/** Implementations must authenticate the enrolled device binding; no retry may create a fresh grant. */
interface ControlledActionLedger {
    suspend fun intent(taskId: String, request: ActionIntentRequest): ActionIntentResponse
    suspend fun outcome(taskId: String, actionKey: String, request: ActionOutcomeRequest): ActionCommit
    suspend fun get(taskId: String, actionKey: String): ActionCommit
}

class PinnedControlledActionLedger(private val connection: CloudConnection) : ControlledActionLedger {
    init {
        val uri = URI(connection.baseUrl)
        require(uri.scheme == "https" && uri.host != null && uri.userInfo == null && uri.query == null && uri.fragment == null)
        require(Regex("[a-f0-9]{64}").matches(connection.certificateSha256))
        require(connection.bearerToken.isNotBlank() && !connection.bearerToken.contains('\r') && !connection.bearerToken.contains('\n'))
    }

    override suspend fun intent(taskId: String, request: ActionIntentRequest): ActionIntentResponse {
        requireEvidence(request.beforeEvidence)
        val (status, json) = request("${taskPath(taskId)}/actions/intent", JSONObject()
            .put("leaseId", request.leaseId).put("actionId", request.actionId)
            .put("actionKey", request.actionKey).put("parameterHash", request.parameterHash)
            .put("beforeEvidence", request.beforeEvidence))
        return ActionIntentResponse(status, ActionIntentDecision.valueOf(json.getString("decision")),
            ActionCommit.fromJson(json.getJSONObject("action")))
    }

    override suspend fun outcome(taskId: String, actionKey: String, request: ActionOutcomeRequest): ActionCommit =
        ActionCommit.fromJson(request("${actionPath(taskId, actionKey)}/outcome", JSONObject()
            .put("leaseId", request.leaseId).put("parameterHash", request.parameterHash)
            .put("status", request.status.name).put("evidence", request.evidence ?: JSONObject.NULL)).second)

    override suspend fun get(taskId: String, actionKey: String): ActionCommit =
        ActionCommit.fromJson(request(actionPath(taskId, actionKey), null).second)

    private suspend fun request(path: String, body: JSONObject?): Pair<Int, JSONObject> = withContext(Dispatchers.IO) {
        ensureActive()
        val (status, response) = PinnedHttpsTransport.request(
            connection.baseUrl, path, connection.certificateSha256, if (body == null) "GET" else "POST",
            mapOf("Accept" to "application/json", "Authorization" to "Bearer ${connection.bearerToken}",
                "Content-Type" to "application/json; charset=utf-8"),
            body?.toString()?.toByteArray(Charsets.UTF_8), 10_000, 35_000,
        )
        ensureActive()
        // Never attach response bodies or binding credentials to failures.
        if (status !in 200..299) throw CloudHttpException(status, "")
        status to JSONObject(response)
    }

    private fun taskPath(taskId: String): String {
        require(Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}").matches(taskId))
        return "/companion/v2/tasks/$taskId"
    }
    private fun actionPath(taskId: String, actionKey: String): String {
        require(Regex("[a-f0-9]{64}").matches(actionKey))
        return "${taskPath(taskId)}/actions/$actionKey"
    }
}

internal fun requireEvidence(value: String?) {
    require(value != null && value.isNotBlank() && value.length <= 500 && !value.contains('\n') && !value.contains('\r')) {
        "Invalid evidence reference"
    }
}
private fun JSONObject.nullableString(key: String): String? = if (isNull(key)) null else getString(key)
