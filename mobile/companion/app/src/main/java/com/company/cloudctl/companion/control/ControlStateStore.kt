package com.company.cloudctl.companion.control

import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.data.PendingControlAck

/** Outcome of one transactional apply pass; feeds ack upload and metrics. */
data class ControlApplyReport(
    /** Events whose seq was behind the cursor and got skipped (idempotent replay). */
    val skippedAsReplayed: List<ControlEvent>,
    /** Events actually applied in this transaction. */
    val applied: List<ControlEvent>,
    val lastAppliedControlSeq: Long,
)

/**
 * B17 control-plane/v1 §1: applies control events with the client cursor
 * (`lastAppliedControlSeq`) in ONE transaction over the AutomationStore
 * database: apply event + update mirror + update lastApplied + COMMIT.
 * Any crash point replays idempotently — every event with
 * `seq <= lastAppliedControlSeq` is skipped on the next pass.
 *
 * §3.4 is preserved: a server terminal converges the mirror, but local
 * UNKNOWN ledger rows are never cleared by a terminal state; such tasks stay
 * RECONCILING and CANCEL acks take the DEFERRED branch (§4).
 */
class ControlStateStore(private val store: AutomationStore) {

    fun lastAppliedControlSeq(): Long = store.lastAppliedControlSeq()

    /**
     * Applies [batch.events] (plus any already-known-but-unapplied seqs) and
     * advances the cursor to [target]. Events referencing tasks absent from
     * the local mirror only advance the cursor — there is nothing to converge.
     */
    fun applyControlBatch(batch: ControlBatchResponse, target: Long): ControlApplyReport =
        applyEvents(batch.events, target)

    fun applyInlineEvents(events: List<ControlEvent>, target: Long): ControlApplyReport =
        applyEvents(events, target)

    /** §2.2 snapshot reconciliation: the server state is authoritative for the
     * mirror; the cursor jumps to the snapshot watermark so subsequent cursor
     * fetches no longer 410. */
    fun applyReconcileSnapshot(snapshot: ReconcileSnapshotResponse): ControlApplyReport =
        store.controlTransaction {
            for (task in snapshot.tasks) {
                val state = store.taskExecutionState(task.taskId) ?: continue
                if (task.terminal && state !in TERMINAL_MIRROR_STATES) {
                    // Server-authoritative terminal: converge the mirror. An
                    // unresolved ledger keeps the row RECONCILING (§3.4).
                    store.finish(task.taskId, false, "SERVER_TERMINAL_${task.status}")
                }
            }
            val advanced = maxOf(store.lastAppliedControlSeq(), snapshot.controlHighWatermark)
            advanceCursorLocked(advanced)
            ControlApplyReport(emptyList(), emptyList(), advanced)
        }

    /** Pending §4 acks; callers defer upload while the task is still RUNNING. */
    fun pendingControlAcks(): List<PendingControlAck> = store.pendingControlAcks()

    fun isTaskLocallyRunning(taskId: String): Boolean =
        store.taskExecutionState(taskId) == AutomationStore.STATE_RUNNING

    /** True when the mirror row is (or settled into) RECONCILING — §4 DEFERRED branch. */
    fun isTaskReconciling(taskId: String): Boolean =
        store.taskExecutionState(taskId) == AutomationStore.STATE_RECONCILING

    fun removeControlAck(id: Long) = store.removeControlAck(id)

    private fun applyEvents(events: List<ControlEvent>, target: Long): ControlApplyReport =
        store.controlTransaction {
            var lastApplied = store.lastAppliedControlSeq()
            val skipped = mutableListOf<ControlEvent>()
            val applied = mutableListOf<ControlEvent>()
            for (event in events.sortedBy { it.seq }) {
                if (event.seq <= lastApplied) {
                    skipped += event
                    continue
                }
                applyOne(event)
                applied += event
                lastApplied = maxOf(lastApplied, event.seq)
            }
            // The cursor tracks the server range (through / watermark), not just
            // the last event seq: the batch guarantees no device event between
            // lastApplied and target was missed.
            if (target > lastApplied) lastApplied = target
            advanceCursorLocked(lastApplied)
            ControlApplyReport(skipped, applied, lastApplied)
        }

