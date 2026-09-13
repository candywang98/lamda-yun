package com.company.cloudctl.companion.automation

/**
 * Durable once-only gate for the irreversible publish tap. The runner stops at
 * the commit step after [publishOnce] returns, regardless of the outcome;
 * terminal state comes from an authenticated server resolution.
 */
fun interface CommitGate {
    suspend fun publishOnce(task: AutomationTask, locatorRef: String)
}
