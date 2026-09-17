package com.company.cloudctl.companion.control

import org.json.JSONObject

/**
 * control-plane/v1@20260917.1 (K14, frozen) — client-side wire models.
 *
 * §1 every control event carries a device-wide monotonic [ControlEvent.seq];
 * the client credential is `lastAppliedControlSeq`, persisted in the SAME
 * transaction as the mirror change.
 */
enum class ControlEventType {
    CANCEL,
    CANCEL_REQUESTED,
    RESUME,
    MARKED_UNKNOWN,
    ABANDON,
    TERMINAL,
    SET_CONFIRM_DEADLINE,
    ;

    companion object {
        fun fromWire(value: String): ControlEventType? = entries.firstOrNull { it.name == value }
    }
}

data class ControlEvent(
    val seq: Long,
    val taskId: String,
    val taskRevision: Long,
    val type: ControlEventType,
    val issuedAt: String,
)

/** §2.1 cursor catch-up response body. */
data class ControlBatchResponse(
    val from: Long,
    val through: Long,
    val highWatermark: Long,
    val events: List<ControlEvent>,
)

/** §2.2 authoritative reconcile snapshot. */
data class ReconcileSnapshotTask(
    val taskId: String,
    /** serverRunnerStatus */
    val status: String,
    val businessState: String?,
    val taskRevision: Long,
    val terminal: Boolean,
    val ledgerBlocks: Boolean,
)

data class ReconcileSnapshotResponse(
    val controlHighWatermark: Long,
    val tasks: List<ReconcileSnapshotTask>,
)

/** §4 cancel-ack results. */
object ControlAckResults {
    const val CANCEL_APPLIED = "CANCEL_APPLIED"
    const val CANCEL_DEFERRED_RECONCILING = "CANCEL_DEFERRED_RECONCILING"
}

/** §5 CURSOR_TOO_OLD/410: retention crossed, snapshot reconciliation is mandatory. */
class ControlCursorTooOldException(val body: String) :
    IllegalStateException("Control cursor too old; snapshot reconciliation required")

class ControlPlaneHttpException(val status: Int, val body: String) :
    IllegalStateException("Control plane request failed with HTTP $status") {
    val retryable: Boolean get() = status in setOf(408, 425, 429) || status >= 500
}

object ControlPlaneJson {
    /**
     * §2.1: with events present — `from > after`, `through <= highWatermark`,
     * events strictly ascending, every seq inside [from, through]. An empty
     * batch ("nothing new") only needs `through <= highWatermark`; the server
     * may echo the cursor unchanged. Anything else rejects with
     * CONTROL_SEQ_INVALID semantics instead of applying a torn batch.
     */
    fun parseControlBatch(body: String): ControlBatchResponse {
        val root = JSONObject(body)
        val from = root.getLong("from")
        val through = root.getLong("through")
        val watermark = root.getLong("highWatermark")
        require(through <= watermark) { "CONTROL_SEQ_INVALID range from=$from through=$through watermark=$watermark" }
        val array = root.optJSONArray("events") ?: org.json.JSONArray()
        val events = mutableListOf<ControlEvent>()
        var previous = 0L
        for (index in 0 until array.length()) {
            val event = parseControlEvent(array.getJSONObject(index))
            require(event.seq > previous) { "CONTROL_SEQ_INVALID: seq order violation at ${event.seq}" }
            require(event.seq in from..through) { "CONTROL_SEQ_INVALID: seq ${event.seq} outside $from..$through" }
            previous = event.seq
            events += event
        }
        if (events.isNotEmpty()) {
            require(from in 1..through) { "CONTROL_SEQ_INVALID range from=$from through=$through" }
        }
        return ControlBatchResponse(from, through, watermark, events)
    }

    fun parseControlEvent(value: JSONObject): ControlEvent {
        val type = ControlEventType.fromWire(value.getString("type"))
            ?: throw IllegalArgumentException("Unknown control event type ${value.getString("type")}")
        return ControlEvent(
            seq = value.getLong("seq"),
            taskId = value.getString("taskId"),
            taskRevision = value.getLong("taskRevision"),
            type = type,
            issuedAt = value.optString("issuedAt"),
        )
    }

    /** §2.1 error shape: 410 { code: CURSOR_TOO_OLD, snapshotRequired: true }. */
    fun parseCursorTooOld(status: Int, body: String): ControlCursorTooOldException? {
        if (status != 410) return null
        val root = runCatching { JSONObject(body) }.getOrNull() ?: JSONObject()
        if (root.optString("code") != "CURSOR_TOO_OLD") return null
        return ControlCursorTooOldException(body)
    }

    fun parseReconcileSnapshot(body: String): ReconcileSnapshotResponse {
        val root = JSONObject(body)
        val watermark = root.getLong("controlHighWatermark")
        val array = root.optJSONArray("tasks") ?: org.json.JSONArray()
        val tasks = mutableListOf<ReconcileSnapshotTask>()
        for (index in 0 until array.length()) {
            val task = array.getJSONObject(index)
            tasks += ReconcileSnapshotTask(
                taskId = task.getString("taskId"),
                status = task.getString("status"),
                businessState = task.optString("businessState").takeIf { it.isNotBlank() },
                taskRevision = task.getLong("taskRevision"),
                terminal = task.getBoolean("terminal"),
                ledgerBlocks = task.optBoolean("ledgerBlocks", false),
            )
        }
        return ReconcileSnapshotResponse(watermark, tasks)
    }

    /** §4 ack payload: { taskId, taskRevision, result, reason? }. */
    fun buildControlAckPayload(taskId: String, taskRevision: Long, result: String, reason: String?): JSONObject =
        JSONObject()
            .put("taskId", taskId)
            .put("taskRevision", taskRevision)
            .put("result", result)
            .apply { reason?.let { put("reason", it) } }
}
