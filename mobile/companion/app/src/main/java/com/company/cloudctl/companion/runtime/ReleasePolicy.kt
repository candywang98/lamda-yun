package com.company.cloudctl.companion.runtime

/**
 * P09-19 frozen release protocol (fleet-identity/v1@20260916.1 §8): a claim
 * may be released back to QUEUED only while it is still CLAIMED/PREFLIGHT —
 * the first task heartbeat has not been confirmed AND no committed
 * (irreversible) write has happened. Everything later belongs to the server
 * lease lifecycle (fail/reconcile), never to a client-side release.
 *
 * The fresh-claim seam (service/FreshClaimExecutionCoordinator.kt) runs
 * strictly before both gates, so its release path is legal by construction;
 * this policy pins the rule for any future caller of the release seam.
 */
object ReleasePolicy {
    fun canReleaseBackToQueue(
        firstHeartbeatConfirmed: Boolean,
        hasCommittedWrite: Boolean,
    ): Boolean = !firstHeartbeatConfirmed && !hasCommittedWrite
}
