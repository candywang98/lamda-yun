package com.company.cloudctl.companion.service

import kotlinx.coroutines.CancellationException

sealed interface FreshClaimAccessibility<out T : Any> {
    data class Ready<T : Any>(val service: T) : FreshClaimAccessibility<T>
    data class Released(val reason: String) : FreshClaimAccessibility<Nothing>
    data class ReleaseBlocked(val reason: String, val error: Exception?) : FreshClaimAccessibility<Nothing>
}

sealed interface FreshClaimStart<out T> {
    data class Started<T>(val value: T) : FreshClaimStart<T>
    data class Blocked(val error: Exception) : FreshClaimStart<Nothing>
}

class FreshClaimExecutionCoordinator<T : Any>(
    private val awaitAccessibility: suspend () -> AccessibilityRuntimeReadiness<T>,
    private val markReleaseBlocked: (String) -> Boolean,
    private val release: suspend (String) -> Unit,
    private val settleReleased: (String) -> Unit,
) {
    suspend fun acquire(): FreshClaimAccessibility<T> {
        val readiness = awaitAccessibility()
        if (readiness is AccessibilityRuntimeReadiness.Ready) {
            return FreshClaimAccessibility.Ready(readiness.service)
        }
        val reason = when (readiness) {
            AccessibilityRuntimeReadiness.NotEnabled -> "ACCESSIBILITY_NOT_ENABLED"
            AccessibilityRuntimeReadiness.NotActive -> "ACCESSIBILITY_NOT_ACTIVE"
            is AccessibilityRuntimeReadiness.Ready -> error("handled above")
        }
        if (!markReleaseBlocked(reason)) {
            return FreshClaimAccessibility.ReleaseBlocked(reason, null)
        }
        return try {
            release(reason)
            settleReleased(reason)
            FreshClaimAccessibility.Released(reason)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            FreshClaimAccessibility.ReleaseBlocked(reason, error)
        }
    }
}

internal object FreshClaimExecutionBoundary {
    suspend fun <T> run(
        heartbeat: suspend () -> Unit,
        onHeartbeatFailure: (Exception) -> Unit,
        execution: suspend () -> T,
    ): FreshClaimStart<T> {
        try {
            heartbeat()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            onHeartbeatFailure(error)
            return FreshClaimStart.Blocked(error)
        }
        return FreshClaimStart.Started(execution())
    }
}
