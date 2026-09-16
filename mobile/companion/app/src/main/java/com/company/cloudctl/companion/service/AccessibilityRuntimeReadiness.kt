package com.company.cloudctl.companion.service

import java.time.Instant

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

// ---------------------------------------------------------------------------
// B11 slice (fleet-identity/v1@20260916.1 §2): the three runtime dimensions —
// enabled (secure setting), active (bound service instance), readiness
// (enabled ∧ stable active) — are reported separately, and a rebind transient
// is absorbed inside a BOUNDED observation window only. Observation never
// replays submissions: when a rebind recovers, the returned Ready carries the
// NEW runtime instance; anything the caller captured before the rebind is
// stale (its B10 fencing token died with the old binding) and must be
// re-acquired through the normal claim path instead of replayed.
// ---------------------------------------------------------------------------

enum class AccessibilityRuntimePhase { READY, REBIND_WAIT, INACTIVE, DISABLED }

/** Queryable, per-dimension report for the UI and the heartbeat payload. */
data class AccessibilityRuntimeStatus(
    val accessibilityEnabled: Boolean,
    val accessibilityActive: Boolean,
    val readiness: Boolean,
    val phase: AccessibilityRuntimePhase,
    val rebindCount: Int,
    val waitedMillis: Long,
    val observedAt: Instant,
) {
    val explanation: String
        get() = when (phase) {
            AccessibilityRuntimePhase.READY ->
                if (rebindCount > 0) "无障碍已在重绑后的新实例上恢复（观察窗内实例切换 $rebindCount 次）"
                else "无障碍服务已启用且处于活动状态"
            AccessibilityRuntimePhase.REBIND_WAIT ->
                "无障碍已启用，正在有界观察窗内等待重绑恢复（已等待 ${waitedMillis}ms）"
            AccessibilityRuntimePhase.INACTIVE ->
                "无障碍已启用但超过观察窗口仍未激活，需人工检查（等待 ${waitedMillis}ms）"
            AccessibilityRuntimePhase.DISABLED ->
                "无障碍服务已被关闭，需用户在系统设置中重新启用"
        }
}

/** Process-wide, thread-safe holder of the latest per-dimension status. */
object AccessibilityRuntimeStatusRegistry {
    @Volatile
    private var latestStatus: AccessibilityRuntimeStatus? = null

    @JvmStatic
    fun record(status: AccessibilityRuntimeStatus) {
        latestStatus = status
    }

    @JvmStatic
    fun snapshot(): AccessibilityRuntimeStatus? = latestStatus

    @JvmStatic
    fun clear() {
        latestStatus = null
    }
}

enum class RebindOutcome { READY, REBIND_RECOVERED, STILL_INACTIVE, DISABLED }

data class RebindObservation<T : Any>(
    val readiness: AccessibilityRuntimeReadiness<T>,
    val outcome: RebindOutcome,
    val rebindCount: Int,
    val instanceChanged: Boolean,
    val waitedMillis: Long,
    val status: AccessibilityRuntimeStatus,
)

/**
 * Bounded rebind observation (B11). A transient rebind (enabled stays on
 * while the active instance flips) consumes only the bounded wait budget; a
 * permanent disable (enabled goes off) exits the wait immediately with a
 * queryable DISABLED status. The waiter only observes — it never re-runs,
 * re-claims, or re-submits anything.
 */
class RebindAwareReadinessWaiter<T : Any>(
    private val timeoutMillis: Long,
    private val pollIntervalMillis: Long,
    private val isEnabled: () -> Boolean,
    private val activeService: () -> T?,
    private val sleep: suspend (Long) -> Unit,
    private val now: () -> Instant = { Instant.now() },
) {
    init {
        require(timeoutMillis >= 0) { "timeoutMillis must not be negative" }
        require(pollIntervalMillis > 0) { "pollIntervalMillis must be positive" }
    }

    suspend fun observe(): RebindObservation<T> {
        var rebindCount = 0
        var waitedMillis = 0L
        var lastSeenInstance: T? = null

        fun captureNow(): AccessibilityRuntimeReadiness<T> {
            if (!isEnabled()) return AccessibilityRuntimeReadiness.NotEnabled
            val first = activeService() ?: return AccessibilityRuntimeReadiness.NotActive
            if (!isEnabled()) return AccessibilityRuntimeReadiness.NotEnabled
            if (first !== lastSeenInstance) {
                if (lastSeenInstance != null) rebindCount += 1
                lastSeenInstance = first
            }
            return if (activeService() === first) {
                AccessibilityRuntimeReadiness.Ready(first)
            } else {
                AccessibilityRuntimeReadiness.NotActive
            }
        }

        fun finish(
            readiness: AccessibilityRuntimeReadiness<T>,
            outcome: RebindOutcome,
            enabled: Boolean,
            active: Boolean,
            phase: AccessibilityRuntimePhase,
        ): RebindObservation<T> {
            val status = AccessibilityRuntimeStatus(
                accessibilityEnabled = enabled,
                accessibilityActive = active,
                readiness = outcome == RebindOutcome.READY || outcome == RebindOutcome.REBIND_RECOVERED,
                phase = phase,
                rebindCount = rebindCount,
                waitedMillis = waitedMillis,
                observedAt = now(),
            )
            AccessibilityRuntimeStatusRegistry.record(status)
            return RebindObservation(
                readiness = readiness,
                outcome = outcome,
                rebindCount = rebindCount,
                instanceChanged = rebindCount > 0,
                waitedMillis = waitedMillis,
                status = status,
            )
        }

        when (val first = captureNow()) {
            is AccessibilityRuntimeReadiness.Ready -> return finish(
                first, RebindOutcome.READY, enabled = true, active = true,
                phase = AccessibilityRuntimePhase.READY,
            )
            AccessibilityRuntimeReadiness.NotEnabled -> return finish(
                first, RebindOutcome.DISABLED, enabled = false, active = false,
                phase = AccessibilityRuntimePhase.DISABLED,
            )
            AccessibilityRuntimeReadiness.NotActive -> Unit
        }

        var remainingMillis = timeoutMillis
        while (remainingMillis > 0) {
            val delayMillis = minOf(pollIntervalMillis, remainingMillis)
            sleep(delayMillis)
            waitedMillis += delayMillis
            remainingMillis -= delayMillis
            when (val readiness = captureNow()) {
                is AccessibilityRuntimeReadiness.Ready -> return finish(
                    readiness,
                    if (rebindCount > 0) RebindOutcome.REBIND_RECOVERED else RebindOutcome.READY,
                    enabled = true, active = true,
                    phase = AccessibilityRuntimePhase.READY,
                )
                AccessibilityRuntimeReadiness.NotEnabled -> return finish(
                    readiness, RebindOutcome.DISABLED, enabled = false, active = false,
                    phase = AccessibilityRuntimePhase.DISABLED,
                )
                AccessibilityRuntimeReadiness.NotActive -> {
                    AccessibilityRuntimeStatusRegistry.record(
                        AccessibilityRuntimeStatus(
                            accessibilityEnabled = true,
                            accessibilityActive = false,
                            readiness = false,
                            phase = AccessibilityRuntimePhase.REBIND_WAIT,
                            rebindCount = rebindCount,
                            waitedMillis = waitedMillis,
                            observedAt = now(),
                        ),
                    )
                }
            }
        }
        return finish(
            AccessibilityRuntimeReadiness.NotActive,
            RebindOutcome.STILL_INACTIVE,
            enabled = true, active = false,
            phase = AccessibilityRuntimePhase.INACTIVE,
        )
    }
}
