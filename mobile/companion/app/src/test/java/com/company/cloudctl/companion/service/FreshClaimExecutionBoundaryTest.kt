package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.ExecutorFailure
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertEquals
import kotlin.test.assertIs

class FreshClaimExecutionBoundaryTest {
    @Test
    fun confirmedHeartbeatRunsExecutionExactlyOnce() = runBlocking {
        var heartbeats = 0
        var executions = 0

        val start = FreshClaimExecutionBoundary.run(
            heartbeat = { heartbeats++ },
            onHeartbeatFailure = { error -> error("execution must not report failure: $error") },
        ) {
            executions++
            "done"
        }

        assertEquals("done", assertIs<FreshClaimStart.Started<String>>(start).value)
        assertEquals(1, heartbeats)
        assertEquals(1, executions)
    }

    @Test
    fun failedHeartbeatBlocksBeforeAnyExecution() = runBlocking {
        var executions = 0
        val reported = mutableListOf<String>()

        val start = FreshClaimExecutionBoundary.run(
            heartbeat = { throw ExecutorFailure("HEARTBEAT_UNCONFIRMED", "test heartbeat lost") },
            onHeartbeatFailure = { error ->
                reported += (error as? ExecutorFailure)?.code ?: "OTHER"
            },
        ) {
            executions++
        }

        assertIs<FreshClaimStart.Blocked>(start)
        assertEquals(listOf("HEARTBEAT_UNCONFIRMED"), reported)
        assertEquals(0, executions)
    }

    @Test
    fun cancellationDuringHeartbeatPropagatesWithoutBlocking() = runBlocking {
        var executions = 0
        var failuresReported = 0

        try {
            FreshClaimExecutionBoundary.run(
                heartbeat = { throw kotlinx.coroutines.CancellationException("step cancelled") },
                onHeartbeatFailure = { failuresReported++ },
            ) {
                executions++
            }
            error("cancellation must propagate")
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            assertEquals("step cancelled", cancelled.message)
        }
        assertEquals(0, executions)
        assertEquals(0, failuresReported)
    }
}
