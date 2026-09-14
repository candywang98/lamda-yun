package com.company.cloudctl.companion.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class AutomationStoreTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(DATABASE_NAME)
        store = AutomationStore(context)
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(DATABASE_NAME)
    }

    @Test
    fun `duplicate enqueue is idempotent and claim is durable`() {
        assertTrue(store.enqueueTask("task-1", "payload", "lease-1", 0))
        assertFalse(store.enqueueTask("task-1", "payload", "lease-1", 0))
        assertNotNull(store.claimNext())
        assertNull(store.claimNext())

        store.close()
        store = AutomationStore(context)
        assertNull(store.claimNext())
    }

    @Test
    fun `restart recovery never reexecutes and persists terminal failure`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()

        store.close()
        store = AutomationStore(context)
        store.recoverInterruptedRuns()

        assertNull(store.claimNext())
        assertEquals("RESUME_CHECK", taskState("task-1"))
        assertTrue(store.pendingEvents().isEmpty())
    }

    @Test
    fun `successful finish uploads typed result instead of empty json`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()
        store.finish("task-1", true)
        val terminal = store.pendingEvents().single()
        val result = JSONObject(terminal.payload).getJSONObject("result")
        assertEquals("ok", result.getString("outcome"))
        assertEquals("DeviceProbeResult", result.getString("resultType"))
        assertFalse(result.has("password"))
    }

    @Test
    fun `idlefish publish finish reports listing result type`() {
        val payload = JSONObject()
            .put("protocolVersion", "cloudctl.mobile/v1")
            .put("taskId", "task-publish")
            .put("deviceId", "device-1")
            .put("targetPackage", "com.taobao.idlefish")
            .put("commandType", "xianyu.publish_listing.v1")
            .put("issuedAt", "2026-09-07T12:00:00Z")
            .put("expiresAt", "2026-09-07T12:10:00Z")
            .put("maxRunSeconds", 180)
            .put("steps", org.json.JSONArray())
            .toString()
        store.enqueueTask("task-publish", payload, "lease-1", 0)
        store.claimNext()
        store.finish("task-publish", true)
        val result = JSONObject(store.pendingEvents().single().payload).getJSONObject("result")
        assertEquals("XianyuPublishListingResult", result.getString("resultType"))
    }

    @Test
    fun `reclaim after terminal rejection requeues complete for the new lease`() {
        val first = JSONObject()
            .put("taskId", "task-1")
            .put("deviceId", "device-1")
            .put("targetPackage", "com.taobao.idlefish")
            .put("issuedAt", "2026-09-07T12:00:00Z")
            .put("steps", org.json.JSONArray().put(JSONObject().put("stepId", "mark-published").put("controlEpoch", 1)))
            .toString()
        store.enqueueTask("task-1", first, "lease-1", 0)
        store.claimNext()
        store.finish("task-1", true)
        store.markPermanentlyRejected(store.pendingEvents().single().id, "HTTP_422")
        assertEquals("TERMINAL_REJECTED", taskState("task-1"))

        val second = JSONObject()
            .put("taskId", "task-1")
            .put("deviceId", "device-1")
            .put("targetPackage", "com.taobao.idlefish")
            .put("commandType", "xianyu.publish_listing.v1")
            .put("issuedAt", "2026-09-07T12:20:00Z")
            .put("steps", org.json.JSONArray().put(JSONObject().put("stepId", "mark-published").put("controlEpoch", 42)))
            .toString()
        assertFalse(store.enqueueTask("task-1", second, "lease-2", 48))
        assertEquals("TERMINAL_PENDING_UPLOAD", taskState("task-1"))
        val retry = store.pendingEvents().single { JSONObject(it.payload).optString("leaseId") == "lease-2" }
        assertTrue(retry.path.endsWith("/complete"))
        assertEquals(
            "XianyuPublishListingResult",
            JSONObject(retry.payload).getJSONObject("result").getString("resultType"),
        )
    }

    @Test
    fun `checkpoint resumes from Nth item and applied journal blocks second click`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()
        store.saveCheckpoint("task-1", "attempt-1", "item", "snap", "recipe", "account-a", 1, 3, "item-3")
        val checkpoint = store.latestCheckpoint("task-1")
        assertNotNull(checkpoint)
        assertEquals(3, checkpoint!!.getInt("loopCursor"))
        assertEquals("item-3", checkpoint.getString("itemId"))
        assertEquals("INTENT", store.recordActionIntent("task-1:item-3:publish", "task-1", "hash-1"))
        assertEquals("UNKNOWN", store.recordActionIntent("task-1:item-3:publish", "task-1", "hash-1"))
        store.markActionApplied("task-1:item-3:publish")
        assertEquals("APPLIED", store.recordActionIntent("task-1:item-3:publish", "task-1", "hash-1"))
    }

    @Test
    fun `action journal binds identity and stays monotonic across reopen`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()
        assertEquals("INTENT", store.recordActionIntent("task-1:item-1:publish", "task-1", "hash-1"))
        assertEquals("UNKNOWN", store.recordActionIntent("task-1:item-1:publish", "task-1", "hash-1"))
        assertEquals("INTENT", store.actionJournal("task-1:item-1:publish")!!.status)
        store.close()
        store = AutomationStore(context)
        val persisted = store.actionJournal("task-1:item-1:publish")
        assertNotNull(persisted)
        assertEquals("task-1", persisted!!.taskId)
        assertEquals("hash-1", persisted.parameterHash)
        assertEquals("INTENT", persisted.status)
        assertEquals("UNKNOWN", store.recordActionIntent("task-1:item-1:publish", "task-1", "hash-1"))
        assertEquals("INTENT", store.actionJournal("task-1:item-1:publish")!!.status)
        assertFailsWith<IllegalArgumentException> {
            store.recordActionIntent("task-1:item-1:publish", "task-1", "hash-changed")
        }
        assertFailsWith<IllegalArgumentException> {
            store.recordActionIntent("task-1:item-1:publish", "task-other", "hash-1")
        }
        assertEquals("INTENT", store.actionJournal("task-1:item-1:publish")!!.status)
        store.markActionUnknown("task-1:item-1:publish")
        assertEquals("UNKNOWN", store.actionJournal("task-1:item-1:publish")!!.status)
        store.close()
        store = AutomationStore(context)
        assertEquals("UNKNOWN", store.actionJournal("task-1:item-1:publish")!!.status)
        assertEquals("UNKNOWN", store.recordActionIntent("task-1:item-1:publish", "task-1", "hash-1"))
        store.markActionUnknown("task-1:item-1:publish")
        assertFailsWith<IllegalStateException> {
            store.markActionApplied("task-1:item-1:publish")
        }
        assertEquals("UNKNOWN", store.actionJournal("task-1:item-1:publish")!!.status)

        store.enqueueTask("task-2", "payload-2", "lease-2", 0)
        store.claimNext()
        assertEquals("INTENT", store.recordActionIntent("task-2:item-1:publish", "task-2", "hash-2"))
        store.markActionApplied("task-2:item-1:publish")
        store.close()
        store = AutomationStore(context)
        assertEquals("APPLIED", store.recordActionIntent("task-2:item-1:publish", "task-2", "hash-2"))
        store.markActionApplied("task-2:item-1:publish")
        assertFailsWith<IllegalStateException> {
            store.markActionUnknown("task-2:item-1:publish")
        }
        assertEquals("APPLIED", store.actionJournal("task-2:item-1:publish")!!.status)
        assertFailsWith<IllegalStateException> {
            store.markActionApplied("missing-key")
        }
        assertFailsWith<IllegalStateException> {
            store.markActionUnknown("missing-key")
        }
        assertNull(store.actionJournal("missing-key"))
    }

    @Test
    fun `pause handshake persists checkpoint and blocks later queued work`() {
        store.enqueueTask("task-1", "payload-one", "lease-1", 0)
        store.enqueueTask("task-2", "payload-two", "lease-2", 0)
        store.claimNext()
        store.saveCheckpoint("task-1", "lease-1", "fill-price", "pause", "recipe", "account-a", 1, 4, "fill-price")
        store.markPaused("task-1", "fill-price", 4, "operator taking over")

        assertEquals("PAUSED_WAITING_USER", taskState("task-1"))
        assertTrue(store.hasBlockingHead())
        assertNull(store.claimNext())
        val ack = store.pendingEvents().single { JSONObject(it.payload).optString("eventType") == "PAUSED_WAITING_USER" }
        assertTrue(ack.path.endsWith("/events"))
        assertEquals("fill-price", store.latestCheckpoint("task-1")!!.getString("stateId"))
    }

    @Test
    fun `resume check keeps the original taskId and still blocks later queued work`() {
        store.enqueueTask("task-1", "payload-one", "lease-1", 0)
        store.enqueueTask("task-2", "payload-two", "lease-2", 0)
        store.claimNext()
        store.saveCheckpoint("task-1", "lease-1", "fill-price", "pause", "recipe", "account-a", 1, 4, "fill-price")
        store.markPaused("task-1", "fill-price", 4, "operator taking over")

        assertTrue(store.markResumeCheck("task-1", "lease-3"))
        assertEquals("RESUME_CHECK", taskState("task-1"))
        assertTrue(store.hasBlockingHead())
        assertNull(store.claimNext())
        assertTrue(store.markResumeCheck("task-1", "lease-3"))

        val resumed = store.claimResume("task-1")
        assertNotNull(resumed)
        assertEquals("task-1", resumed!!.taskId)
        assertEquals("lease-3", resumed.leaseId)
        assertEquals("RUNNING", taskState("task-1"))
        assertEquals("QUEUED", taskState("task-2"))
    }

    @Test
    fun `finished task cannot be resumed on the original taskId`() {
        store.enqueueTask("task-1", "payload-one", "lease-1", 0)
        store.claimNext()
        store.finish("task-1", false, "CANCELLED")
        assertFalse(store.markResumeCheck("task-1", "lease-9"))
        assertNull(store.claimResume("task-1"))
    }

    @Test
    fun `journal event and sequence are committed with one outbox record`() {
        store.enqueueTask("task-1", "payload", "lease-1", 7)
        store.claimNext()
        store.recordStepEvent(
            "task-1",
            "open_app",
            "STARTED",
            "STEP_STARTED",
            "STEP_STARTED",
            0,
        )

        val event = store.pendingEvents().single()
        assertEquals(8, JSONObject(event.payload).getInt("sequence"))
        assertEquals(9, intQuery("SELECT next_sequence FROM task_inbox WHERE task_id='task-1'"))
        assertEquals(2, intQuery("SELECT COUNT(*) FROM run_journal WHERE task_id='task-1'"))
    }

    @Test
    fun `retry metadata survives reopen and blocks later delivery`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()
        store.enqueueStepEvent("task-1", "STEP_STARTED", 0)
        store.finish("task-1", true)
        val first = store.pendingEvents().first()
        val now = Instant.now()
        val future = now.plusSeconds(300)
        store.recordDeliveryFailure(first.id, "HTTP_503", future)

        store.close()
        store = AutomationStore(context)
        assertTrue(store.pendingEvents(now).isEmpty())
        val retried = store.pendingEvents(future)
        assertEquals(2, retried.size)
        assertEquals(1, retried.first().attemptCount)
    }

    @Test
    fun `terminal state is confirmed only after delivery`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()
        store.finish("task-1", true)
        assertEquals("TERMINAL_PENDING_UPLOAD", taskState("task-1"))

        store.markDelivered(store.pendingEvents().single().id)
        assertEquals("TERMINAL_CONFIRMED", taskState("task-1"))
        assertTrue(store.pendingEvents().isEmpty())
    }

    @Test
    fun `unresolved intent and unknown block ordinary exits across reopen`() {
        for (unknown in listOf(false, true)) {
            store.close()
            context.deleteDatabase(DATABASE_NAME)
            store = AutomationStore(context)
            store.enqueueTask("task-1", "payload", "lease-1", 0)
            store.claimNext()
            store.recordActionIntent("action", "task-1", "hash")
            if (unknown) store.markActionUnknown("action")
            store.enqueueTask("task-2", "other", "lease-2", 0)
            assertTrue(store.hasBlockingHead())
            assertNull(store.claimNext())
            store.close()
            store = AutomationStore(context)
            assertEquals(AutomationStore.STATE_RECONCILING, taskState("task-1"))
            store.recoverInterruptedRuns()
            assertTrue(store.hasBlockingHead())
            assertNull(store.claimNext())
            assertNull(store.claimResume())
            assertNull(store.claimResume("task-1"))
            assertFalse(store.markResumeCheck("task-1", "replacement"))
            assertFailsWith<IllegalArgumentException> { store.markPaused("task-1", null, 0, null) }
            assertFalse(store.enqueueTask("task-1", "payload", "lease-1", 0))
            assertFalse(store.enqueueTask("task-1", "payload", "replacement", 20))
            store.finish("task-1", true)
            store.finish("task-1", false)
            assertEquals(AutomationStore.STATE_RECONCILING, taskState("task-1"))
            assertTrue(store.pendingEvents().isEmpty())
            assertEquals(if (unknown) "UNKNOWN" else "INTENT", store.actionJournal("action")?.status)
            assertEquals("lease-1", store.readableDatabase.rawQuery(
                "SELECT lease_id FROM task_inbox WHERE task_id='task-1'", emptyArray(),
            ).use { it.moveToFirst(); it.getString(0) })
        }
    }

    @Test
    fun `legacy terminal state with unresolved intent reopens as reconciliation`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        store.claimNext()
        store.finish("task-1", true)
        val terminal = store.pendingEvents().single()
        store.recordActionIntent("action", "task-1", "hash")
        store.close()
        store = AutomationStore(context)
        store.markDelivered(terminal.id)
        assertEquals(AutomationStore.STATE_RECONCILING, taskState("task-1"))
        assertTrue(store.hasBlockingHead())
    }

    @Test
    fun `duty yields to a running task via hasActiveTask`() {
        assertFalse(store.hasActiveTask())
        store.enqueueTask("task-duty", "payload", "lease-duty", 0)
        assertNotNull(store.claimNext())
        // Claiming moves the task into RUNNING; the duty controller must treat
        // that as device ownership even though nothing is paused or reconciling.
        assertTrue(store.hasActiveTask())
        store.finish("task-duty", succeeded = true)
        assertFalse(store.hasActiveTask())
    }

    private fun taskState(taskId: String): String = store.readableDatabase.rawQuery(
        "SELECT state FROM task_inbox WHERE task_id=?",
        arrayOf(taskId),
    ).use { cursor ->
        assertTrue(cursor.moveToFirst())
        cursor.getString(0)
    }

    private fun intQuery(sql: String): Int = store.readableDatabase.rawQuery(sql, null).use { cursor ->
        assertTrue(cursor.moveToFirst())
        cursor.getInt(0)
    }

    private companion object {
        const val DATABASE_NAME = "cloudctl-automation.sqlite3"
    }
}
