package com.company.cloudctl.companion.runtime

import com.company.cloudctl.companion.service.AccessibilityRuntimeReadiness
import com.company.cloudctl.companion.service.FreshClaimAccessibility
import com.company.cloudctl.companion.service.FreshClaimExecutionCoordinator
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * B10 acceptance 3: after a claim, an accessibility disconnect in the
 * uncommitted window goes through the P09-19 frozen release (only
 * CLAIMED/PREFLIGHT and before the first heartbeat → back to QUEUED). The
 * task is not lost and nothing loops: the release strikes exactly once, the
 * arbiter never began a task session, and the server redelivery can mint a
 * fresh session.
 */
class FreshClaimReleaseSeamTest {

    private class ReleaseRecorder {
        val releases = mutableListOf<String>()
        val settled = mutableListOf<String>()
    }

    @Test
    fun releasePolicyAllowsOnlyTheFrozenClaimWindow() {
        // CLAIMED/PREFLIGHT, nothing confirmed or committed yet.
        assertTrue(ReleasePolicy.canReleaseBackToQueue(firstHeartbeatConfirmed = false, hasCommittedWrite = false))
        // First heartbeat confirmed → the lease lifecycle owns the outcome.
        assertFalse(ReleasePolicy.canReleaseBackToQueue(firstHeartbeatConfirmed = true, hasCommittedWrite = false))
        // Any committed (irreversible) write → reconcile path, never release.
        assertFalse(ReleasePolicy.canReleaseBackToQueue(firstHeartbeatConfirmed = false, hasCommittedWrite = true))
        assertFalse(ReleasePolicy.canReleaseBackToQueue(firstHeartbeatConfirmed = true, hasCommittedWrite = true))
    }

    @Test
    fun accessibilityDisconnectAfterClaimReleasesOnceWithoutLooping() = runBlocking {
        val arbiter = DeviceArbiter()
        val recorder = ReleaseRecorder()
        val service = Any()

        // Claim lands; duty writes are still legal (no execution started).
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.TAP) is ArbiterDecision.Allowed)

        // The accessibility runtime drops before any heartbeat or UI write:
        // the real fresh-claim coordinator drives the release seam.
        val coordinator = FreshClaimExecutionCoordinator<Any>(
            awaitAccessibility = { AccessibilityRuntimeReadiness.NotEnabled },
            markReleaseBlocked = { true },
            release = { reason -> recorder.releases += reason },
            settleReleased = { reason -> recorder.settled += reason },
        )
        val outcome = coordinator.acquire()

        assertEquals("ACCESSIBILITY_NOT_ENABLED", assertIs<FreshClaimAccessibility.Released>(outcome).reason)
        // Released exactly once and settled — no retry storm, no local requeue.
        assertEquals(listOf("ACCESSIBILITY_NOT_ENABLED"), recorder.releases)
        assertEquals(listOf("ACCESSIBILITY_NOT_ENABLED"), recorder.settled)

        // No task session was ever begun: the device stayed free…
        assertFalse(arbiter.hasActiveTaskSession())
        // …so duty (and a later redelivered claim) are unaffected.
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.TAP) is ArbiterDecision.Allowed)

        // The server redelivers after lease expiry: a fresh claim mints a
        // fresh epoch/session and executes normally.
        val epochBefore = arbiter.controlEpoch
        val session = arbiter.beginTaskSession("task-redelivered")
        assertTrue(session.fencingToken > epochBefore)
        assertTrue(arbiter.request(UiWriter.TASK, UiWriteKind.TAP, session.fencingToken) is ArbiterDecision.Allowed)
        assertTrue(arbiter.request(UiWriter.IM_DUTY, UiWriteKind.TAP) is ArbiterDecision.Denied)
        assertTrue(arbiter.endTaskSession(session.fencingToken, ReleaseBoundary.COMPLETED))
    }

    @Test
    fun readyClaimExecutesWithoutTouchingTheReleaseSeam() = runBlocking {
        val recorder = ReleaseRecorder()
        val coordinator = FreshClaimExecutionCoordinator<Any>(
            awaitAccessibility = { AccessibilityRuntimeReadiness.Ready(Any()) },
            markReleaseBlocked = { false },
            release = { reason -> recorder.releases += reason },
            settleReleased = { reason -> recorder.settled += reason },
        )
        val outcome = coordinator.acquire()
        assertIs<FreshClaimAccessibility.Ready<Any>>(outcome)
        assertTrue(recorder.releases.isEmpty())
        assertTrue(recorder.settled.isEmpty())
    }
}
