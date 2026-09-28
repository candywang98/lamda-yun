package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.network.ClaimedTask
import com.company.cloudctl.companion.network.CloudHttpException
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlin.test.fail

class ClaimMaintenanceRecoveryTest {
    @Test
    fun exactStructuredMaintenanceDenialDefersWithoutLocalSideEffects() = runBlocking {
        val recording = Recording()

        val result = runSyncClaimPass(
            claimRequest = { throw maintenanceDenied() },
            acceptClaim = recording::accept,
            executeLocal = recording::execute,
            deferMaintenance = recording::defer,
        )

        assertIs<SyncClaimPassResult.MaintenanceDeferred>(result)
        assertEquals(0, recording.enqueued)
        assertEquals(0, recording.finished)
        assertEquals(0, recording.executed)
        assertEquals(1, recording.deferred)
    }

    @Test
    fun laterOrdinaryClaimUsesNormalAcceptanceAndExecutionPath() = runBlocking {
        val recording = Recording()
        var attempts = 0
        val request: suspend () -> ClaimedTask? = {
            attempts += 1
            if (attempts == 1) throw maintenanceDenied() else CLAIMED_TASK
        }

        assertIs<SyncClaimPassResult.MaintenanceDeferred>(
            runSyncClaimPass(request, recording::accept, recording::execute, recording::defer),
        )
        val recovered = assertIs<SyncClaimPassResult.Completed>(
            runSyncClaimPass(request, recording::accept, recording::execute, recording::defer),
        )

        assertSame(CLAIMED_TASK, recovered.claimed)
        assertTrue(recovered.executed)
        assertEquals(1, recording.enqueued)
        assertEquals(1, recording.executed)
        assertEquals(0, recording.finished)
        assertEquals(1, recording.deferred)
    }

    @Test
    fun noCloudClaimStillRunsExistingLocalQueuePath() = runBlocking {
        val recording = Recording()

        val result = assertIs<SyncClaimPassResult.Completed>(
            runSyncClaimPass(null, recording::accept, recording::execute, recording::defer),
        )

        assertEquals(null, result.claimed)
        assertTrue(result.executed)
        assertEquals(0, recording.enqueued)
        assertEquals(1, recording.executed)
    }

    @Test
    fun rejectedAcceptedClaimPreservesContinueWithoutLocalExecution() = runBlocking {
        val recording = Recording(acceptResult = false)

        val result = runSyncClaimPass(
            claimRequest = { CLAIMED_TASK },
            acceptClaim = recording::accept,
            executeLocal = recording::execute,
            deferMaintenance = recording::defer,
        )

        assertIs<SyncClaimPassResult.ClaimRejected>(result)
        assertEquals(1, recording.enqueued)
        assertEquals(0, recording.executed)
        assertEquals(0, recording.deferred)
    }

    @Test
    fun maintenanceShapedFailuresFromAcceptOrExecutionRemainRejected() = runBlocking {
        val acceptFailure = maintenanceDenied()
        val caughtAccept = try {
            runSyncClaimPass(
                claimRequest = { CLAIMED_TASK },
                acceptClaim = { throw acceptFailure },
                executeLocal = { fail("local execution must not run") },
                deferMaintenance = { fail("accept failure must not defer") },
            )
            fail("expected accept failure")
        } catch (caught: CloudHttpException) {
            caught
        }
        assertSame(acceptFailure, caughtAccept)

        val executeFailure = maintenanceDenied()
        val caughtExecute = try {
            runSyncClaimPass(
                claimRequest = null,
                acceptClaim = { fail("no cloud claim should be accepted") },
                executeLocal = { throw executeFailure },
                deferMaintenance = { fail("execution failure must not defer") },
            )
            fail("expected execution failure")
        } catch (caught: CloudHttpException) {
            caught
        }
        assertSame(executeFailure, caughtExecute)
    }

    @Test
    fun missingWrongExtraAndMalformedDetailsRemainRejected() = runBlocking {
        listOf(
            "{}",
            "{\"detail\":\"another conflict\"}",
            "{\"detail\":\"$MAINTENANCE_DETAIL\",\"extra\":true}",
            "{\"detail\":null}",
            "not-json",
        ).forEach { body ->
            assertPassRethrows(CloudHttpException(409, body))
        }
    }

    @Test
    fun wrongStatusAndUnrelated409RemainRejected() = runBlocking {
        assertPassRethrows(CloudHttpException(422, maintenanceBody()))
        assertPassRethrows(CloudHttpException(409, "{\"detail\":\"DEVICE_REMOTE\"}"))
    }

    @Test
    fun authenticationErrorsRemainAuthenticationErrors() = runBlocking {
        listOf(401, 403).forEach { status ->
            val error = CloudHttpException(status, maintenanceBody())
            assertTrue(error.authenticationRejected)
            assertSame(error, capturePassFailure(error))
        }
    }

    @Test
    fun maintenanceBodyIsNotSpecialOutsideClaimEndpoint() {
        assertFalse(
            isExactMaintenanceClaimDenial(
                endpoint = "/companion/v2/devices/heartbeat",
                error = maintenanceDenied(),
            ),
        )
    }

    private suspend fun assertPassRethrows(error: CloudHttpException) {
        assertSame(error, capturePassFailure(error))
    }

    private suspend fun capturePassFailure(error: CloudHttpException): CloudHttpException {
        return try {
            runSyncClaimPass(
                claimRequest = { throw error },
                acceptClaim = { fail("claim must not be accepted") },
                executeLocal = { fail("local execution must not run") },
                deferMaintenance = { fail("non-maintenance errors must not defer") },
            )
            fail("expected CloudHttpException")
        } catch (caught: CloudHttpException) {
            caught
        }
    }

    private class Recording(
        private val acceptResult: Boolean = true,
    ) {
        var enqueued = 0
        var finished = 0
        var executed = 0
        var deferred = 0

        suspend fun accept(task: ClaimedTask): Boolean {
            assertSame(CLAIMED_TASK, task)
            enqueued += 1
            return acceptResult
        }

        suspend fun execute(): Boolean {
            executed += 1
            return true
        }

        suspend fun defer() {
            deferred += 1
        }
    }

    private companion object {
        const val MAINTENANCE_DETAIL = "device is in maintenance and cannot claim tasks"
        val CLAIMED_TASK = ClaimedTask("{}", "task-1", "device-1", "lease-1", 0)

        fun maintenanceBody(): String = "{\"detail\":\"$MAINTENANCE_DETAIL\"}"

        fun maintenanceDenied(): CloudHttpException = CloudHttpException(409, maintenanceBody())
    }
}
