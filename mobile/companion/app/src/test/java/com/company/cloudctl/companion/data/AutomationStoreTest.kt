package com.company.cloudctl.companion.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
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
        val terminal = store.pendingEvents().single()
        assertTrue(terminal.path.endsWith("/fail"))
        assertEquals("FAILED_RESTART", JSONObject(terminal.payload).getString("errorCode"))
        assertEquals("TERMINAL_PENDING_UPLOAD", taskState("task-1"))
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
