package com.company.cloudctl.companion.runtime

import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * B10 acceptance 1 (fleet-identity/v1@20260916.1 §6.3): while a RUNNING task
 * holds the device, IM duty cannot launch / back / tap / edit an input —
 * every write family is rejected by the single arbiter AND recorded.
 */
class DeviceArbiterSingleWriterTest {
    private val arbiter = DeviceArbiter()

    @AfterTest
    fun tearDown() {
        arbiter.clearRecordedDenials()
    }

    @Test
    fun dutyCannotLaunchBackTapOrTypeWhileTaskRunning() {
        val session = arbiter.beginTaskSession("task-1")

        val dutyKinds = listOf(
            UiWriteKind.LAUNCH,
            UiWriteKind.BACK,
            UiWriteKind.TAP,
            UiWriteKind.TEXT_INPUT,
            UiWriteKind.SWIPE,
        )
        dutyKinds.forEach { kind ->
            val decision = arbiter.request(UiWriter.IM_DUTY, kind, detail = "duty $kind")
            val denied = assertIs<ArbiterDecision.Denied>(decision)
            assertEquals(ArbiterDenialReason.DEVICE_BUSY, denied.reason)
        }

        // Rejected AND recorded, in order, with the writer/kind/reason triple.
        val recorded = arbiter.denials()
        assertEquals(dutyKinds.size, recorded.size)
        assertEquals(dutyKinds, recorded.map { it.kind })
        assertTrue(recorded.all { it.writer == UiWriter.IM_DUTY })
        assertTrue(recorded.all { it.reason == ArbiterDenialReason.DEVICE_BUSY })
        assertTrue(recorded.all { it.controlEpoch == session.fencingToken })

        // The owning task still writes with its fencing token.
        assertTrue(arbiter.request(UiWriter.TASK, UiWriteKind.TAP, session.fencingToken) is ArbiterDecision.Allowed)
        // A task write with a stale token never lands.
        val stale = arbiter.request(UiWriter.TASK, UiWriteKind.TAP, session.fencingToken + 1)
        assertEquals(ArbiterDenialReason.EPOCH_STALE, assertIs<ArbiterDecision.Denied>(stale).reason)
    }

    @Test
    fun remoteAndEdgeAreAlsoRejectedWhileTaskRunning() {
        arbiter.beginTaskSession("task-1")

        listOf(UiWriter.REMOTE_LIVE, UiWriter.EDGE).forEach { writer ->
            val decision = arbiter.request(writer, UiWriteKind.TAP, fencingToken = 1L)
            assertEquals(
                ArbiterDenialReason.DEVICE_BUSY,
                assertIs<ArbiterDecision.Denied>(decision).reason,
            )
        }
        assertEquals(2, arbiter.denials().size)
    }

    @Test
    fun dutyWritesResumeAfterTheTaskReturnsAtASafeBoundary() {
        val session = arbiter.beginTaskSession("task-1")
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.TAP) is ArbiterDecision.Denied)
        assertTrue(arbiter.endTaskSession(session.fencingToken, ReleaseBoundary.COMPLETED))

        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.LAUNCH) is ArbiterDecision.Allowed)
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.BACK) is ArbiterDecision.Allowed)
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.TAP) is ArbiterDecision.Allowed)
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.TEXT_INPUT) is ArbiterDecision.Allowed)
    }

    @Test
    fun lateTaskWriteAfterCancelBoundaryIsRejectedNotLanded() {
        val session = arbiter.beginTaskSession("task-1")
        assertTrue(arbiter.endTaskSession(session.fencingToken, ReleaseBoundary.CANCELLED))

        // A straggler write from the cancelled run presents the dead token.
        val stale = arbiter.request(UiWriter.TASK, UiWriteKind.TAP, session.fencingToken)
        assertEquals(ArbiterDenialReason.EPOCH_STALE, assertIs<ArbiterDecision.Denied>(stale).reason)
        // And with no session at all there is nothing to hold the device.
        val orphan = arbiter.request(UiWriter.TASK, UiWriteKind.TAP)
        assertEquals(ArbiterDenialReason.NOT_HOLDER, assertIs<ArbiterDecision.Denied>(orphan).reason)
    }

    @Test
    fun duplicateOrStaleReleaseNeverFreesASuccessorSession() {
        val first = arbiter.beginTaskSession("task-1")
        assertTrue(arbiter.endTaskSession(first.fencingToken, ReleaseBoundary.COMPLETED))
        // A late second release is a no-op…
        assertFalse(arbiter.endTaskSession(first.fencingToken, ReleaseBoundary.CANCELLED))
        // …and cannot free the next task's session.
        val second = arbiter.beginTaskSession("task-2")
        assertFalse(arbiter.endTaskSession(first.fencingToken, ReleaseBoundary.CANCELLED))
        assertTrue(arbiter.hasActiveTaskSession())
        assertTrue(arbiter.endTaskSession(second.fencingToken, ReleaseBoundary.COMPLETED))
        assertFalse(arbiter.hasActiveTaskSession())
    }

    @Test
    fun denialRecordIsBounded() {
        val small = DeviceArbiter(maxRecordedDenials = 3)
        val session = small.beginTaskSession("task-1")
        repeat(10) {
            assertTrue(small.request(UiWriter.IM_DUTY, UiWriteKind.TAP) is ArbiterDecision.Denied)
        }
        assertEquals(3, small.denials().size)
        assertTrue(session.handoverAck == null)
    }
}
