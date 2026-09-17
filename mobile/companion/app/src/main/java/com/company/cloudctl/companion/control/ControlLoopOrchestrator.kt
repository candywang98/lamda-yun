package com.company.cloudctl.companion.control

import com.company.cloudctl.companion.data.PausedHeadInfo

/**
 * B17 ordering seam for the sync loop (contract §0 invariant):
 *
 *   heartbeat watermark (§2.3, presence loop feeds [ControlSyncClient])
 *   → control sync — UNGATED, runs before and regardless of every barrier
 *   → mirror convergence (inside the same transactional apply)
 *   → SUSPECT_ORPHANED barrier evaluation (§3.3: alert, never local unblock)
 *   → the pre-existing claim gates stay intact.
 *
 * Work acquisition (claim) may be gated by local execution state and
 * accessibility readiness; control-plane synchronization may not. This class
 * exists so that property is unit-testable without an Android Service.
 */
class ControlLoopOrchestrator(
    private val syncClient: ControlSyncClient,
    private val state: ControlStateStore,
    private val pausedHead: () -> PausedHeadInfo?,
    private val suspectPolicy: SuspectOrphanedPolicy,
    private val onSuspectOrphaned: (SuspectOrphanedPolicy.Signal) -> Unit = {},
) {
    data class PreClaimPass(
        val controlSyncOutcome: ControlSyncClient.ControlSyncOutcome,
        val suspect: SuspectOrphanedPolicy.Signal?,
        /** §3.3: while SUSPECT_ORPHANED is active no new destructive task may be claimed. */
        val claimPermitted: Boolean,
    )

    /**
     * Runs once per sync-loop iteration BEFORE the claim gate. The control
     * sync call is unconditional: a blocked queue head, a missing
     * accessibility runtime, or any other barrier must never delay it.
     */
    fun runPreClaimPass(forceSnapshot: Boolean = false): PreClaimPass {
        val outcome = syncClient.syncOnce(forceSnapshot)
        val suspect = suspectPolicy.evaluate(
            pausedHead = pausedHead(),
            lastAppliedControlSeq = state.lastAppliedControlSeq(),
            serverWatermark = syncClient.knownServerWatermark,
        )
        suspect?.let(onSuspectOrphaned)
        return PreClaimPass(
            controlSyncOutcome = outcome,
            suspect = suspect,
            claimPermitted = suspect == null,
        )
    }
}
