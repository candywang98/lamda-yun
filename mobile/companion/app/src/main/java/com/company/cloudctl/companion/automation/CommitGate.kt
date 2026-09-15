package com.company.cloudctl.companion.automation

/**
 * Durable once-only gate for the irreversible publish tap. The runner stops at
 * the commit step after [publishOnce] returns, regardless of the outcome;
 * terminal state comes from an authenticated server resolution.
 */
fun interface CommitGate {
    suspend fun publishOnce(task: AutomationTask, locatorRef: String)
}

/**
 * Durable once-only gate for the destructive confirm click of a xianyu
 * maintenance action (下架/删除已下架 second strike). The tap happens only
 * after one fresh server authorization; the ledger verifies the badge
 * postcondition and reports UNKNOWN when unconfirmed — never retried.
 *
 * Implementations return the pre-strike badge baseline so a follow-up
 * `ui.assertBadge` step can assert the expected delta, or null when a prior
 * recorded intent only reconciled (no fresh strike, no valid baseline).
 */
interface DestructiveClickGate {
    suspend fun confirmOnce(task: AutomationTask, step: AutomationStep.TapLayout): Int?

    suspend fun confirmOnce(task: AutomationTask, locatorRef: String): Int? {
        throw ExecutorFailure("G3_NOT_ACCEPTED", "Semantic destructive confirm is not supported")
    }
}
