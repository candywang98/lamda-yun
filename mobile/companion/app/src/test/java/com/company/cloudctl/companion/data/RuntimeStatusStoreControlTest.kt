package com.company.cloudctl.companion.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.model.AuthorizedTaskState
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** B17 profile storage: capability self-check + SUSPECT_ORPHANED alert round-trip. */
@RunWith(RobolectricTestRunner::class)
@org.robolectric.annotation.Config(sdk = [35])
class RuntimeStatusStoreControlTest {
    private lateinit var context: Context
    private lateinit var store: RuntimeStatusStore

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.getSharedPreferences("cloudctl_runtime_status", Context.MODE_PRIVATE).edit().clear().commit()
        store = RuntimeStatusStore(context)
    }

    @AfterTest
    fun tearDown() {
        context.getSharedPreferences("cloudctl_runtime_status", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @Test
    fun `capabilities round-trip including unknown state`() {
        store.updateCapabilities(
            mapOf(
                "CAP_ACCESSIBILITY_BOUND" to CapabilityProbeStatus("CAP_ACCESSIBILITY_BOUND", true, "bound"),
                "CAP_ADB_MOTION_INJECTION" to CapabilityProbeStatus("CAP_ADB_MOTION_INJECTION", null, "external"),
            ),
        )
        val snapshot = store.snapshot()
        assertTrue(snapshot.capabilities.getValue("CAP_ACCESSIBILITY_BOUND").detected!!)
        assertNull(snapshot.capabilities.getValue("CAP_ADB_MOTION_INJECTION").detected)
    }

    @Test
    fun `suspect orphaned alert is stored and queryable until cleared`() {
        store.markSuspectOrphaned("task-a", "paused too long, control lag 30")
        val alert = store.snapshot().suspectOrphanedAlert
        assertNotNull(alert)
        assertEquals("task-a", alert.taskId)
        assertTrue(alert.detail.contains("control lag"))

        store.clearSuspectOrphanedAlert()
        assertNull(store.snapshot().suspectOrphanedAlert)
    }

    @Test
    fun `existing task profile fields keep working alongside the new ones`() {
        store.updateTask("task-a", AuthorizedTaskState.Running, "running", "TASK_STARTED")
        val snapshot = store.snapshot()
        assertEquals("task-a", snapshot.task?.taskRunId)
        assertTrue(snapshot.capabilities.isEmpty())
        assertNull(snapshot.suspectOrphanedAlert)
    }
}
