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

/**
 * Frozen protocol (R20260916-P09-18 / P09-19): a fresh local claim that cannot
 * reach a stable accessibility runtime must release the server task back to
 * the queue. The release is legal only in the CLAIMED/PREFLIGHT window —
 * before the first task heartbeat and before any committed write (see
 * runtime/ReleasePolicy.kt, fleet-identity/v1@20260916.1 §8); this coordinator
 * runs strictly inside that window, so no committed action can exist and the
 * settled task is never re-executed locally, only redelivered by the server
 * after lease expiry (no loss, no busy loop).
 */
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
