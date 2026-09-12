package com.company.cloudctl.companion.service

import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.ControlledActionIdentity
import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.LocalAutomationUi
import com.company.cloudctl.companion.automation.RecipeState
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive

/** One signed commit state; never interprets tap completion as platform success. */
class RecipeCommitAdapter(
    private val executor: ControlledActionExecutor,
    private val ui: LocalAutomationUi,
) {
    suspend fun execute(command: CommandV1, state: RecipeState, controlCheckpoint: () -> Unit) {
        if (command.commandType != "device.probe_capabilities.v1" ||
            command.targetPackage != TargetLocatorRegistry.COMPANION_PACKAGE) {
            throw ExecutorFailure("G3_NOT_ACCEPTED", "Platform commit acceptance is required")
        }
        val locator = requireNotNull(state.locatorRef)
        val postcondition = requireNotNull(state.postcondition)
        TargetLocatorRegistry.resolve(command.targetPackage, locator)
        TargetLocatorRegistry.resolve(command.targetPackage, postcondition)
        val identity = ControlledActionIdentity.from(command, state.stateId)
        // Recover before inspecting UI: a prior intent can never become a fresh effect.
        if (executor.hasRecordedAction(identity.actionKey)) {
            executor.reconcile(identity.actionKey)
            return
        }
        currentCoroutineContext().ensureActive()
        controlCheckpoint()
        ui.ensureReady(command.targetPackage)
        if (ui.inspect(command.targetPackage, postcondition)?.visible == true) {
            throw ExecutorFailure("POSTCONDITION_ALREADY_MET", "Commit postcondition was already present")
        }
        val before = evidence(command.taskId, identity.actionKey, "before")
        executor.execute(command.taskId, state.stateId, before, timeoutMs = 40_000,
            effect = {
                currentCoroutineContext().ensureActive()
                controlCheckpoint()
                ui.ensureReady(command.targetPackage)
                if (ui.inspect(command.targetPackage, postcondition)?.visible == true) {
                    throw ExecutorFailure("POSTCONDITION_ALREADY_MET", "Commit postcondition changed before effect")
                }
                ui.tapOnce(command.targetPackage, locator)
            },
            postconditionEvidence = {
                var reference: String? = null
                for (attempt in 0 until 20) {
                    currentCoroutineContext().ensureActive()
                    controlCheckpoint()
                    ui.ensureReady(command.targetPackage)
                    val node = ui.inspect(command.targetPackage, postcondition)
                    if (node?.visible == true && node.enabled) {
                        reference = evidence(command.taskId, identity.actionKey, "after")
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
