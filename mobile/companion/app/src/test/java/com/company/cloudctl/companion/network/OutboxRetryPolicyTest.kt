package com.company.cloudctl.companion.network

import java.time.Duration
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class OutboxRetryPolicyTest {
    @Test
    fun `transient statuses retry while credentials fail permanently`() {
        listOf(408, 425, 429, 500, 503).forEach { status ->
            assertEquals(
                DeliveryFailureAction.RETRY,
                OutboxRetryPolicy.classify(CloudHttpException(status, "temporary")),
            )
        }
        listOf(400, 401, 403, 404, 422).forEach { status ->
            assertEquals(
                DeliveryFailureAction.PERMANENT_REJECTION,
                OutboxRetryPolicy.classify(CloudHttpException(status, "invalid")),
            )
        }
    }

    @Test
    fun `stale mobile lease is idempotently accepted`() {
        assertEquals(
            DeliveryFailureAction.ACCEPT_AS_DELIVERED,
            OutboxRetryPolicy.classify(
                CloudHttpException(409, "The mobile task lease is already closed"),
            ),
        )
        assertEquals(
            DeliveryFailureAction.PERMANENT_REJECTION,
            OutboxRetryPolicy.classify(CloudHttpException(409, "unrelated conflict")),
        )
    }

    @Test
    fun `backoff grows and remains bounded with deterministic jitter`() {
        val now = Instant.parse("2026-09-01T00:00:00Z")
        val first = OutboxRetryPolicy.nextAttemptAt(7, 1, now)
        val second = OutboxRetryPolicy.nextAttemptAt(7, 2, now)
        val capped = OutboxRetryPolicy.nextAttemptAt(7, 40, now)

        assertTrue(first.isAfter(now))
        assertTrue(second.isAfter(first))
        assertEquals(first, OutboxRetryPolicy.nextAttemptAt(7, 1, now))
        assertTrue(Duration.between(now, capped) <= Duration.ofMinutes(6))
    }
}
