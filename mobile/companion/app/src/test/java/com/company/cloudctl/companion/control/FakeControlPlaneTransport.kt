package com.company.cloudctl.companion.control

import org.json.JSONObject

/** Programmable in-memory transport for pure-JVM control-sync tests. */
class FakeControlPlaneTransport : ControlPlaneTransport {
    val fetchCalls = mutableListOf<Pair<Long, Int>>()
    val acksPosted = mutableListOf<Triple<String, Long, String>>()
    var snapshotFetches = 0

    /** Queued cursor responses; exhausted queue repeats the last element. */
    val batches = ArrayDeque<ControlBatchResponse>()
    var cursorTooOld = false

    var snapshot: ReconcileSnapshotResponse = ReconcileSnapshotResponse(0, emptyList())
    var failAcks = false

    override fun fetchControlEvents(after: Long, limit: Int): ControlBatchResponse {
        fetchCalls += after to limit
        if (cursorTooOld) {
            throw ControlPlaneJson.parseCursorTooOld(
                410,
                JSONObject().put("code", "CURSOR_TOO_OLD").put("snapshotRequired", true).toString(),
            )!!
        }
        return if (batches.isEmpty()) {
            // "Nothing new": cursor echoed, watermark may still lead.
            ControlBatchResponse(after, after, after, emptyList())
        } else {
            batches.removeFirst()
        }
    }

    override fun fetchReconcileSnapshot(): ReconcileSnapshotResponse {
        snapshotFetches++
        return snapshot
    }

    override fun postControlAck(taskId: String, taskRevision: Long, result: String, reason: String?): JSONObject {
        if (failAcks) throw ControlPlaneHttpException(503, "down")
        acksPosted += Triple(taskId, taskRevision, result)
        return JSONObject()
    }
}
