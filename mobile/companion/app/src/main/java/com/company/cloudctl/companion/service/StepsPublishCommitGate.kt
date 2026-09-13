package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.CommitGate
import com.company.cloudctl.companion.automation.ControlledActionIdentity
import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

/**
 * One gated publish for the legacy allowlisted idlefish steps task
 * (contract p09-steps-commit/20260913.1). Never interprets tap completion
 * as platform success; a prior intent only ever reconciles.
 */
class StepsPublishCommitGate(
    private val executor: ControlledActionExecutor,
    private val ui: LocalAutomationUi,
) : CommitGate {
    override suspend fun publishOnce(task: AutomationTask, locatorRef: String) {
        val gatedPublish = when (task.targetPackage) {
            TargetLocatorRegistry.XIANYU_PACKAGE -> "xianyu_publish_button" to "xianyu_publish_success"
            TargetLocatorRegistry.XHS_PACKAGE -> "xhs_publish_button" to "xhs_publish_success"
            else -> throw ExecutorFailure("G3_NOT_ACCEPTED", "Target package has no gated publish")
        }
        require(locatorRef == gatedPublish.first) { "G3_NOT_ACCEPTED" }
        val postcondition = gatedPublish.second
        TargetLocatorRegistry.resolve(task.targetPackage, locatorRef)
        TargetLocatorRegistry.resolve(task.targetPackage, postcondition)
        val payload = JSONObject(
            requireNotNull(executor.persistedPayload(task.taskId)) { "Missing persisted steps task" },
        )
        val identity = ControlledActionIdentity.fromStepsPayload(payload)
        // Recover before touching UI: a recorded intent can never become a fresh tap.
        if (executor.hasRecordedAction(identity.actionKey)) {
            executor.reconcile(identity.actionKey)
            return
        }
        currentCoroutineContext().ensureActive()
        ui.ensureReady(task.targetPackage)
        if (ui.inspect(task.targetPackage, postcondition)?.visible == true) {
            throw ExecutorFailure("POSTCONDITION_ALREADY_MET", "Publish success was already present")
        }
        val before = evidence(task.taskId, identity.actionKey, "before")
        executor.executeStepsCommit(
            taskId = task.taskId,
            beforeEvidence = before,
            timeoutMs = 40_000,
            effect = {
                currentCoroutineContext().ensureActive()
                ui.ensureReady(task.targetPackage)
                if (ui.inspect(task.targetPackage, postcondition)?.visible == true) {
                    throw ExecutorFailure("POSTCONDITION_ALREADY_MET", "Publish success appeared before the submit")
                }
                ui.tapOnce(task.targetPackage, locatorRef)
            },
            postconditionEvidence = {
                var reference: String? = null
                for (attempt in 0 until 24) {
                    currentCoroutineContext().ensureActive()
                    ui.ensureReady(task.targetPackage)
                    val node = ui.inspect(task.targetPackage, postcondition)
                    if (node?.visible == true && node.enabled) {
                        reference = evidence(task.taskId, identity.actionKey, "after")
                        require(reference != before) { "Postcondition screenshot did not change" }
                        break
                    }
                    delay(250)
                }
                reference
            },
        )
    }

    private suspend fun evidence(taskId: String, actionKey: String, stage: String): String {
        val screenshot = ui.screenshot(taskId, "$actionKey-$stage")
        require(screenshot.size > 0 && screenshot.path.isNotBlank() &&
            Regex("[a-f0-9]{64}").matches(screenshot.sha256)) { "Invalid commit evidence" }
        return "sha256:${screenshot.sha256}"
    }
}
