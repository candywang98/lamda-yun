package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.IrreversibleActionGate
import com.company.cloudctl.companion.automation.IrreversibleActionOutcome
import com.company.cloudctl.companion.data.AutomationStore
import org.json.JSONObject

/**
 * Bridges the local once-gate onto Companion outbox events.
 *
 * Unknown or rejected irreversible attempts persist a RECONCILING event while the
 * inbox row stays RUNNING. This does not pause, resume, or touch real recipes.
 */
class IrreversibleActionCoordinator(
    private val store: AutomationStore,
    private val gate: IrreversibleActionGate = IrreversibleActionGate(store),
) {
    suspend fun executeOnce(
        actionKey: String,
        taskId: String,
        parameterHash: String,
        timeoutMs: Long = IrreversibleActionGate.DEFAULT_TIMEOUT_MS,
        confirmApplied: Boolean = true,
        action: suspend () -> Unit,
    ): IrreversibleActionOutcome {
        val outcome = try {
            gate.executeOnce(
                actionKey = actionKey,
                taskId = taskId,
                parameterHash = parameterHash,
                timeoutMs = timeoutMs,
                confirmApplied = confirmApplied,
                action = action,
            )
        } catch (rejected: IllegalArgumentException) {
            persistReconciling(
                actionKey = actionKey,
                taskId = taskId,
                outcome = IrreversibleActionOutcome(
                    decision = IrreversibleActionGate.DECISION_RECONCILE_REQUIRED,
                    journalStatus = store.actionJournal(actionKey)?.status
                        ?: IrreversibleActionGate.STATUS_UNKNOWN,
                    actionInvoked = false,
                    reason = rejected.message ?: "gate rejected",
                ),
            )
            throw rejected
        }
        if (needsReconciliation(outcome)) {
            persistReconciling(actionKey, taskId, outcome)
        }
        return outcome
    }

    private fun needsReconciliation(outcome: IrreversibleActionOutcome): Boolean {
        return outcome.decision == IrreversibleActionGate.DECISION_UNKNOWN ||
            outcome.decision == IrreversibleActionGate.DECISION_RECONCILE_REQUIRED ||
            outcome.journalStatus == IrreversibleActionGate.STATUS_UNKNOWN ||
            outcome.journalStatus == IrreversibleActionGate.STATUS_INTENT && !outcome.actionInvoked
    }

    private fun persistReconciling(
        actionKey: String,
        taskId: String,
        outcome: IrreversibleActionOutcome,
    ) {
        store.recordStepEvent(
            taskId = taskId,
            stepId = actionKey,
            state = "RUNNING",
            detailCode = "RECONCILING",
            eventType = EVENT_RECONCILING,
            stepIndex = null,
            payload = JSONObject()
                .put("actionKey", actionKey)
                .put("decision", outcome.decision)
                .put("journalStatus", outcome.journalStatus)
                .put("reason", outcome.reason)
                .put("blockedResume", true)
                .put("ordinaryResume", false),
        )
    }

    companion object {
        const val EVENT_RECONCILING = "RECONCILING"
    }
}
