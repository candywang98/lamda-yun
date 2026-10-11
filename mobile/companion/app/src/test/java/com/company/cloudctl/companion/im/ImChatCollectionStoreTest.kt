package com.company.cloudctl.companion.im

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.data.AutomationStore
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.test.*

@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class ImChatCollectionStoreTest {
    private lateinit var context: Context
    private lateinit var store: AutomationStore
    @BeforeTest fun setup() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase("cloudctl-automation.sqlite3")
        store = AutomationStore(context)
        assertTrue(store.enqueueTask("task-collect", CollectionFixture.payload().toString(), "lease-1", 0))
        assertNotNull(store.claimNext())
    }
    @AfterTest fun close() { store.close(); context.deleteDatabase("cloudctl-automation.sqlite3") }
    private fun capture() = store.finishImChatCollection("task-collect", "lease-1", CollectionFixture.target, CollectionFixture.snapshot())
    private fun events() = store.pendingEvents()
    @Test fun captureAtomicallyPersistsTypedTerminalAndNeverGenericComplete() {
        capture()
        val terminal = events().single { it.path.endsWith(":complete") }
        val body = JSONObject(terminal.payload)
        assertEquals("lease-1", body.getString("leaseId"))
        assertEquals(7L, body.getLong("controlEpoch"))
        assertEquals(CollectionFixture.target.toJson().toString(), body.getJSONObject("target").toString())
        assertEquals("UNVERIFIED", body.getJSONObject("snapshot").getString("accountIdentity"))
        assertEquals(AutomationStore.STATE_TERMINAL_PENDING, store.taskExecutionState("task-collect"))
        assertFalse(events().any { it.path.endsWith("/complete") })
    }
    @Test fun restartAndSameLeaseRedeliveryReplayIdenticalSnapshot() {
        capture()
        val before = events().map { it.path to it.payload }
        store.close(); store = AutomationStore(context); store.recoverInterruptedRuns()
        assertFalse(store.enqueueTask("task-collect", CollectionFixture.payload().toString(), "lease-1", 0))
        assertNull(store.claimNext())
        assertEquals(before, events().map { it.path to it.payload })
    }
    @Test fun genericSuccessWithoutSnapshotIsRejected() {
        assertFailsWith<IllegalArgumentException> { store.finish("task-collect", true) }
        assertFalse(events().any { it.path.endsWith("/complete") || it.path.endsWith(":complete") })
    }
    @Test fun lateFailureAndGenericFinishCannotOverwriteCapturedSuccess() {
        capture(); val before = events().map { it.path to it.payload }
        store.finish("task-collect", true)
        store.finish("task-collect", false, "CANCELLED")
        assertEquals(before, events().map { it.path to it.payload })
    }
    @Test fun replacementLeaseCannotReauthorizeSnapshotOrGenericSuccess() {
        capture()
        assertFalse(store.enqueueTask("task-collect", CollectionFixture.payload(8).toString(), "lease-2", 0))
        val remaining = events()
        assertEquals(1, remaining.size)
        assertTrue(remaining.single().path.endsWith("/fail"))
        val body = JSONObject(remaining.single().payload)
        assertEquals("IM_COLLECTION_LEASE_REPLACED", body.getString("errorCode"))
        assertEquals("lease-2", body.getString("leaseId"))
        assertFalse(remaining.any { it.path.endsWith("complete") })
    }
    @Test fun wrongLeaseOrTargetCannotPartiallyPersistCapture() {
        assertFails { store.finishImChatCollection("task-collect", "wrong", CollectionFixture.target, CollectionFixture.snapshot()) }
        assertFails { store.finishImChatCollection("task-collect", "lease-1", CollectionFixture.target.copy(peerName = "other"), CollectionFixture.snapshot()) }
        assertEquals(AutomationStore.STATE_RUNNING, store.taskExecutionState("task-collect"))
        assertTrue(events().isEmpty())
    }
    @Test fun terminalSnapshotDeliveryConfirmationSurvivesRestart() {
        capture(); events().forEach { store.markDelivered(it.id) }
        store.close(); store = AutomationStore(context)
        assertEquals(AutomationStore.STATE_TERMINAL_CONFIRMED, store.taskExecutionState("task-collect"))
        assertTrue(events().isEmpty())
    }
    @Test fun targetChangeWithSameTaskIsRejectedButEpochIsDynamic() {
        val changed = CollectionFixture.payload().apply {
            getJSONArray("steps").getJSONObject(0).getJSONObject("target").put("peerName", "other")
        }
        assertFails { store.enqueueTask("task-collect", changed.toString(), "lease-2", 0) }
        assertTrue(AutomationStore.sameExecutionPayload(CollectionFixture.payload().toString(), CollectionFixture.payload(8).toString()))
    }
}
