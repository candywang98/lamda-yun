package com.company.cloudctl.companion.service

import kotlin.math.min
import kotlin.random.Random

internal class SyncRetryPolicy(
    private val initialDelayMillis: Long = 1_000L,
    private val maximumDelayMillis: Long = 60_000L,
    private val jitter: () -> Double = { Random.nextDouble(0.8, 1.2) },
) {
    private var failures = 0

    fun nextDelayMillis(): Long {
        val exponent = min(failures, MAX_EXPONENT)
        val base = min(initialDelayMillis * (1L shl exponent), maximumDelayMillis)
        failures += 1
        return (base * jitter()).toLong().coerceIn(1L, maximumDelayMillis)
    }

    fun reset() {
        failures = 0
    }

    private companion object {
        const val MAX_EXPONENT = 16
    }
}
