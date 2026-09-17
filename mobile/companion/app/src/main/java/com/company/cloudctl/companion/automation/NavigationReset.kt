package com.company.cloudctl.companion.automation

/**
 * Bounded navigation policy; the port owns Android I/O, cancellation and time.
 *
 * B13 / FLEET-20 addition — [recoverStalledWait]: wait-type steps (for
 * example the recipe `wait-home` state) that make no progress or fail now
 * recover through a BOUNDED return-to-target-page loop: a limited number of
 * back/navigation actions, the page summary re-sampled after EVERY action to
 * judge arrival, a no-progress counter with explicit termination conditions,
 * and a fail-closed report once the budget is spent. Force-stopping the app
 * (`am force-stop`) is forbidden; so is an unbounded back loop. The
 * forced-relaunch last resort exists ONLY on the fresh-run [execute] path,
 * which predates this task and stays byte-compatible.
 */
internal class NavigationReset(private val port: Port) {
    interface Port {
        fun atRootPage(): Boolean
        fun isTargetForeground(): Boolean
        /** Atomically recognizes and gesture-taps one allowlisted safe button, or returns null. */
        suspend fun dismissBlockedDialog(): String?
        suspend fun goBack()
        suspend fun relaunch()
        suspend fun settle(ms: Long)
        fun checkpoint()
        fun event(code: String)
    }

    suspend fun execute() {
        var dismissed = 0
        suspend fun recoverRoot(): Boolean {
            port.checkpoint()
            if (port.atRootPage()) return true
            while (dismissed < MAX_DIALOGS && port.isTargetForeground()) {
                port.checkpoint()
                val label = port.dismissBlockedDialog() ?: break
                dismissed++
                port.event("NAV_DIALOG_DISMISSED label=$label")
                port.settle(DIALOG_SETTLE_MS)
                port.checkpoint()
                if (port.atRootPage()) return true
            }
            return false
        }

        if (recoverRoot()) return
        port.event("NAV_RESET_BACK")
        repeat(MAX_BACKS) {
            if (recoverRoot()) return
            if (!port.isTargetForeground()) return@repeat
            port.checkpoint()
            port.goBack()
        }
        if (recoverRoot()) return
        port.checkpoint()
        port.event("NAV_RESET_RELAUNCH")
        port.relaunch()
        repeat(RELAUNCH_POLLS) {
            if (recoverRoot()) return
            port.settle(POLL_MS)
        }
        if (!recoverRoot()) {
            throw ExecutorFailure("NAV_RESET_FAILED", "Target app could not be returned to its root page")
        }
    }

    companion object {
        const val MAX_DIALOGS = 3
        const val DIALOG_SETTLE_MS = 800L
        private const val MAX_BACKS = 5
        private const val RELAUNCH_POLLS = 12
        private const val POLL_MS = 500L

        // FLEET-20 wait-recovery defaults: small, bounded, observable.
        const val WAIT_RECOVERY_MAX_ACTIONS = 4
        const val WAIT_RECOVERY_NO_PROGRESS_LIMIT = 2
        const val WAIT_RECOVERY_SETTLE_MS = 400L
    }

    // -------------------------------------------------------------------------
    // FLEET-20 — bounded wait-step recovery by page summary (B13).
    // -------------------------------------------------------------------------

    /**
     * Live page-summary sampler. The digest must follow the B12
     * business-digest discipline (banner/keyboard layers excluded,
     * displacement normalized — ui-observation/v1 §6): a banner shifting
     * every bound is NOT progress. [sessionEpoch] follows the §2/§6 rule:
     * digests from different epochs are never compared for progress.
     */
    interface PageSummarySource {
        fun sessionEpoch(): Long
        fun pageDigest(): String
        /** True when the freshly sampled digest proves the wait's target page is showing. */
        fun isTargetPage(): Boolean
    }

    /** Bounded budget for one wait-step recovery; every field is an explicit termination condition. */
    data class WaitRecoveryBudget(
        val maxRecoveryActions: Int = WAIT_RECOVERY_MAX_ACTIONS,
        val noProgressLimit: Int = WAIT_RECOVERY_NO_PROGRESS_LIMIT,
        val settleMs: Long = WAIT_RECOVERY_SETTLE_MS,
    ) {
        init {
            require(maxRecoveryActions > 0) { "maxRecoveryActions must be positive" }
            require(noProgressLimit > 0) { "noProgressLimit must be positive" }
            require(settleMs >= 0) { "settleMs must not be negative" }
        }
    }

    /** One executed recovery action and the page state right after it. */
    data class RecoveryStep(
        val kind: Kind,
        val detail: String,
        val digestAfter: String,
        val epochAfter: Long,
        val arrived: Boolean,
    ) {
        enum class Kind { DIALOG_DISMISS, BACK }
    }

