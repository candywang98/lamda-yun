package com.company.cloudctl.companion.network

import java.time.Instant
import kotlin.math.min

enum class DeliveryFailureAction {
    RETRY,
    ACCEPT_AS_DELIVERED,
    PERMANENT_REJECTION,
}

object OutboxRetryPolicy {
    private const val BASE_DELAY_MILLIS = 5_000L
    private const val MAX_DELAY_MILLIS = 5 * 60_000L

    fun classify(error: CloudHttpException): DeliveryFailureAction = when {
        error.status == 401 -> DeliveryFailureAction.PERMANENT_REJECTION
        error.status == 409 && error.responseBody.contains("mobile task lease", ignoreCase = true) ->
            DeliveryFailureAction.ACCEPT_AS_DELIVERED
        error.status == 408 || error.status == 425 || error.status == 429 || error.status in 500..599 ->
            DeliveryFailureAction.RETRY
        else -> DeliveryFailureAction.PERMANENT_REJECTION
    }

    fun nextAttemptAt(outboxId: Long, failedAttempt: Int, now: Instant = Instant.now()): Instant {
        require(failedAttempt >= 1)
        val exponent = min(failedAttempt - 1, 16)
        val uncapped = BASE_DELAY_MILLIS * (1L shl exponent)
        val capped = min(uncapped, MAX_DELAY_MILLIS)
        val jitterPercent = 80L + Math.floorMod(outboxId * 31L + failedAttempt * 17L, 41L)
        return now.plusMillis(capped * jitterPercent / 100L)
    }
}
