package com.company.cloudctl.companion.control

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.data.PausedHeadInfo
import java.time.Duration
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * B17 §0 frozen invariant: work acquisition may be gated; control-plane
 * synchronization may never be. These tests pin the sync-loop ordering seam.
 */
@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class ControlLoopOrchestratorTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var state: ControlStateStore
    private lateinit var transport: FakeControlPlaneTransport
    private lateinit var client: ControlSyncClient
    private lateinit var alerts: MutableList<SuspectOrphanedPolicy.Signal>
    private lateinit var orchestrator: ControlLoopOrchestrator

    private val now = Instant.parse("2026-09-17T06:00:00Z")

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
        store = AutomationStore(context)
        state = ControlStateStore(store)
        transport = FakeControlPlaneTransport()
        client = ControlSyncClient(transport, state)
        alerts = mutableListOf()
        orchestrator = ControlLoopOrchestrator(
            syncClient = client,
            state = state,
            pausedHead = { store.pausedHeadInfo() },
            suspectPolicy = SuspectOrphanedPolicy(
                pausedOlderThan = Duration.ofMinutes(10),
                clock = { now },
            ),
            onSuspectOrphaned = { alerts += it },
        )
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(AutomationStore.DATABASE_NAME)
    }

    private fun event(seq: Long, taskId: String, type: ControlEventType = ControlEventType.CANCEL) =
        ControlEvent(seq, taskId, 1, type, "2026-09-17T04:30:00Z")

    private fun pausedTask(taskId: String, pausedAt: Instant) {
        store.enqueueTask(taskId, """{"taskId":"$taskId"}""", "lease-$taskId", 0)
        store.claimNext()
        store.markPaused(taskId, null, -1, "operator pause")
        // Backdate the mirror row into the suspect window.
        store.writableDatabase.execSQL(
            "UPDATE task_inbox SET updated_at=? WHERE task_id=?",
            arrayOf(pausedAt.toString(), taskId),
        )
    }

    @Test
    fun `control sync runs even when the queue head blocks claims`() {
        pausedTask("task-a", now.minus(Duration.ofMinutes(30)))
        // The heartbeat escape channel already saw a watermark far ahead.
        client.onHeartbeatResponse(controlHighWatermark = 500, inlineEvents = emptyList())

        val pass = orchestrator.runPreClaimPass()

        // §0: the cursor fetch happened despite the PAUSED head.
        assertTrue(transport.fetchCalls.isNotEmpty(), "control sync must not be gated by the blocked queue head")
        assertEquals(AutomationStore.STATE_PAUSED, store.taskExecutionState("task-a"))
    }

    @Test
    fun `suspect orphaned alerts, forces snapshot reconcile and blocks claims without unblocking the mirror`() {
        pausedTask("task-a", now.minus(Duration.ofMinutes(30)))
        client.onHeartbeatResponse(controlHighWatermark = 500, inlineEvents = emptyList())

        val pass = orchestrator.runPreClaimPass()

        // §3.3 required: alert raised, new destructive claims blocked…
        assertEquals(1, alerts.size)
        assertEquals("task-a", alerts[0].taskId)
        assertTrue(!pass.claimPermitted)
        // …and forbidden: the PAUSED blocker is NOT cleared locally (D-7).
        assertEquals(AutomationStore.STATE_PAUSED, store.taskExecutionState("task-a"))

        // The alert forces a snapshot reconciliation on the next pass.
        transport.snapshot = ControlPlaneJson.parseReconcileSnapshot(
            org.json.JSONObject()
                .put("controlHighWatermark", 500)
                .put("tasks", org.json.JSONArray())
                .toString(),
        )
        orchestrator.runPreClaimPass(forceSnapshot = true)
        assertEquals(1, transport.snapshotFetches)
        // Snapshot without a server terminal: still PAUSED (server-authoritative
        // pause stands; only its own ABANDON/CANCEL events resolve it).
        assertEquals(AutomationStore.STATE_PAUSED, store.taskExecutionState("task-a"))
    }

    @Test
    fun `server-authoritative CANCEL resolves the suspect and reopens claims`() {
        pausedTask("task-a", now.minus(Duration.ofMinutes(30)))
        client.onHeartbeatResponse(controlHighWatermark = 500, inlineEvents = emptyList())

        val suspectPass = orchestrator.runPreClaimPass()
        assertTrue(!suspectPass.claimPermitted)

        // The server now resolves the orphan through the control channel.
        transport.batches += ControlBatchResponse(490, 500, 500, listOf(event(490, "task-a")))
        val resolvedPass = orchestrator.runPreClaimPass()

        assertNull(resolvedPass.suspect, "signal disappears once the PAUSED head is gone")
        assertTrue(resolvedPass.claimPermitted)
        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-a"))
        assertEquals(listOf(Triple("task-a", 1L, ControlAckResults.CANCEL_APPLIED)), transport.acksPosted)
    }

    @Test
    fun `fresh pause and caught-up cursor never escalate`() {
        pausedTask("task-a", now.minus(Duration.ofMinutes(1)))
        client.onHeartbeatResponse(controlHighWatermark = 100, inlineEvents = emptyList())
        transport.batches += ControlBatchResponse(90, 100, 100, emptyList())
        orchestrator.runPreClaimPass()
        assertTrue(alerts.isEmpty())

        // Old pause but cursor caught up: the server confirms the pause; its
        // confirm deadline produces the authoritative ABANDON (§3.2). The
        // head info is synthetic — no mirror mutation is involved.
        assertNull(
            SuspectOrphanedPolicy(Duration.ofMinutes(10)) { now }.evaluate(
                PausedHeadInfo("task-b", now.minus(Duration.ofMinutes(30)).toString()),
                lastAppliedControlSeq = 100,
                serverWatermark = 100,
            ),
        )
    }

    @Test
    fun `policy is a pure evaluation and never mutates the mirror`() {
        pausedTask("task-a", now.minus(Duration.ofHours(2)))
        val policy = SuspectOrphanedPolicy(Duration.ofMinutes(10)) { now }
        val signal = policy.evaluate(
            PausedHeadInfo("task-a", now.minus(Duration.ofHours(2)).toString()),
            lastAppliedControlSeq = 10,
            serverWatermark = 40,
        )
        assertNotNull(signal)
        assertEquals(30L, signal.controlLag)
        // Even after escalation the mirror row is untouched — the policy holds
        // no write path at all (k14-negative-local-timeout-unblock: local
        // timeout never unblocks PAUSED/UNKNOWN).
        assertEquals(AutomationStore.STATE_PAUSED, store.taskExecutionState("task-a"))
    }
}
