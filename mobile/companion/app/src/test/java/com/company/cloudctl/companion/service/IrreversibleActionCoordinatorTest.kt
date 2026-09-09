package com.company.cloudctl.companion.service

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.IrreversibleActionGate
import com.company.cloudctl.companion.data.AutomationStore
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class IrreversibleActionCoordinatorTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var coordinator: IrreversibleActionCoordinator

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(DATABASE_NAME)
        store = AutomationStore(context)
        coordinator = IrreversibleActionCoordinator(store)
        store.enqueueTask(TASK_ID, "payload", "lease-1", 0)
        store.claimNext()
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(DATABASE_NAME)
    }

    @Test
    fun `fresh fake action runs once and does not emit reconciling`() = runBlocking {
        val calls = AtomicInteger(0)
        val first = coordinator.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_APPLIED, first.decision)
        assertTrue(first.actionInvoked)
        assertEquals(1, calls.get())
        assertTrue(store.pendingEvents().none { eventType(it.payload) == EVENT })
        assertEquals("RUNNING", inboxState())
        assertFalse(store.hasBlockingHead())

        val second = coordinator.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_SKIPPED_APPLIED, second.decision)
        assertFalse(second.actionInvoked)
        assertEquals(1, calls.get())
        assertTrue(store.pendingEvents().none { eventType(it.payload) == EVENT })
        assertEquals("RUNNING", inboxState())
    }

    @Test
    fun `confirmation loss writes reconciling and stays running not paused`() = runBlocking {
        val calls = AtomicInteger(0)
        val lost = coordinator.executeOnce(
            actionKey = ACTION_KEY,
            taskId = TASK_ID,
            parameterHash = HASH,
            confirmApplied = false,
        ) { calls.incrementAndGet() }

        assertEquals(IrreversibleActionGate.DECISION_UNKNOWN, lost.decision)
        assertTrue(lost.actionInvoked)
        assertEquals(1, calls.get())
        val events = reconcilingEvents()
        assertEquals(1, events.size)
        assertEquals(ACTION_KEY, events.single().getJSONObject("payload").getString("actionKey"))
        assertTrue(events.single().getJSONObject("payload").getBoolean("blockedResume"))
        assertEquals("RUNNING", inboxState())
        assertFalse(store.hasBlockingHead())
    }

    @Test
    fun `restart after unknown does not resume or replay fake action`() = runBlocking {
        val calls = AtomicInteger(0)
        coordinator.executeOnce(
            actionKey = ACTION_KEY,
            taskId = TASK_ID,
            parameterHash = HASH,
            confirmApplied = false,
        ) { calls.incrementAndGet() }

        reopen()

        val blocked = coordinator.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertFalse(blocked.actionInvoked)
        assertEquals(1, calls.get())
        assertEquals("RUNNING", inboxState())
        assertFalse(store.hasBlockingHead())
        assertNullClaim()
        assertTrue(reconcilingEvents().isNotEmpty())
    }

    @Test
    fun `restart with intent requires reconciling and does not invoke action`() = runBlocking {
        val calls = AtomicInteger(0)
        assertEquals("INTENT", store.recordActionIntent(ACTION_KEY, TASK_ID, HASH))
        reopen()

        val blocked = coordinator.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertEquals(IrreversibleActionGate.STATUS_INTENT, blocked.journalStatus)
        assertFalse(blocked.actionInvoked)
        assertEquals(0, calls.get())
        assertEquals("RUNNING", inboxState())
        assertFalse(store.hasBlockingHead())
        val payload = reconcilingEvents().single().getJSONObject("payload")
        assertEquals(ACTION_KEY, payload.getString("actionKey"))
        assertEquals("INTENT", payload.getString("journalStatus"))
    }

    @Test
    fun `gate rejection persists reconciling without invoking action`() = runBlocking {
        val calls = AtomicInteger(0)
        store.recordActionIntent(ACTION_KEY, TASK_ID, HASH)
        val rejected = assertFailsWith<IllegalArgumentException> {
            coordinator.executeOnce(ACTION_KEY, TASK_ID, "hash-other") {
                calls.incrementAndGet()
            }
        }
        assertTrue(rejected.message!!.contains("parameter"))
        assertEquals(0, calls.get())
        assertEquals("RUNNING", inboxState())
        assertFalse(store.hasBlockingHead())
        assertEquals(EVENT, reconcilingEvents().single().getString("eventType"))
    }

    private fun reopen() {
        store.close()
        store = AutomationStore(context)
        coordinator = IrreversibleActionCoordinator(store)
    }

    private fun inboxState(): String =
        store.readableDatabase.rawQuery(
            "SELECT state FROM task_inbox WHERE task_id=?",
            arrayOf(TASK_ID),
        ).use { cursor ->
            assertTrue(cursor.moveToFirst())
            cursor.getString(0)
        }

    private fun assertNullClaim() {
        assertEquals(null, store.claimNext())
    }

    private fun reconcilingEvents() = store.pendingEvents().map { JSONObject(it.payload) }
        .filter { it.optString("eventType") == EVENT }

    private fun eventType(payload: String): String = JSONObject(payload).optString("eventType")

    private companion object {
        const val DATABASE_NAME = "cloudctl-automation.sqlite3"
        const val TASK_ID = "task-1"
        const val ACTION_KEY = "task-1:item-1:fake-action"
        const val HASH = "hash-1"
        const val EVENT = IrreversibleActionCoordinator.EVENT_RECONCILING
    }
}
