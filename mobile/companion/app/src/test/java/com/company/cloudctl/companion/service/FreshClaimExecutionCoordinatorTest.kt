package com.company.cloudctl.companion.service

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class FreshClaimExecutionCoordinatorTest {
    private val service = Any()

    private fun coordinator(
        readiness: AccessibilityRuntimeReadiness<Any>,
        markResult: Boolean = true,
        releaseError: Exception? = null,
    ): Pair<FreshClaimExecutionCoordinator<Any>, Recording> {
        val recording = Recording(markResult, releaseError)
        val coordinator = FreshClaimExecutionCoordinator(
            awaitAccessibility = { readiness },
            markReleaseBlocked = { reason -> recording.marked += reason; recording.markResult },
            release = { reason ->
                recording.releases += reason
                recording.releaseError?.let { throw it }
            },
            settleReleased = { reason -> recording.settled += reason },
        )
        return coordinator to recording
    }

    private class Recording(
        val markResult: Boolean,
        val releaseError: Exception?,
    ) {
        val marked = mutableListOf<String>()
        val releases = mutableListOf<String>()
        val settled = mutableListOf<String>()
    }

    @Test
    fun readyRuntimeExecutesNoRelease() = kotlinx.coroutines.runBlocking {
        val (coordinator, recording) = coordinator(AccessibilityRuntimeReadiness.Ready(service))

        val outcome = coordinator.acquire()

        assertEquals(service, assertIs<FreshClaimAccessibility.Ready<Any>>(outcome).service)
        assertTrue(recording.marked.isEmpty())
        assertTrue(recording.releases.isEmpty())
        assertTrue(recording.settled.isEmpty())
    }

    @Test
    fun disabledRuntimeReleasesOnceAndSettles() = kotlinx.coroutines.runBlocking {
        val (coordinator, recording) = coordinator(AccessibilityRuntimeReadiness.NotEnabled)

        val outcome = coordinator.acquire()

        assertEquals(
            "ACCESSIBILITY_NOT_ENABLED",
            assertIs<FreshClaimAccessibility.Released>(outcome).reason,
        )
        assertEquals(listOf("ACCESSIBILITY_NOT_ENABLED"), recording.marked)
        assertEquals(listOf("ACCESSIBILITY_NOT_ENABLED"), recording.releases)
        assertEquals(listOf("ACCESSIBILITY_NOT_ENABLED"), recording.settled)
    }

    @Test
    fun inactiveRuntimeReleasesWithActiveReason() = kotlinx.coroutines.runBlocking {
        val (coordinator, recording) = coordinator(AccessibilityRuntimeReadiness.NotActive)

        val outcome = coordinator.acquire()

        assertEquals(
            "ACCESSIBILITY_NOT_ACTIVE",
            assertIs<FreshClaimAccessibility.Released>(outcome).reason,
        )
        assertEquals(listOf("ACCESSIBILITY_NOT_ACTIVE"), recording.releases)
    }

    @Test
    fun releaseFailureKeepsTaskBlockedWithoutSettling() = kotlinx.coroutines.runBlocking {
        val failure = java.io.IOException("network down")
        val (coordinator, recording) = coordinator(
            AccessibilityRuntimeReadiness.NotEnabled,
            releaseError = failure,
        )

        val outcome = coordinator.acquire()

        val blocked = assertIs<FreshClaimAccessibility.ReleaseBlocked>(outcome)
        assertEquals("ACCESSIBILITY_NOT_ENABLED", blocked.reason)
        assertEquals(failure, blocked.error)
        assertTrue(recording.settled.isEmpty())
    }

    @Test
    fun settleFailureAfterSuccessfulReleaseReportsBlockedButNeverRestrikes() = runBlocking {
        val recording = Recording(markResult = true, releaseError = null)
        val coordinator = FreshClaimExecutionCoordinator(
            awaitAccessibility = { AccessibilityRuntimeReadiness.NotEnabled },
            markReleaseBlocked = { reason -> recording.marked += reason; true },
            release = { reason -> recording.releases += reason },
            settleReleased = { throw java.io.IOException("local settle failed") },
        )

        val outcome = coordinator.acquire()

        val blocked = assertIs<FreshClaimAccessibility.ReleaseBlocked>(outcome)
        assertEquals("ACCESSIBILITY_NOT_ENABLED", blocked.reason)
        // The server release succeeded exactly once; recovery is redelivery.
        assertEquals(listOf("ACCESSIBILITY_NOT_ENABLED"), recording.releases)
    }

    @Test
    fun rejectedMarkSkipsReleaseEntirely() = kotlinx.coroutines.runBlocking {
        val (coordinator, recording) = coordinator(
            AccessibilityRuntimeReadiness.NotEnabled,
            markResult = false,
        )

        val outcome = coordinator.acquire()

        val blocked = assertIs<FreshClaimAccessibility.ReleaseBlocked>(outcome)
        assertEquals("ACCESSIBILITY_NOT_ENABLED", blocked.reason)
        assertNull(blocked.error)
        assertTrue(recording.releases.isEmpty())
        assertTrue(recording.settled.isEmpty())
    }
}
