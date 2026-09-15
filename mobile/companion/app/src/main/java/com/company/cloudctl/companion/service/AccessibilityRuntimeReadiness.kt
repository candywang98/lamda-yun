package com.company.cloudctl.companion.service

sealed interface AccessibilityRuntimeReadiness<out T : Any> {
    data class Ready<T : Any>(val service: T) : AccessibilityRuntimeReadiness<T>
    data object NotEnabled : AccessibilityRuntimeReadiness<Nothing>
    data object NotActive : AccessibilityRuntimeReadiness<Nothing>
}

class AccessibilityRuntimeReadinessWaiter<T : Any>(
    private val timeoutMillis: Long,
    private val pollIntervalMillis: Long,
    private val isEnabled: () -> Boolean,
    private val activeService: () -> T?,
    private val sleep: suspend (Long) -> Unit,
) {
    init {
        require(timeoutMillis >= 0) { "timeoutMillis must not be negative" }
        require(pollIntervalMillis > 0) { "pollIntervalMillis must be positive" }
    }

    fun capture(): AccessibilityRuntimeReadiness<T> {
        if (!isEnabled()) return AccessibilityRuntimeReadiness.NotEnabled
        val first = activeService() ?: return AccessibilityRuntimeReadiness.NotActive
        if (!isEnabled()) return AccessibilityRuntimeReadiness.NotEnabled
        return if (activeService() === first) {
            AccessibilityRuntimeReadiness.Ready(first)
        } else {
            AccessibilityRuntimeReadiness.NotActive
        }
    }

    suspend fun await(): AccessibilityRuntimeReadiness<T> {
        capture().let { readiness ->
            if (readiness !is AccessibilityRuntimeReadiness.NotActive) return readiness
        }

        var remainingMillis = timeoutMillis
        while (remainingMillis > 0) {
            val delayMillis = minOf(pollIntervalMillis, remainingMillis)
            sleep(delayMillis)
            capture().let { readiness ->
                if (readiness !is AccessibilityRuntimeReadiness.NotActive) return readiness
            }
            remainingMillis -= delayMillis
        }
        return AccessibilityRuntimeReadiness.NotActive
    }
}