    /** Terminal outcome of [recoverStalledWait]; [Failed] is the fail-closed report. */
    sealed interface WaitRecovery {
        data class Recovered(val actions: Int, val trace: List<RecoveryStep>) : WaitRecovery
        data class Failed(val code: String, val reason: String, val actions: Int, val trace: List<RecoveryStep>) :
            WaitRecovery

        /** Convenience for callers that fail-closed by exception. */
        fun orThrow(): WaitRecovery = when (this) {
            is Recovered -> this
            is Failed -> throw ExecutorFailure(code, reason)
        }
    }

    /**
     * Recover a stalled wait step by walking the page back toward the wait's
     * target page, bounded and observable:
     *
     * 1. sample the page summary; if the target page is already showing,
     *    done ([WaitRecovery.Recovered]);
     * 2. take ONE recovery action — a bounded allowlisted dialog dismissal
     *    when one is up, otherwise a single system BACK;
     * 3. settle, then re-sample the summary and judge arrival again;
     * 4. termination conditions, all explicit: target page reached; target
     *    app lost from the foreground; [WaitRecoveryBudget.noProgressLimit]
     *    consecutive actions after which the digest did not change (same
     *    epoch — cross-epoch samples reset the counter, §2/§6);
     *    [WaitRecoveryBudget.maxRecoveryActions] spent.
     *
     * Exceeding the budget fails closed with [Failed] — no forced relaunch,
     * no `am force-stop`, no unbounded back. Cancellation/deadline still
     * propagate through [Port.checkpoint].
     */
    suspend fun recoverStalledWait(
        summary: PageSummarySource,
        budget: WaitRecoveryBudget = WaitRecoveryBudget(),
    ): WaitRecovery {
        val trace = mutableListOf<RecoveryStep>()
        var actions = 0
        var lastDigest: String? = null
        var lastEpoch: Long? = null
        var consecutiveNoProgress = 0
        while (true) {
            port.checkpoint()
            if (!port.isTargetForeground()) {
                return WaitRecovery.Failed(
                    code = "NAV_WAIT_TARGET_LOST",
                    reason = "target app left the foreground during wait recovery; failing closed " +
                        "instead of pressing BACK inside another app",
                    actions = actions,
                    trace = trace,
                )
            }
            val digest = summary.pageDigest()
            val epoch = summary.sessionEpoch()
            if (summary.isTargetPage()) {
                port.event("NAV_WAIT_RECOVERED actions=$actions")
                return WaitRecovery.Recovered(actions = actions, trace = trace)
            }
            // Progress bookkeeping AFTER an action (this loop's actions are
            // deliberate navigation side effects, so the B12 pre-side-effect
            // NoProgressMonitor cannot be reused here — but its frozen rules
            // are mirrored: compare only same-epoch digests, and an unchanged
            // digest after an action is no progress, never "settled").
            if (lastDigest != null && lastEpoch == epoch && digest == lastDigest) {
                consecutiveNoProgress += 1
            } else {
                consecutiveNoProgress = 0
            }
            lastDigest = digest
            lastEpoch = epoch
            if (consecutiveNoProgress >= budget.noProgressLimit) {
                port.event("NAV_WAIT_NO_PROGRESS actions=$actions")
                return WaitRecovery.Failed(
                    code = "NAV_WAIT_NO_PROGRESS",
                    reason = "page summary unchanged after $consecutiveNoProgress consecutive recovery " +
                        "actions (digest=$digest, epoch=$epoch); no-progress termination",
                    actions = actions,
                    trace = trace,
                )
            }
            if (actions >= budget.maxRecoveryActions) {
                port.event("NAV_WAIT_BUDGET_EXHAUSTED actions=$actions")
                return WaitRecovery.Failed(
                    code = "NAV_WAIT_RECOVERY_BUDGET_EXHAUSTED",
                    reason = "wait recovery budget spent ($actions back/navigation actions) without " +
                        "reaching the target page; failing closed (no force-stop, no unbounded back)",
                    actions = actions,
                    trace = trace,
                )
            }
            port.checkpoint()
            val label = port.dismissBlockedDialog()
            val step = if (label != null) {
                actions += 1
                port.event("NAV_WAIT_DIALOG_DISMISSED label=$label")
                RecoveryStep.Kind.DIALOG_DISMISS
            } else {
                actions += 1
                port.event("NAV_WAIT_BACK n=$actions")
                port.goBack()
                RecoveryStep.Kind.BACK
            }
            port.settle(budget.settleMs)
            port.checkpoint()
            trace += RecoveryStep(
                kind = step,
                detail = label ?: "back#$actions",
                digestAfter = summary.pageDigest(),
                epochAfter = summary.sessionEpoch(),
                arrived = summary.isTargetPage(),
            )
        }
    }
}
