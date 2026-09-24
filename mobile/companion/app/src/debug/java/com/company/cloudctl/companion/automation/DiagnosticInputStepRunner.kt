package com.company.cloudctl.companion.automation

import com.company.cloudctl.companion.ime.InputChannel
import com.company.cloudctl.companion.ime.InputProof
import com.company.cloudctl.companion.ime.InputProofProjection
import com.company.cloudctl.companion.ime.InputProofProjector
import com.company.cloudctl.companion.ime.InputRoutePolicy
import com.company.cloudctl.companion.runtime.DeviceArbiter
import com.company.cloudctl.companion.runtime.DeviceArbiterHolder
import com.company.cloudctl.companion.runtime.ReleaseBoundary
import java.time.Instant

/**
 * Debug-only one-step runner for the isolated input field.
 *
 * It constructs the fixed package, the fixed locator and exactly one
 * [AutomationStep.Input] itself. Callers cannot supply a package, a locator,
 * a second step, or any other action. The step is then executed by
 * [LocalAutomationExecutor], whose input path calls
 * [CloudCtlAccessibilityService.replaceText] and therefore the normal
 * [com.company.cloudctl.companion.runtime.DeviceArbiter] task-session demand.
 * This class never calls rawReplaceText or [com.company.cloudctl.companion.runtime.UiExecutionPort].
 *
 * There is no cloud claim, no network, and no launch of a business app.
 * Release does not compile this file.
 */
internal class DiagnosticInputStepRunner(
    private val ui: LocalAutomationUi,
    private val arbiter: DeviceArbiter = DeviceArbiterHolder.get(),
    private val sdkInt: Int,
    private val now: () -> Instant = Instant::now,
    private val elapsedMs: () -> Long = { android.os.SystemClock.elapsedRealtime() },
    private val sleep: suspend (Long) -> Unit = {},
) {
    /**
     * Runs the one fixed step under a fresh task session and always releases it.
     * [text] is the fixture. It is not logged; the returned projection carries
     * only its length and digest.
     */
    suspend fun runOnce(text: String): InputProofProjection {
        val channel = InputRoutePolicy.channel(sdkInt).name
        if (text.isBlank() || text.length > CompleteTextLimit) {
            return InputProofProjector.failure("INPUT_REJECTED", channel)
        }
        val task = fixedTask(text)
        val session = arbiter.beginTaskSession(TASK_ID)
        val executor = LocalAutomationExecutor(
            ui = ui,
            now = now,
            elapsedMs = elapsedMs,
            sleep = sleep,
        )
        return try {
            executor.execute(task) { _, _ -> }
            // The proof replaceText just minted. A chat send proof is a different
            // slot and is not read here. Missing proof is not success, and a proof
            // left over from an earlier field is not this write.
            val proof = ui.lastInputProof()
                ?: return InputProofProjector.failure("INPUT_READBACK_UNAVAILABLE", channel)
            if (proof.expected != text || proof.targetPackage != DebugDiagnosticInputPolicy.PACKAGE ||
                proof.locatorRef != DebugDiagnosticInputPolicy.FIELD
            ) {
                return InputProofProjector.failure("INPUT_REJECTED", channel)
            }
            // Complete equality against the field node. A page substring is not
            // consulted. A node that cannot show the text fails closed.
            val node = ui.inspect(DebugDiagnosticInputPolicy.PACKAGE, DebugDiagnosticInputPolicy.FIELD)
            if (node?.text != text) {
                return InputProofProjector.failure("INPUT_REJECTED", channel)
            }
            // The proof and the live node must name the same field. Text equality
            // alone is not enough: a proof minted for an older node fails closed.
            if (proof.nodeKey.isNullOrBlank() || node.nodeKey.isNullOrBlank() || proof.nodeKey != node.nodeKey) {
                return InputProofProjector.failure("INPUT_TARGET_CHANGED", channel)
            }
            val commits = proof.commitCount
                ?: return InputProofProjector.failure("INPUT_READBACK_UNAVAILABLE", channel)
            if (commits != 0 && commits != 1) {
                return InputProofProjector.failure("INPUT_REJECTED", channel)
            }
            InputProofProjector.project(proof, channel, commits)
        } catch (failure: ExecutorFailure) {
            InputProofProjector.failure(failure.code, channel)
        } finally {
            arbiter.endTaskSession(session.fencingToken, ReleaseBoundary.COMPLETED)
        }
    }

    /**
     * The only task this runner can build. A second step, a business package,
     * or a non-input action cannot be represented here.
     */
    fun fixedTask(text: String): AutomationTask {
        require(text.length <= CompleteTextLimit) { "fixture exceeds the verified window" }
        val issued = now()
        return AutomationTask(
            taskId = TASK_ID,
            deviceId = DEVICE_ID,
            targetPackage = DebugDiagnosticInputPolicy.PACKAGE,
            issuedAt = issued,
            expiresAt = issued.plusSeconds(60),
            maxRunSeconds = 30,
            steps = listOf(fixedStep(text)),
        )
    }

    fun fixedStep(text: String): AutomationStep.Input = AutomationStep.Input(
        stepId = STEP_ID,
        timeoutMs = 15_000L,
        locatorRef = DebugDiagnosticInputPolicy.FIELD,
        value = text,
        sensitive = false,
    )

    /** Rejects anything that is not the one fixed input step. Used by tests. */
    fun accepts(task: AutomationTask): Boolean {
        if (task.targetPackage != DebugDiagnosticInputPolicy.PACKAGE) return false
        if (task.steps.size != 1) return false
        val step = task.steps.single()
        return step is AutomationStep.Input && step.locatorRef == DebugDiagnosticInputPolicy.FIELD
    }

    companion object {
        const val TASK_ID = "diag-input-0001"
        const val DEVICE_ID = "diag-device"
        const val STEP_ID = "diag-input"
        const val CompleteTextLimit = 10_000

        /**
         * The only fixture a device may run. Callers cannot pass a package, a
         * locator, a step, or a text. The string is compiled in; it is not an
         * intent extra.
         */
        const val FIXTURE = "你好🙂\n第二行"

        /**
         * Device entry. Uses the accessibility service that is already connected
         * in this process as a [LocalAutomationUi], and the same
         * [DeviceArbiterHolder] that service uses. The runner then calls
         * [LocalAutomationExecutor] itself.
         *
         * It does not call [CloudCtlAccessibilityService.execute]. That method
         * launches the target before the executor runs. The harness activity
         * must already be the foreground window; this entry never launches,
         * goes back, or restarts anything, and it never starts the sync service.
         */
        suspend fun runFixedOnActiveService(sdkInt: Int): InputProofProjection {
            val service = CloudCtlAccessibilityService.active
                ?: return InputProofProjector.failure(
                    "ACCESSIBILITY_NOT_ACTIVE",
                    channelName(sdkInt),
                )
            // A retry that never reaches replaceText must not leave the previous
            // proof readable. replaceTextReturningProof clears again before it writes.
            service.discardFieldProof()
            return DiagnosticInputStepRunner(
                ui = service,
                sdkInt = sdkInt,
            ).runOnce(FIXTURE)
        }

        fun channelName(sdkInt: Int): String = when (InputRoutePolicy.channel(sdkInt)) {
            InputChannel.ACCESSIBILITY -> InputChannel.ACCESSIBILITY.name
            InputChannel.TEMPORARY_IME -> InputChannel.TEMPORARY_IME.name
            InputChannel.MANUAL_IME -> InputChannel.MANUAL_IME.name
        }
    }
}
