package com.company.cloudctl.companion.automation

import kotlinx.coroutines.delay
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import java.time.Instant

data class LocalNodeState(
    val enabled: Boolean,
    val visible: Boolean,
    val clickable: Boolean,
    val editable: Boolean,
    val text: String?,
)

data class ScreenshotEvidence(val path: String, val size: Long, val sha256: String)

class ExecutorFailure(
    val code: String,
    message: String,
    cause: Throwable? = null,
) : IllegalStateException(message, cause)

interface LocalAutomationUi {
    fun ensureReady(targetPackage: String)
    fun inspect(targetPackage: String, locatorRef: String): LocalNodeState?
    fun visibleTextContains(expected: String): Boolean = false
    suspend fun tap(targetPackage: String, locatorRef: String)
    suspend fun tapOnce(targetPackage: String, locatorRef: String) {
        throw ExecutorFailure("SINGLE_SHOT_UNAVAILABLE", "UI does not provide a single-shot tap")
    }
    suspend fun replaceText(targetPackage: String, locatorRef: String, value: String)
    suspend fun screenshot(taskId: String, label: String): ScreenshotEvidence
    suspend fun swipeUp() {}
    fun log(level: LogLevel, messageCode: String)
}

class LocalAutomationExecutor(
    private val ui: LocalAutomationUi,
    private val now: () -> Instant = Instant::now,
    private val elapsedMs: () -> Long = { android.os.SystemClock.elapsedRealtime() },
    private val sleep: suspend (Long) -> Unit = { delay(it) },
    private val commitGate: CommitGate? = null,
) {
    suspend fun execute(
        task: AutomationTask,
        control: ExecutionControl? = null,
        startAfterIndex: Int = -1,
        journal: (AutomationStep, String) -> Unit,
    ) {
        if (!task.expiresAt.isAfter(now())) throw ExecutorFailure("TASK_EXPIRED", "Task has expired")
        val runDeadline = elapsedMs() + task.maxRunSeconds * 1_000L
        var lastCompleted: AutomationStep? = task.steps.getOrNull(startAfterIndex)
        var lastCompletedIndex = startAfterIndex
        for ((index, step) in task.steps.withIndex()) {
            if (index <= startAfterIndex) continue
            ensureWithinTaskDeadline(task, runDeadline)
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            journal(step, "STARTED")
            var stopAfterCommit = false
            try {
                val remaining = (runDeadline - elapsedMs()).coerceAtLeast(1L)
                    withTimeout(minOf(step.timeoutMs, remaining)) {
                    ui.ensureReady(task.targetPackage)
                    stopAfterCommit = executeStep(
                        task,
                        step,
                        minOf(runDeadline, elapsedMs() + step.timeoutMs),
                        control,
                        lastCompleted,
                        lastCompletedIndex,
                    )
                }
            } catch (paused: TaskPausedException) {
                throw TaskPausedException(lastCompleted?.stepId, lastCompletedIndex, paused.message)
            } catch (failure: ExecutorFailure) {
                ui.log(LogLevel.ERROR, failure.code)
                throw failure
            } catch (failure: TimeoutCancellationException) {
                ui.log(LogLevel.ERROR, "STEP_TIMEOUT")
                throw ExecutorFailure("STEP_TIMEOUT", "Step ${step.stepId} exceeded its timeout", failure)
            } catch (failure: Exception) {
                ui.log(LogLevel.ERROR, "STEP_EXECUTION_FAILED")
                throw ExecutorFailure("STEP_EXECUTION_FAILED", "Step ${step.stepId} failed safely", failure)
            }
            journal(step, "SUCCEEDED")
            lastCompleted = step
            lastCompletedIndex = index
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            if (stopAfterCommit) return
        }
    }

    private suspend fun executeStep(
        task: AutomationTask,
        step: AutomationStep,
        runDeadline: Long,
        control: ExecutionControl?,
        lastCompleted: AutomationStep? = null,
        lastCompletedIndex: Int = -1,
    ): Boolean {
        when (step) {
            is AutomationStep.Find -> waitFor(
                task, step.locatorRef, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control,
                lastCompleted, lastCompletedIndex,
            )
            is AutomationStep.Tap -> {
                waitFor(
                    task, step.locatorRef, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control,
                    lastCompleted, lastCompletedIndex,
                )
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                val node = requireNode(task, step.locatorRef)
                if (!node.visible || !node.enabled) {
                    throw ExecutorFailure("NODE_NOT_CLICKABLE", "Approved locator is not safely clickable")
                }
                if (step.postconditionLocatorRef != null && matches(task, step.postconditionLocatorRef, NodeCondition.EXISTS)) {
                    throw ExecutorFailure("POSTCONDITION_ALREADY_MET", "Click postcondition was already present")
                }
                if (step.locatorRef == "xianyu_publish_button" && commitGate != null) {
                    // Irreversible submit: durable intent, one tap, then stop the run.
                    commitGate.publishOnce(task, step.locatorRef)
                    return true
                }
                ui.tap(task.targetPackage, step.locatorRef)
                step.postconditionLocatorRef?.let {
                    waitFor(task, it, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control, lastCompleted, lastCompletedIndex)
                }
            }
            is AutomationStep.Input -> {
                waitFor(
                    task, step.locatorRef, NodeCondition.EXISTS, step.pollInterval(), runDeadline, control,
                    lastCompleted, lastCompletedIndex,
                )
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                val node = requireNode(task, step.locatorRef)
                if (!node.visible || !node.enabled) {
                    throw ExecutorFailure("NODE_NOT_EDITABLE", "Approved locator is not safely editable")
                }
                ui.replaceText(task.targetPackage, step.locatorRef, step.value)
                waitForText(task, step.locatorRef, step.value, step.pollInterval(), runDeadline)
            }
            is AutomationStep.Wait -> waitFor(
                task, step.locatorRef, step.condition, step.pollMs, runDeadline, control,
                lastCompleted, lastCompletedIndex,
            )
            is AutomationStep.Screenshot -> {
                throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
                val evidence = ui.screenshot(task.taskId, step.label)
                if (evidence.size <= 0L || !SHA256.matches(evidence.sha256) || evidence.path.isBlank()) {
                    throw ExecutorFailure("SCREENSHOT_INVALID", "Screenshot evidence is incomplete")
                }
                ui.log(LogLevel.INFO, "SCREENSHOT_CAPTURED")
            }
            is AutomationStep.Assert -> if (!matches(task, step.locatorRef, step.predicate)) {
                throw ExecutorFailure("ASSERTION_FAILED", "UI assertion failed")
            }
            is AutomationStep.Log -> ui.log(step.level, step.messageCode)
        }
        return false
    }

    private fun requireNode(task: AutomationTask, locatorRef: String): LocalNodeState =
        ui.inspect(task.targetPackage, locatorRef)
            ?: throw ExecutorFailure("LOCATOR_NOT_FOUND", "Approved locator was not found")

    private fun matches(task: AutomationTask, locatorRef: String, condition: NodeCondition): Boolean {
        val node = ui.inspect(task.targetPackage, locatorRef)
        return when (condition) {
            NodeCondition.EXISTS -> node != null && node.visible
            NodeCondition.NOT_EXISTS -> node == null || !node.visible
            NodeCondition.ENABLED -> node?.visible == true && node.enabled
        }
    }

    private suspend fun waitFor(
        task: AutomationTask,
        locatorRef: String,
        condition: NodeCondition,
        pollMs: Long,
        runDeadline: Long,
        control: ExecutionControl? = null,
        lastCompleted: AutomationStep? = null,
        lastCompletedIndex: Int = -1,
    ) {
        while (true) {
            throwIfControlRequested(control, lastCompleted, lastCompletedIndex)
            ensureWithinTaskDeadline(task, runDeadline)
            ui.ensureReady(task.targetPackage)
            if (locatorRef == "xianyu_home_sell" || locatorRef == "xianyu_publish_page" || locatorRef == "xianyu_publish_success") {
                if (ui.inspect(task.targetPackage, "xianyu_draft_discard")?.visible == true) {
                    ui.tap(task.targetPackage, "xianyu_draft_discard")
                }
                if (ui.inspect(task.targetPackage, "xianyu_draft_nosave")?.visible == true) {
                    ui.tap(task.targetPackage, "xianyu_draft_nosave")
                }
                if (ui.inspect(task.targetPackage, "xianyu_publish_blocked_ack")?.visible == true) {
                    ui.tap(task.targetPackage, "xianyu_publish_blocked_ack")
                }
            }
            if ((locatorRef == "xianyu_price" || locatorRef == "xianyu_shipping" || locatorRef == "xianyu_location") &&
                !matches(task, locatorRef, condition)
            ) {
                ui.swipeUp()
            }
            if (matches(task, locatorRef, condition)) return
            sleep(pollMs)
        }
    }

    private suspend fun waitForText(
        task: AutomationTask,
        locatorRef: String,
        expected: String,
        pollMs: Long,
        runDeadline: Long,
    ) {
        while (true) {
            ensureWithinTaskDeadline(task, runDeadline)
            ui.ensureReady(task.targetPackage)
            if (ui.visibleTextContains(expected)) return
            if (locatorRef == "xianyu_price") {
                val typed = PriceKeypad.keys(expected)
                if (typed.isNotEmpty() && ui.visibleTextContains(typed)) return
            }
            val node = ui.inspect(task.targetPackage, locatorRef)
            val actual = node?.text.orEmpty()
            if (FlutterTextCommit.accepted(actual, expected)) return
            if (locatorRef == "xianyu_price" && PriceKeypad.acceptedOnForm(actual, expected)) return
            // Flutter replaces the "描述一下" hint after focus. Missing locator is not success.
            sleep(pollMs)
        }
    }

    private fun ensureWithinTaskDeadline(task: AutomationTask, runDeadline: Long) {
        if (!task.expiresAt.isAfter(now())) throw ExecutorFailure("TASK_EXPIRED", "Task expired during execution")
        if (elapsedMs() >= runDeadline) throw ExecutorFailure("TASK_TIMEOUT", "Task exceeded its local runtime limit")
    }

    private fun throwIfControlRequested(
        control: ExecutionControl?,
        lastCompleted: AutomationStep? = null,
        lastCompletedIndex: Int = -1,
    ) {
        when {
            control == null -> return
            control.cancelRequested -> throw ExecutorFailure("CANCELLED", control.reason ?: "Task was cancelled")
            control.pauseRequested -> throw TaskPausedException(
                lastCompleted?.stepId,
                lastCompletedIndex,
                control.reason,
            )
        }
    }

    private fun AutomationStep.pollInterval() = minOf(200L, timeoutMs)

    private companion object {
        val SHA256 = Regex("^[a-f0-9]{64}$")
    }
}