    /**
     * Mirror convergence per event type. Must stay inside the caller's
     * transaction so the cursor and the mirror commit together.
     */
    private fun applyOne(event: ControlEvent) {
        when (event.type) {
            ControlEventType.CANCEL -> applyCancel(event)
            ControlEventType.ABANDON, ControlEventType.TERMINAL -> convergeToTerminal(event)
            ControlEventType.RESUME -> resumeMirror(event)
            ControlEventType.MARKED_UNKNOWN -> markUnknown(event)
            // These carry no local mirror obligation beyond the cursor advance:
            // CANCEL_REQUESTED interrupts a RUNNING task through the task
            // heartbeat channel (applyHeartbeatControl), SET_CONFIRM_DEADLINE
            // is enforced server-side (§3.2).
            ControlEventType.CANCEL_REQUESTED, ControlEventType.SET_CONFIRM_DEADLINE -> Unit
        }
    }

    /**
     * §4: CANCEL neutralizes the local mirror. When the task has unresolved
     * controlled actions (UNKNOWN ledger) the ack is DEFERRED_RECONCILING —
     * the server stays RECONCILING for manual reconciliation. A RUNNING task
     * keeps executing: its interruption flows through the task heartbeat
     * channel, and the pending APPLIED ack stays queued until the executor
     * settles (see [isTaskLocallyRunning]); if it settles into RECONCILING
     * the uploader rewrites the result to DEFERRED at send time.
     */
    private fun applyCancel(event: ControlEvent) {
        val state = store.taskExecutionState(event.taskId)
        when (state) {
            null -> {
                store.enqueueControlAck(
                    event.taskId, event.taskRevision, ControlAckResults.CANCEL_APPLIED, null,
                )
                return
            }
            AutomationStore.STATE_RUNNING,
            AutomationStore.STATE_RECONCILING,
            AutomationStore.STATE_TERMINAL_PENDING,
            AutomationStore.STATE_TERMINAL_CONFIRMED,
            AutomationStore.STATE_TERMINAL_REJECTED,
            -> Unit
            else -> store.finish(event.taskId, false, "CANCELLED")
        }
        val finalState = store.taskExecutionState(event.taskId)
        if (finalState == AutomationStore.STATE_RECONCILING) {
            store.enqueueControlAck(
                event.taskId,
                event.taskRevision,
                ControlAckResults.CANCEL_DEFERRED_RECONCILING,
                "unresolved controlled-action ledger; manual reconciliation required",
            )
        } else {
            store.enqueueControlAck(
                event.taskId, event.taskRevision, ControlAckResults.CANCEL_APPLIED, null,
            )
        }
    }

    private fun convergeToTerminal(event: ControlEvent) {
        val state = store.taskExecutionState(event.taskId) ?: return
        if (state in TERMINAL_MIRROR_STATES) return
        if (state == AutomationStore.STATE_RUNNING) return
        store.finish(event.taskId, false, "SERVER_${event.type.name}")
    }

    /** Server RESUME releases the PAUSED blocker; the run resumes via the existing resume command path. */
    private fun resumeMirror(event: ControlEvent) {
        val state = store.taskExecutionState(event.taskId)
            ?: return
        if (state != AutomationStore.STATE_PAUSED) return
        val leaseId = store.persistedTask(event.taskId)?.leaseId ?: return
        store.markResumeCheck(event.taskId, leaseId)
    }

    /** §3.4: MARKED_UNKNOWN keeps the local ledger blocking; the mirror follows. */
    private fun markUnknown(event: ControlEvent) {
        val state = store.taskExecutionState(event.taskId) ?: return
        if (state == AutomationStore.STATE_RECONCILING) return
        if (state != AutomationStore.STATE_RUNNING) return
        store.markTaskReconciling(event.taskId)
    }

    /** Cursor write inside the caller's transaction — commits with the mirror change (§1). */
    private fun android.database.sqlite.SQLiteDatabase.advanceCursorLocked(seq: Long) {
        execSQL(
            "UPDATE control_state SET last_applied_control_seq=?,updated_at=? WHERE id=1 AND last_applied_control_seq<?",
            arrayOf(seq.toString(), java.time.Instant.now().toString(), seq.toString()),
        )
    }

    private companion object {
        val TERMINAL_MIRROR_STATES = setOf(
            AutomationStore.STATE_TERMINAL_PENDING,
            AutomationStore.STATE_TERMINAL_CONFIRMED,
            AutomationStore.STATE_TERMINAL_REJECTED,
            AutomationStore.TERMINAL_SUCCEEDED,
            AutomationStore.TERMINAL_FAILED,
        )
    }
}
