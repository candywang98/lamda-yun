package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.data.AutomationStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeout

data class IrreversibleActionOutcome(
    val decision: String,
    val journalStatus: String,
    val actionInvoked: Boolean,
    val reason: String,
)

class IrreversibleActionGate(
    private val store: AutomationStore,
) {
    suspend fun executeOnce(
        actionKey: String,
        taskId: String,
        parameterHash: String,
        timeoutMs: Long = DEFAULT_TIMEOUT_MS,
        confirmApplied: Boolean = false,
        controlledIdentity: ControlledActionIdentity? = null,
        action: suspend () -> Unit,
    ): IrreversibleActionOutcome {
        val recorded = store.recordActionIntent(actionKey, taskId, parameterHash, controlledIdentity)
        return when (recorded) {
            STATUS_NOT_SUBMITTED -> IrreversibleActionOutcome(
                DECISION_RECONCILE_REQUIRED, STATUS_NOT_SUBMITTED, false, "resolved not submitted; old action is not executable",
            )
            STATUS_APPLIED -> IrreversibleActionOutcome(
                decision = DECISION_SKIPPED_APPLIED,
                journalStatus = STATUS_APPLIED,
                actionInvoked = false,
                reason = "already applied",
            )
            STATUS_UNKNOWN -> IrreversibleActionOutcome(
                decision = DECISION_RECONCILE_REQUIRED,
                journalStatus = store.actionJournal(actionKey)?.status ?: STATUS_UNKNOWN,
                actionInvoked = false,
                reason = "prior intent requires reconciliation",
            )
            STATUS_INTENT -> invokeFresh(
                actionKey = actionKey,
                timeoutMs = timeoutMs,
                confirmApplied = confirmApplied,
                action = action,
            )
            else -> error("Illegal action journal decision $recorded for $actionKey")
        }
    }

    private suspend fun invokeFresh(
        actionKey: String,
        timeoutMs: Long,
        confirmApplied: Boolean,
        action: suspend () -> Unit,
    ): IrreversibleActionOutcome {
        return try {
            withTimeout(timeoutMs) { action() }
            if (!confirmApplied) {
                store.markActionUnknown(actionKey)
                IrreversibleActionOutcome(
                    decision = DECISION_UNKNOWN,
                    journalStatus = STATUS_UNKNOWN,
                    actionInvoked = true,
                    reason = "action completed before confirmation",
                )
            } else {
                store.markActionApplied(actionKey)
                IrreversibleActionOutcome(
                    decision = DECISION_APPLIED,
                    journalStatus = STATUS_APPLIED,
                    actionInvoked = true,
                    reason = "explicit confirmation",
                )
            }
        } catch (cancelled: CancellationException) {
            store.markActionUnknown(actionKey)
            throw cancelled
        } catch (failure: Throwable) {
            store.markActionUnknown(actionKey)
            IrreversibleActionOutcome(
                decision = DECISION_UNKNOWN,
                journalStatus = STATUS_UNKNOWN,
                actionInvoked = true,
                reason = failure.message ?: "action failed",
            )
        }
    }

    companion object {
        const val STATUS_NOT_SUBMITTED = "NOT_SUBMITTED"
        const val STATUS_INTENT = "INTENT"
        const val STATUS_UNKNOWN = "UNKNOWN"
        const val STATUS_APPLIED = "APPLIED"
        const val DECISION_APPLIED = "APPLIED"
        const val DECISION_SKIPPED_APPLIED = "APPLIED"
        const val DECISION_UNKNOWN = "UNKNOWN"
        const val DECISION_RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
        const val DEFAULT_TIMEOUT_MS = 5_000L
    }
}
