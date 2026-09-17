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

/**
 * B17 §1: lastAppliedControlSeq is committed in the SAME transaction as the
 * mirror change; every crash point replays idempotently.
 */
@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class ControlStateStoreTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var control: ControlStateStore

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        reopen()
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
    }

    private fun reopen() {
        store = AutomationStore(context)
        control = ControlStateStore(store)
    }

    private fun batch(vararg events: ControlEvent, through: Long, watermark: Long = through): ControlBatchResponse =
        ControlBatchResponse(
            from = events.minOf { it.seq },
            through = through,
            highWatermark = watermark,
            events = events.toList(),
        )

    private fun event(seq: Long, taskId: String, revision: Long = 1, type: ControlEventType = ControlEventType.CANCEL) =
        ControlEvent(seq, taskId, revision, type, "2026-09-17T04:30:00Z")

    /** QUEUED → RUNNING → PAUSED_WAITING_USER mirror with a lease. */
    private fun pausedTask(taskId: String) {
        store.enqueueTask(taskId, """{"taskId":"$taskId"}""", "lease-$taskId", 0)
        store.claimNext()
        store.markPaused(taskId, null, -1, "operator pause")
    }

    @Test
    fun `cursor starts at zero and advances with batch through`() {
        assertEquals(0L, control.lastAppliedControlSeq())
        val report = control.applyControlBatch(
            batch(event(1302, "task-a"), through = 1307),
            target = 1307,
        )
        assertEquals(listOf(1302L), report.applied.map { it.seq })
        assertEquals(1307L, control.lastAppliedControlSeq())
        assertEquals(1307L, report.lastAppliedControlSeq)
    }

    @Test
    fun `CANCEL converges a paused mirror to terminal and queues CANCEL_APPLIED ack`() {
        pausedTask("task-a")
        control.applyControlBatch(batch(event(10, "task-a"), through = 10), target = 10)

        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-a"))
        // §0 payoff: the PAUSED queue head no longer blocks claims.
        assertTrue(!store.hasBlockingHead())
        val acks = control.pendingControlAcks()
        assertEquals(1, acks.size)
        assertEquals("task-a", acks[0].taskId)
        assertEquals(ControlAckResults.CANCEL_APPLIED, acks[0].result)
        assertEquals(1L, acks[0].taskRevision)
    }

    @Test
    fun `CANCEL over unresolved ledger stays RECONCILING and acks DEFERRED`() {
        store.enqueueTask("task-a", """{"taskId":"task-a"}""", "lease-a", 0)
        store.claimNext()
        store.recordActionIntent("key-1", "task-a", "hash-1")
        store.markActionUnknown("key-1")
        assertEquals(AutomationStore.STATE_RECONCILING, store.taskExecutionState("task-a"))

        control.applyControlBatch(batch(event(11, "task-a"), through = 11), target = 11)

        // §3.4: the terminal event never clears the local UNKNOWN ledger row.
        assertEquals(AutomationStore.STATE_RECONCILING, store.taskExecutionState("task-a"))
        val acks = control.pendingControlAcks()
        assertEquals(1, acks.size)
        assertEquals(ControlAckResults.CANCEL_DEFERRED_RECONCILING, acks[0].result)
    }

    @Test
    fun `CANCEL for a task absent from the mirror only advances the cursor with an APPLIED ack`() {
        control.applyControlBatch(batch(event(12, "task-ghost"), through = 12), target = 12)
        assertEquals(12L, control.lastAppliedControlSeq())
        assertEquals(1, control.pendingControlAcks().size)
        assertEquals(ControlAckResults.CANCEL_APPLIED, control.pendingControlAcks()[0].result)
    }

    @Test
    fun `crash replay after reopen is idempotent`() {
        pausedTask("task-a")
        control.applyControlBatch(batch(event(20, "task-a"), through = 25), target = 25)
        val stateBefore = store.taskExecutionState("task-a")
        val acksBefore = control.pendingControlAcks().size
        val outboxBefore = store.pendingEvents(limit = 100).size

        // Simulated crash: same batch redelivered after process restart.
        store.close()
        reopen()

        val report = control.applyControlBatch(batch(event(20, "task-a"), through = 25), target = 25)
        assertTrue(report.applied.isEmpty(), "replayed events must all be behind the cursor")
        assertEquals(listOf(20L), report.skippedAsReplayed.map { it.seq })
        assertEquals(25L, control.lastAppliedControlSeq())
        assertEquals(stateBefore, store.taskExecutionState("task-a"))
        assertEquals(acksBefore, control.pendingControlAcks().size)
        assertEquals(outboxBefore, store.pendingEvents(limit = 100).size)
    }

    @Test
    fun `mirror change and cursor commit atomically`() {
        pausedTask("task-a")
        // The transaction body throws AFTER the mirror mutation; both must roll back.
        val error = runCatching {
            store.controlTransaction {
                store.finish("task-a", false, "CANCELLED")
                error("simulated crash mid-transaction")
            }
        }.exceptionOrNull()
        assertTrue(error?.message == "simulated crash mid-transaction")

        assertEquals(AutomationStore.STATE_PAUSED, store.taskExecutionState("task-a"))
        assertEquals(0L, control.lastAppliedControlSeq())
        assertTrue(control.pendingControlAcks().isEmpty())
    }

    @Test
    fun `RESUME control event moves paused mirror to resume check`() {
        pausedTask("task-a")
        control.applyControlBatch(
            batch(event(30, "task-a", type = ControlEventType.RESUME), through = 30),
            target = 30,
        )
        assertEquals(AutomationStore.STATE_RESUME_CHECK, store.taskExecutionState("task-a"))
    }

    @Test
    fun `SET_CONFIRM_DEADLINE and CANCEL_REQUESTED only advance the cursor`() {
        pausedTask("task-a")
        control.applyControlBatch(
            batch(
                event(40, "task-a", type = ControlEventType.SET_CONFIRM_DEADLINE),
                event(41, "task-a", type = ControlEventType.CANCEL_REQUESTED),
                through = 41,
            ),
            target = 41,
        )
        assertEquals(AutomationStore.STATE_PAUSED, store.taskExecutionState("task-a"))
        assertEquals(41L, control.lastAppliedControlSeq())
        assertTrue(control.pendingControlAcks().isEmpty())
    }

    @Test
    fun `reconcile snapshot converges terminal tasks and jumps the cursor past compaction`() {
        pausedTask("task-a")
        val snapshot = ControlPlaneJson.parseReconcileSnapshot(
            org.json.JSONObject()
                .put("controlHighWatermark", 900)
                .put(
                    "tasks",
                    org.json.JSONArray().put(
                        org.json.JSONObject()
                            .put("taskId", "task-a")
                            .put("status", "ABANDONED")
                            .put("businessState", "ABANDONED")
                            .put("taskRevision", 2)
                            .put("terminal", true)
                            .put("ledgerBlocks", false),
                    ),
                )
                .toString(),
        )
        control.applyReconcileSnapshot(snapshot)

        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-a"))
        assertEquals(900L, control.lastAppliedControlSeq())
    }

    @Test
    fun `MARKED_UNKNOWN on a running task blocks the mirror into reconciling`() {
        store.enqueueTask("task-a", """{"taskId":"task-a"}""", "lease-a", 0)
        store.claimNext()
        control.applyControlBatch(
            batch(event(50, "task-a", type = ControlEventType.MARKED_UNKNOWN), through = 50),
            target = 50,
        )
        assertEquals(AutomationStore.STATE_RECONCILING, store.taskExecutionState("task-a"))
    }
}
