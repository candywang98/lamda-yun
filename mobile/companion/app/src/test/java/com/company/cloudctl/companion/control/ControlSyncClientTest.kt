package com.company.cloudctl.companion.control

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.data.AutomationStore
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class ControlSyncClientTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var state: ControlStateStore
    private lateinit var transport: FakeControlPlaneTransport
    private lateinit var client: ControlSyncClient

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
        state = ControlStateStore(store)
        transport = FakeControlPlaneTransport()
        client = ControlSyncClient(transport, state)
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
    }

    private fun batch(vararg events: ControlEvent, through: Long, watermark: Long = through) =
        ControlBatchResponse(events.minOf { it.seq }, through, watermark, events.toList())

    private fun event(seq: Long, taskId: String, revision: Long = 1, type: ControlEventType = ControlEventType.CANCEL) =
        ControlEvent(seq, taskId, revision, type, "2026-09-17T04:30:00Z")

    private fun pausedTask(taskId: String) {
        store.enqueueTask(taskId, """{"taskId":"$taskId"}""", "lease-$taskId", 0)
        store.claimNext()
        store.markPaused(taskId, null, -1, "operator pause")
    }

    @Test
    fun `cursor catch-up applies batch events and uploads the queued ack`() {
        pausedTask("task-a")
        transport.batches += batch(event(10, "task-a"), through = 12, watermark = 12)

        val outcome = client.syncOnce()

        assertTrue(outcome.cursorAdvanced)
        assertEquals(12L, state.lastAppliedControlSeq())
        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-a"))
        assertEquals(listOf(Triple("task-a", 1L, ControlAckResults.CANCEL_APPLIED)), transport.acksPosted)
        assertTrue(state.pendingControlAcks().isEmpty(), "uploaded ack must leave the outbox")
    }

    @Test
    fun `410 CURSOR_TOO_OLD falls back to the snapshot and jumps the cursor`() {
        pausedTask("task-a")
        transport.cursorTooOld = true
        transport.snapshot = ControlPlaneJson.parseReconcileSnapshot(
            org.json.JSONObject()
                .put("controlHighWatermark", 1307)
                .put(
                    "tasks",
                    org.json.JSONArray().put(
                        org.json.JSONObject()
                            .put("taskId", "task-a")
                            .put("status", "CANCELLED")
                            .put("taskRevision", 3)
                            .put("terminal", true),
                    ),
                )
                .toString(),
        )

        val outcome = client.syncOnce()

        assertTrue(outcome.reconciledFromSnapshot)
        assertEquals(1, transport.snapshotFetches)
        assertEquals(1307L, state.lastAppliedControlSeq())
        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-a"))
        // Next round: cursor is past compaction — the server keeps serving
        // (cursorTooOld only fired while the cursor was behind retention).
        transport.cursorTooOld = false
        client.syncOnce()
        assertEquals(1, transport.snapshotFetches)
    }

    @Test
    fun `multi-batch catch-up drains until through reaches the watermark`() {
        pausedTask("task-a")
        transport.batches += batch(event(5, "task-a"), through = 5, watermark = 20)
        transport.batches += batch(event(9, "task-a", type = ControlEventType.SET_CONFIRM_DEADLINE), through = 20)

        client.syncOnce()

        assertEquals(listOf(0L, 5L), transport.fetchCalls.map { it.first })
        assertEquals(20L, state.lastAppliedControlSeq())
    }

    @Test
    fun `ack upload defers while the task is running and rewrites to DEFERRED on reconciling`() {
        store.enqueueTask("task-a", """{"taskId":"task-a"}""", "lease-a", 0)
        store.claimNext() // RUNNING
        transport.batches += batch(event(30, "task-a"), through = 30)

        client.syncOnce()

        // RUNNING: cancel interruption flows through the task heartbeat channel;
        // the ack waits, the server keeps CANCEL as desired (§4).
        assertTrue(state.pendingControlAcks().isNotEmpty())
        assertTrue(transport.acksPosted.isEmpty())

        // Executor settles into RECONCILING (UNKNOWN ledger): ack rewrites to DEFERRED.
        store.recordActionIntent("key-1", "task-a", "hash-1")
        store.markActionUnknown("key-1")
        client.syncOnce()
        assertEquals(
            listOf(Triple("task-a", 1L, ControlAckResults.CANCEL_DEFERRED_RECONCILING)),
            transport.acksPosted,
        )
        assertTrue(state.pendingControlAcks().isEmpty())
    }

    @Test
    fun `retryable ack failure keeps the ack queued`() {
        pausedTask("task-a")
        transport.batches += batch(event(40, "task-a"), through = 40)
        transport.failAcks = true

        client.syncOnce()

        assertEquals(1, state.pendingControlAcks().size)
        assertEquals(40L, state.lastAppliedControlSeq())
    }

    @Test
    fun `heartbeat watermark and inline events feed idempotent apply`() {
        pausedTask("task-a")
        val cancel = event(60, "task-a")

        client.onHeartbeatResponse(controlHighWatermark = 60, inlineEvents = listOf(cancel))
        assertEquals(60L, state.lastAppliedControlSeq())
        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-a"))
        assertEquals(60L, client.knownServerWatermark)

        // Re-delivery of the same inline event (server retries before ack):
        // idempotent — no duplicate ack, no state change.
        client.onHeartbeatResponse(controlHighWatermark = 60, inlineEvents = listOf(cancel))
        assertEquals(1, state.pendingControlAcks().size)
        assertEquals(60L, state.lastAppliedControlSeq())
    }

    @Test
    fun `heartbeat request fields follow the frozen contract shape`() {
        val fields = client.heartbeatRequestFields(lastApplied = 12, safetyBarrier = "RECONCILING")
        assertEquals(12L, fields.getLong("lastAppliedControlSeq"))
        assertEquals("RECONCILING", fields.getString("safetyBarrier"))
    }
}
