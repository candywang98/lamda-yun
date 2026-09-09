package com.company.cloudctl.companion.automation

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.data.AutomationStore
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class IrreversibleActionGateTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    private lateinit var gate: IrreversibleActionGate

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(DATABASE_NAME)
        store = AutomationStore(context)
        gate = IrreversibleActionGate(store)
        store.enqueueTask(TASK_ID, "payload", "lease-1", 0)
        store.claimNext()
    }

    @AfterTest
    fun tearDown() {
        store.close()
        context.deleteDatabase(DATABASE_NAME)
    }

    @Test
    fun `fresh intent invokes injected action once and confirms applied`() = runBlocking {
        val calls = AtomicInteger(0)
        val first = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_APPLIED, first.decision)
        assertEquals(IrreversibleActionGate.STATUS_APPLIED, first.journalStatus)
        assertTrue(first.actionInvoked)
        assertEquals(1, calls.get())

        val second = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_SKIPPED_APPLIED, second.decision)
        assertEquals(IrreversibleActionGate.STATUS_APPLIED, second.journalStatus)
        assertFalse(second.actionInvoked)
        assertEquals(1, calls.get())
    }

    @Test
    fun `applied journal skips without invoking action after reopen`() = runBlocking {
        val calls = AtomicInteger(0)
        gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(1, calls.get())

        store.close()
        store = AutomationStore(context)
        gate = IrreversibleActionGate(store)

        val skipped = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(IrreversibleActionGate.DECISION_SKIPPED_APPLIED, skipped.decision)
        assertEquals(IrreversibleActionGate.STATUS_APPLIED, skipped.journalStatus)
        assertFalse(skipped.actionInvoked)
        assertEquals(1, calls.get())
    }

    @Test
    fun `existing intent requires reconciliation and never invokes again`() = runBlocking {
        val calls = AtomicInteger(0)
        assertEquals("INTENT", store.recordActionIntent(ACTION_KEY, TASK_ID, HASH))

        val blocked = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertEquals(IrreversibleActionGate.STATUS_INTENT, blocked.journalStatus)
        assertFalse(blocked.actionInvoked)
        assertEquals(0, calls.get())
    }

    @Test
    fun `unknown journal requires reconciliation and never invokes again`() = runBlocking {
        val calls = AtomicInteger(0)
        store.recordActionIntent(ACTION_KEY, TASK_ID, HASH)
        store.markActionUnknown(ACTION_KEY)

        val blocked = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertEquals(IrreversibleActionGate.STATUS_UNKNOWN, blocked.journalStatus)
        assertFalse(blocked.actionInvoked)
        assertEquals(0, calls.get())
    }

    @Test
    fun `identity or parameter mismatch is rejected without invoking action`() = runBlocking {
        val calls = AtomicInteger(0)
        store.recordActionIntent(ACTION_KEY, TASK_ID, HASH)

        assertFailsWith<IllegalArgumentException> {
            gate.executeOnce(ACTION_KEY, TASK_ID, "hash-changed") { calls.incrementAndGet() }
        }
        store.enqueueTask("task-other", "payload-other", "lease-2", 0)
        store.claimNext()
        assertFailsWith<IllegalArgumentException> {
            gate.executeOnce(ACTION_KEY, "task-other", HASH) { calls.incrementAndGet() }
        }
        assertEquals(0, calls.get())
        assertEquals(IrreversibleActionGate.STATUS_INTENT, store.actionJournal(ACTION_KEY)!!.status)
        assertEquals(TASK_ID, store.actionJournal(ACTION_KEY)!!.taskId)
        assertEquals(HASH, store.actionJournal(ACTION_KEY)!!.parameterHash)
    }

    @Test
    fun `action throw keeps unknown and second call does not invoke`() = runBlocking {
        val calls = AtomicInteger(0)
        val failed = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) {
            calls.incrementAndGet()
            error("injected failure")
        }
        assertEquals(IrreversibleActionGate.DECISION_UNKNOWN, failed.decision)
        assertEquals(IrreversibleActionGate.STATUS_UNKNOWN, failed.journalStatus)
        assertTrue(failed.actionInvoked)
        assertEquals(1, calls.get())

        val blocked = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertEquals(IrreversibleActionGate.STATUS_UNKNOWN, blocked.journalStatus)
        assertFalse(blocked.actionInvoked)
        assertEquals(1, calls.get())
    }

    @Test
    fun `timeout keeps unknown and does not replay after reopen`() = runBlocking {
        val calls = AtomicInteger(0)
        val timedOut = gate.executeOnce(ACTION_KEY, TASK_ID, HASH, timeoutMs = 40L) {
            calls.incrementAndGet()
            delay(200L)
        }
        assertEquals(IrreversibleActionGate.DECISION_UNKNOWN, timedOut.decision)
        assertEquals(IrreversibleActionGate.STATUS_UNKNOWN, timedOut.journalStatus)
        assertTrue(timedOut.actionInvoked)
        assertEquals(1, calls.get())

        store.close()
        store = AutomationStore(context)
        gate = IrreversibleActionGate(store)

        val blocked = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertFalse(blocked.actionInvoked)
        assertEquals(1, calls.get())
    }

    @Test
    fun `confirmation loss after action stays unknown and is not replayed`() = runBlocking {
        val calls = AtomicInteger(0)
        val lost = gate.executeOnce(
            actionKey = ACTION_KEY,
            taskId = TASK_ID,
            parameterHash = HASH,
            confirmApplied = false,
        ) {
            calls.incrementAndGet()
        }
        assertEquals(IrreversibleActionGate.DECISION_UNKNOWN, lost.decision)
        assertEquals(IrreversibleActionGate.STATUS_UNKNOWN, lost.journalStatus)
        assertTrue(lost.actionInvoked)
        assertEquals(1, calls.get())

        store.close()
        store = AutomationStore(context)
        gate = IrreversibleActionGate(store)

        val blocked = gate.executeOnce(ACTION_KEY, TASK_ID, HASH) { calls.incrementAndGet() }
        assertEquals(IrreversibleActionGate.DECISION_RECONCILE_REQUIRED, blocked.decision)
        assertEquals(IrreversibleActionGate.STATUS_UNKNOWN, blocked.journalStatus)
        assertFalse(blocked.actionInvoked)
        assertEquals(1, calls.get())
    }

    private companion object {
        const val DATABASE_NAME = "cloudctl-automation.sqlite3"
        const val TASK_ID = "task-1"
        const val ACTION_KEY = "task-1:item-1:fake-action"
        const val HASH = "hash-1"
    }
}
