package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.network.ClaimedTask
import com.company.cloudctl.companion.network.CloudHttpException
import org.json.JSONObject

internal const val TASK_CLAIM_ENDPOINT = "/companion/v2/tasks/claim"
internal const val MAINTENANCE_CLAIM_DETAIL = "device is in maintenance and cannot claim tasks"
private const val CONFLICT_PROBLEM_TYPE = "urn:cloudctl:problem:conflict"
private const val CONFLICT_PROBLEM_CODE = "CONFLICT"
private val PROBLEM_ENVELOPE_FIELDS = setOf(
    "type",
    "title",
    "status",
    "code",
    "detail",
    "correlation_id",
    "retryable",
    "fields",
)

internal sealed interface SyncClaimPassResult {
    data object MaintenanceDeferred : SyncClaimPassResult
    data object ClaimRejected : SyncClaimPassResult
    data class Completed(
        val claimed: ClaimedTask?,
        val executed: Boolean,
    ) : SyncClaimPassResult
}

internal fun isExactMaintenanceClaimDenial(
    endpoint: String,
    error: CloudHttpException,
): Boolean {
    if (endpoint != TASK_CLAIM_ENDPOINT || error.status != 409) return false
    val body = runCatching { JSONObject(error.responseBody) }.getOrNull() ?: return false
    val keys = body.keys().asSequence().toSet()
    if (keys == setOf("detail")) return body.opt("detail") == MAINTENANCE_CLAIM_DETAIL
    if (keys != PROBLEM_ENVELOPE_FIELDS) return false
    return body.opt("type") == CONFLICT_PROBLEM_TYPE &&
        body.opt("title") is String &&
        body.opt("status") == 409 &&
        body.opt("code") == CONFLICT_PROBLEM_CODE &&
        body.opt("detail") == MAINTENANCE_CLAIM_DETAIL &&
        body.opt("correlation_id") is String &&
        body.opt("retryable") == false &&
        body.optJSONObject("fields")?.length() == 0
}

/**
 * One production sync-loop claim pass. Maintenance deferral exits before any
 * local queue mutation or execution; every other HTTP failure is preserved.
 */
internal suspend fun runSyncClaimPass(
    claimRequest: (suspend () -> ClaimedTask?)?,
    acceptClaim: suspend (ClaimedTask) -> Boolean,
    executeLocal: suspend () -> Boolean,
    deferMaintenance: suspend () -> Unit,
): SyncClaimPassResult {
    val claimed = try {
        claimRequest?.invoke()
    } catch (error: CloudHttpException) {
        if (isExactMaintenanceClaimDenial(TASK_CLAIM_ENDPOINT, error)) {
            deferMaintenance()
            return SyncClaimPassResult.MaintenanceDeferred
        }
        throw error
    }
    if (claimed != null && !acceptClaim(claimed)) return SyncClaimPassResult.ClaimRejected
    return SyncClaimPassResult.Completed(claimed, executeLocal())
}
