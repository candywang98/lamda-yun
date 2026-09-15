package com.company.cloudctl.companion.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Frozen protocol R20260916-P09-18: a fresh claim whose accessibility runtime
 * is unavailable must be releasable back to the cloud queue before any
 * heartbeat or UI work. Release-blocked and start-blocked rows never execute,
 * never upload /fail, and never wedge the claim loop: a replacement lease from
 * the server always requeues them.
 */
@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class AutomationStoreReleaseTest {
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

    private fun state(taskId: String): String = store.readableDatabase
        .rawQuery("SELECT state FROM task_inbox WHERE task_id=?", arrayOf(taskId))
        .use { it.moveToFirst(); it.getString(0) }

    private fun claimedRunning(taskId: String = "task-1"): Pair<String, String> {
        store.enqueueTask(taskId, "payload", "lease-1", 0)
        assertNotNull(store.claimNext())
        assertEquals("RUNNING", state(taskId))
        return taskId to "lease-1"
    }

    private companion object {
        const val DATABASE_NAME = "cloudctl-automation.sqlite3"
    }

    @Test
    fun `release blocked task never executes fails or wedges claiming`() {
        val (taskId, _) = claimedRunning()

        assertTrue(store.markReleaseBlocked(taskId, "ACCESSIBILITY_NOT_ACTIVE"))
        assertFalse(store.markReleaseBlocked(taskId, "ACCESSIBILITY_NOT_ACTIVE"))
        assertEquals("RELEASE_BLOCKED", state(taskId))

        assertNull(store.claimNext())
        assertFalse(store.hasBlockingHead())
        assertFalse(store.hasActiveTask())

        store.finish(taskId, false, "ACCESSIBILITY_NOT_ACTIVE")
        assertTrue(store.pendingEvents().isEmpty())
        assertEquals("RELEASE_BLOCKED", state(taskId))
    }

    @Test
    fun `settled release accepts replacement lease and becomes claimable again`() {
        val (taskId, lease) = claimedRunning()

        store.markReleaseBlocked(taskId, "ACCESSIBILITY_NOT_ENABLED")
        store.settleReleased(taskId, "ACCESSIBILITY_NOT_ENABLED")
        assertEquals("RELEASED", state(taskId))

        assertFalse(store.enqueueTask(taskId, "payload", lease, 0))
        assertEquals("RELEASED", state(taskId))

        assertTrue(store.enqueueTask(taskId, "payload", "lease-2", 5))
        assertEquals("QUEUED", state(taskId))
        val reclaimed = assertNotNull(store.claimNext())
        assertEquals(Pair(taskId, "lease-2"), Pair(reclaimed.taskId, reclaimed.leaseId))
        assertEquals("RUNNING", state(taskId))
    }

    @Test
    fun `release blocked task unblocks via replacement lease after lease expiry`() {
        val (taskId, lease) = claimedRunning()
        store.markReleaseBlocked(taskId, "ACCESSIBILITY_NOT_ACTIVE")

        assertFalse(store.enqueueTask(taskId, "payload", lease, 0))
        assertTrue(store.enqueueTask(taskId, "payload", "lease-2", 7))
        assertEquals("QUEUED", state(taskId))
        assertNotNull(store.claimNext())
        assertEquals("RUNNING", state(taskId))
    }

    @Test
    fun `start blocked task unblocks via replacement lease without failing`() {
        val (taskId, lease) = claimedRunning()

        store.markStartBlocked(taskId, "HEARTBEAT_UNCONFIRMED")
        assertEquals("START_BLOCKED", state(taskId))
        assertNull(store.claimNext())
        assertFalse(store.hasBlockingHead())

        store.finish(taskId, false, "HEARTBEAT_UNCONFIRMED")
        assertTrue(store.pendingEvents().isEmpty())

        assertFalse(store.enqueueTask(taskId, "payload", lease, 0))
        assertTrue(store.enqueueTask(taskId, "payload", "lease-2", 9))
        assertNotNull(store.claimNext())
        assertEquals("RUNNING", state(taskId))
    }

    @Test
    fun `stale blocked row retires so a later queued task still executes`() {
        val (taskId, _) = claimedRunning("task-blocked")
        store.markStartBlocked(taskId, "HEARTBEAT_UNCONFIRMED")
        store.enqueueTask("task-next", "payload-next", "lease-next", 0)

        assertNull(store.claimNext())

        val stale = java.time.Instant.now().minusMillis(AutomationStore.BLOCKED_RETIRE_MILLIS + 60_000).toString()
        store.writableDatabase.execSQL(
            "UPDATE task_inbox SET updated_at=? WHERE task_id=?", arrayOf(stale, taskId),
        )

        val next = assertNotNull(store.claimNext())
        assertEquals("task-next", next.taskId)
        assertEquals("FAILED", state(taskId))
        assertTrue(store.pendingEvents().isEmpty())
    }

    @Test
    fun `release transitions reject unknown or unclaimed tasks`() {
        store.enqueueTask("task-1", "payload", "lease-1", 0)
        assertFailsWith<IllegalArgumentException> {
            store.markReleaseBlocked("task-1", "ACCESSIBILITY_NOT_ENABLED")
        }
        assertFailsWith<IllegalArgumentException> {
            store.settleReleased("task-1", "ACCESSIBILITY_NOT_ENABLED")
        }
        assertFailsWith<IllegalArgumentException> {
            store.markStartBlocked("task-1", "HEARTBEAT_UNCONFIRMED")
        }
        assertFailsWith<IllegalStateException> {
            store.markReleaseBlocked("missing", "ACCESSIBILITY_NOT_ENABLED")
        }
    }
}
