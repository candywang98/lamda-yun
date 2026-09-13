package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.CommandV1Parser
import com.company.cloudctl.companion.automation.ControlledActionIdentity
import com.company.cloudctl.companion.automation.IrreversibleActionGate
import com.company.cloudctl.companion.automation.IrreversibleActionOutcome
import com.company.cloudctl.companion.automation.RecipeCatalog
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.data.PendingTask
import com.company.cloudctl.companion.network.ActionCommitStatus
import com.company.cloudctl.companion.network.ActionIntentDecision
import com.company.cloudctl.companion.network.ActionIntentRequest
import com.company.cloudctl.companion.network.ActionOutcomeRequest
import com.company.cloudctl.companion.network.ControlledActionLedger
import com.company.cloudctl.companion.network.requireEvidence
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

/** Durable once-only ledger adapter used by signed Recipe commits and controlled probes. */
class ControlledActionExecutor(
    private val store: AutomationStore,
    private val remote: ControlledActionLedger,
    private val coordinator: IrreversibleActionCoordinator = IrreversibleActionCoordinator(store),
) {
    fun hasRecordedAction(actionKey: String): Boolean = store.actionJournal(actionKey) != null

    suspend fun reconcilePending(): List<String> {
        val resolved = mutableListOf<String>()
        for (actionKey in store.unresolvedControlledActionKeys()) {
            if (reconcile(actionKey)) resolved.add(actionKey)
        }
        return resolved
    }

    suspend fun execute(
        taskId: String,
        actionId: String,
        beforeEvidence: String,
        timeoutMs: Long = IrreversibleActionGate.DEFAULT_TIMEOUT_MS,
        effect: suspend () -> Unit,
        postconditionEvidence: suspend () -> String?,
    ): IrreversibleActionOutcome {
        requireEvidence(beforeEvidence)
        require(timeoutMs > 0)
        currentCoroutineContext().ensureActive()
        val task = requireNotNull(store.persistedTask(taskId)) { "Missing persisted task" }
        val payload = JSONObject(task.payload)
        val command = CommandV1Parser.parse(payload.getJSONObject("command").toString())
        require(command.taskId == taskId && payload.getString("deviceId") == command.deviceId)
        require(command.commandType == "device.probe_capabilities.v1" &&
            command.targetPackage == "com.company.cloudctl.companion") { "G3_NOT_ACCEPTED" }
        val identity = ControlledActionIdentity.from(command, actionId)
        val prior = checkJournal(identity, taskId)
        if (prior != null) return prior
        // RecipeCatalog contains only verified packages (or the shipped built-in probe).
        val recipe = JSONObject(RecipeCatalog.jsonFor(command))
        val states = recipe.getJSONObject("graph").getJSONArray("states")
        val graph = recipe.getJSONObject("graph")
        require(graph.isNull("commitActionId") || graph.getString("commitActionId") == actionId) {
            "Action does not match declared commitActionId"
        }
        require((0 until states.length()).any { states.getJSONObject(it).getString("stateId") == actionId }) {
            "Action absent from pinned recipe"
        }
        return commitOnce(identity, task, beforeEvidence, timeoutMs, effect, postconditionEvidence)
    }

    /**
     * Gated publish for the legacy allowlisted idlefish steps task
     * (contract p09-steps-commit/20260913.1). Identity is frozen from the
     * canonical steps text; the server re-derives and enforces the same shape.
     */
    suspend fun executeStepsCommit(
        taskId: String,
        beforeEvidence: String,
        timeoutMs: Long = 40_000,
        effect: suspend () -> Unit,
        postconditionEvidence: suspend () -> String?,
    ): IrreversibleActionOutcome {
        requireEvidence(beforeEvidence)
        require(timeoutMs > 0)
        currentCoroutineContext().ensureActive()
        val task = requireNotNull(store.persistedTask(taskId)) { "Missing persisted task" }
        val payload = JSONObject(task.payload)
        require(payload.has("steps") && payload.isNull("command")) { "G3_NOT_ACCEPTED" }
        require(payload.getString("targetPackage") in setOf("com.taobao.idlefish", "com.xingin.xhs")) {
            "G3_NOT_ACCEPTED"
        }
        val identity = ControlledActionIdentity.fromStepsPayload(payload)
        val prior = checkJournal(identity, taskId)
        if (prior != null) return prior
        return commitOnce(identity, task, beforeEvidence, timeoutMs, effect, postconditionEvidence)
    }

    fun persistedPayload(taskId: String): String? = store.persistedTask(taskId)?.payload

    private suspend fun checkJournal(
        identity: ControlledActionIdentity,
        taskId: String,
    ): IrreversibleActionOutcome? {
        val recorded = store.actionJournal(identity.actionKey)
        if (recorded == null) return null
        require(store.controlledActionIdentity(identity.actionKey) == identity) { "Controlled identity mismatch" }
        require(identity.taskId == taskId)
        reconcile(identity.actionKey)
        return IrreversibleActionOutcome("RECONCILE_REQUIRED", recorded.status, false, "prior action is never executable")
    }

    private suspend fun commitOnce(
        identity: ControlledActionIdentity,
        task: PendingTask,
        beforeEvidence: String,
        timeoutMs: Long,
        effect: suspend () -> Unit,
        postconditionEvidence: suspend () -> String?,
    ): IrreversibleActionOutcome {
        var invoked = false
        val outcome = coordinator.executeOnce(
            actionKey = identity.actionKey, taskId = identity.taskId, parameterHash = identity.parameterHash,
            timeoutMs = timeoutMs, confirmApplied = true, controlledIdentity = identity,
        ) {
            val grant = remote.intent(identity.taskId, ActionIntentRequest(task.leaseId, identity.actionId,
                identity.actionKey, identity.parameterHash, beforeEvidence))
            check(grant.httpStatus == 201 && grant.decision == ActionIntentDecision.AUTHORIZED &&
                grant.action.matches(identity) && grant.action.status == ActionCommitStatus.INTENT &&
                grant.action.resolutionRevision == 0L && grant.action.beforeEvidence == beforeEvidence) {
                "Fresh authorization required"
            }
            currentCoroutineContext().ensureActive()
            var reportingApplied = false
            try {
                invoked = true
                effect()
                val evidence = postconditionEvidence()
                requireEvidence(evidence)
                currentCoroutineContext().ensureActive()
                reportingApplied = true
                val reported = remote.outcome(identity.taskId, identity.actionKey,
                    ActionOutcomeRequest(task.leaseId, identity.parameterHash, ActionCommitStatus.APPLIED, evidence))
                check(reported.matches(identity) && reported.status == ActionCommitStatus.APPLIED) {
                    "Outcome identity or status mismatch"
                }
            } catch (cancelled: CancellationException) {
                // The gate persists UNKNOWN and reconciliation before propagating cancellation.
                throw cancelled
            } catch (_: Exception) {
                // A lost APPLIED response is ambiguous: never send a conflicting UNKNOWN replay.
                if (!reportingApplied) {
                    try {
                        remote.outcome(identity.taskId, identity.actionKey,
                            ActionOutcomeRequest(task.leaseId, identity.parameterHash, ActionCommitStatus.UNKNOWN,
                                "android-observation://${identity.actionKey}/unconfirmed"))
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (_: Exception) { /* Durable local UNKNOWN remains authoritative for blocking. */ }
                }
                error("Controlled observation unavailable; reconciliation required")
            }
        }
        return outcome.copy(actionInvoked = invoked)
    }

    /** Recovery needs only the durable full identity, even if the recipe is no longer cached. */
    suspend fun reconcile(actionKey: String): Boolean {
        val identity = store.controlledActionIdentity(actionKey) ?: return false
        return try {
            val row = remote.get(identity.taskId, actionKey)
            store.applyControlledActionResolution(row)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            false
        }
    }
}
