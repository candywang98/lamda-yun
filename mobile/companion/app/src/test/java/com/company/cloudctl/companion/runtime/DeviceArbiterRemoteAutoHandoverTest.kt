package com.company.cloudctl.companion.runtime

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B10 acceptance 2: a remote->auto handover must ack and advance the control
 * epoch; late remote commands carrying the superseded epoch are rejected and
 * never land (fleet-identity/v1@20260916.1 §4/§6).
 */
class DeviceArbiterRemoteAutoHandoverTest {
    private val arbiter = DeviceArbiter()

    @Test
    fun remoteGrantEpochGatesItsOwnCommands() {
        val granted = arbiter.beginRemoteSession()

        assertTrue(arbiter.request(UiWriter.REMOTE_LIVE, UiWriteKind.TAP, granted) is ArbiterDecision.Allowed)
        // An arbitrary other epoch is a late/foreign command.
        val stale = arbiter.request(UiWriter.REMOTE_LIVE, UiWriteKind.TAP, granted + 1)
        assertEquals(ArbiterDenialReason.EPOCH_STALE, assertIs<ArbiterDecision.Denied>(stale).reason)

        assertTrue(arbiter.endRemoteSession(granted))
        assertFalse(arbiter.endRemoteSession(granted))
    }

    @Test
    fun handoverAcksRemoteEpochAndAdvancesControlEpoch() {
        val granted = arbiter.beginRemoteSession()
        val epochBefore = arbiter.controlEpoch

        val session = arbiter.beginTaskSession("task-1")

        // The ack records the acknowledged remote grant and the new epoch,
        // and the task fencing token is minted from the new epoch.
        val ack = assertNotNull(session.handoverAck)
        assertEquals("task-1", ack.taskId)
        assertEquals(granted, ack.ackedRemoteEpoch)
        assertEquals(ack.controlEpoch, arbiter.controlEpoch)
        assertEquals(ack.controlEpoch, session.fencingToken)
        assertTrue(ack.controlEpoch > epochBefore)
        assertNull(ack.ackedEdgeEpoch)
        // The remote grant itself is gone.
        assertNull(arbiter.activeRemoteSessionEpoch())
    }

    @Test
    fun lateRemoteCommandAfterHandoverNeverLands() {
        val granted = arbiter.beginRemoteSession()
        val session = arbiter.beginTaskSession("task-1")
        val ops = RecordingOps()
        ArbiterGuardedUiExecutionPort(arbiter, ops).apply {
            // Late command from the superseded remote session.
            assertFalse(submitGestureTap(UiWriter.REMOTE_LIVE, 540.0, 1200.0, epoch = granted))
            assertFalse(submitGestureSwipe(UiWriter.REMOTE_LIVE, 100.0, 100.0, 200.0, 200.0, epoch = granted))
            // The new owner still writes.
        }
        assertEquals(0, ops.taps.size)
        assertEquals(0, ops.swipes.size)

        // Task writes with the fresh token pass through the same port.
        val taskOps = RecordingOps()
        ArbiterGuardedUiExecutionPort(arbiter, taskOps).apply {
            assertTrue(submitGestureTap(UiWriter.TASK, 540.0, 1200.0, epoch = session.fencingToken))
        }
        assertEquals(listOf(540.0 to 1200.0), taskOps.taps)

        // Denials are recorded: two late remote commands.
        val lateDenials = arbiter.denials().filter { it.writer == UiWriter.REMOTE_LIVE }
        assertEquals(2, lateDenials.size)
        assertTrue(lateDenials.all { it.reason == ArbiterDenialReason.EPOCH_STALE })
    }

    @Test
    fun remoteMustReapplyAfterTheTaskFinishes() {
        val granted = arbiter.beginRemoteSession()
        val session = arbiter.beginTaskSession("task-1")
        assertTrue(arbiter.endTaskSession(session.fencingToken, ReleaseBoundary.COMPLETED))

        // The old remote epoch stays dead after the task finishes…
        val stale = arbiter.request(UiWriter.REMOTE_LIVE, UiWriteKind.TAP, granted)
        assertEquals(ArbiterDenialReason.EPOCH_STALE, assertIs<ArbiterDecision.Denied>(stale).reason)
        // …a fresh take-control gets a fresh epoch.
        val regranted = arbiter.beginRemoteSession()
        assertTrue(regranted > granted)
        assertTrue(arbiter.request(UiWriter.REMOTE_LIVE, UiWriteKind.TAP, regranted) is ArbiterDecision.Allowed)
    }

    private class RecordingOps : RawUiOps {
        val taps = mutableListOf<Pair<Double, Double>>()
        val swipes = mutableListOf<Pair<Double, Double>>()
        var launches = 0
        var backs = 0
        var texts = 0

        override suspend fun launchTargetApp(targetPackage: String) {
            launches++
        }

        override fun globalBack() {
            backs++
        }

        override fun submitGestureTap(x: Double, y: Double) {
            taps += x to y
        }

        override fun submitGestureSwipe(x1: Double, y1: Double, x2: Double, y2: Double) {
            swipes += x1 to x2
        }

        override suspend fun replaceText(targetPackage: String, locatorRef: String, value: String) {
            texts++
        }
    }
}
