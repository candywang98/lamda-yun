package com.company.cloudctl.companion.control

import com.company.cloudctl.companion.data.PausedHeadInfo
import java.time.Duration
import java.time.Instant

/**
 * B17 control-plane/v1 §3.3 (D-7): a local PAUSED mirror that has been stuck
 * longer than expected WHILE the control cursor lags the server watermark can
 * at most be escalated to SUSPECT_ORPHANED — an alert plus forced sync plus
 * snapshot reconciliation plus a claim block on destructive tasks. The local
 * clock is NEVER a reason to clear the PAUSED/UNKNOWN blocker; only server
 * events (ABANDON/CANCEL) or a snapshot reconcile converge the mirror, after
 * which the signal naturally disappears.
 */
class SuspectOrphanedPolicy(
    private val pausedOlderThan: Duration = DEFAULT_PAUSED_OLDER_THAN,
    private val clock: () -> Instant = Instant::now,
) {
    data class Signal(
        val taskId: String,
        val pausedSince: Instant,
        val controlLag: Long,
    )

    fun evaluate(pausedHead: PausedHeadInfo?, lastAppliedControlSeq: Long, serverWatermark: Long): Signal? {
        val head = pausedHead ?: return null
        val pausedSince = runCatching { Instant.parse(head.pausedSince) }.getOrNull() ?: return null
        // A fresh pause is a legitimate operator state — not suspect.
        if (Duration.between(pausedSince, clock()) < pausedOlderThan) return null
        // A stuck mirror with a caught-up cursor means the server confirms the
        // pause; its humanConfirmDeadline (§3.2) will produce the authoritative
        // ABANDON/CANCEL. Only a lagging cursor is suspicious.
        if (serverWatermark <= lastAppliedControlSeq) return null
        return Signal(
            taskId = head.taskId,
            pausedSince = pausedSince,
            controlLag = serverWatermark - lastAppliedControlSeq,
        )
    }

    companion object {
        /** Well beyond ordinary operator takeover; matches BLOCKED_RETIRE_MILLIS scale. */
        val DEFAULT_PAUSED_OLDER_THAN: Duration = Duration.ofMinutes(10)
    }
}
