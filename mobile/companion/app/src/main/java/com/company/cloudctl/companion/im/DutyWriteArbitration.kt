package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.runtime.DeviceArbiter
import java.time.LocalTime

/**
 * I10 (fleet-first-20260916.1): the formalized write arbitration duty must pass
 * before ANY navigation. This is not a second arbiter — [DeviceArbiter] stays
 * the enforcement point that rejects individual IM_DUTY writes while a task /
 * remote / edge session holds the device. This object formalizes the duty-side
 * ENTRY decision that previously lived as inline booleans in
 * DutyController.tick ("who holds the device write right now, duty proceeds or
 * yields to whom"), so the arbitration order itself is unit-testable:
 *
 *  1. config gate (monitor enabled, DUTY mode inside the window, xianyu monitored),
 *  2. arbiter ownership: an active task session (RUNNING) or a remote/edge
 *     grant owns the device — duty yields,
 *  3. FLEET-21 store guard: ANY un-finished task row (queued / running /
 *     paused / resume-check / reconciling / start-blocked / release-blocked,
 *     [AutomationStore.hasUnfinishedTaskRows]) means an automation task may
 *     start acting at any moment — duty yields even though no session is
 *     minted yet. Publishing (发品) and duty triggering at the same time
 *     therefore always resolves to exactly one UI writer: the task.
 *  4. otherwise duty holds the opportunistic write right until a real write is
 *     denied by the arbiter.
 *
 * Pure Kotlin, no Android imports: JVM unit-testable.
 */
object DutyWriteArbitration {

    /** Who currently owns (or blocks) the device write right. */
    enum class WriteHolder { DUTY, TASK_SESSION, REMOTE_SESSION, EDGE_SESSION, TASK_ROW, DUTY_CONFIG }

    /**
     * @param holder the single current owner of the device write right;
     *   DUTY_CONFIG means duty itself is switched off (no writer contest).
     * @param code stable audit log code (DUTY_* / ARB_*).
     */
    data class Decision(val holder: WriteHolder, val code: String, val detail: String? = null) {
        val dutyMayWrite: Boolean get() = holder == WriteHolder.DUTY
    }

    /** Ownership snapshot taken from the arbiter + store at one instant. */
    data class OwnershipSnapshot(
        val activeTaskSessionId: String? = null,
        val activeRemoteSession: Boolean = false,
        val activeEdgeSession: Boolean = false,
        val unfinishedTaskRows: Boolean = false,
    ) {
        companion object {
            /** Live snapshot: the process-wide arbiter plus the FLEET-21 store guard. */
            fun capture(arbiter: DeviceArbiter, store: AutomationStore): OwnershipSnapshot =
                OwnershipSnapshot(
                    activeTaskSessionId = arbiter.activeTaskSession()?.taskId,
                    activeRemoteSession = arbiter.activeRemoteSessionEpoch() != null,
                    activeEdgeSession = arbiter.activeEdgeSessionEpoch() != null,
                    unfinishedTaskRows = store.hasUnfinishedTaskRows(),
                )
        }
    }

    /**
     * The single duty entry decision. Order matters and is frozen: config first
     * (a disabled monitor never reports yield-to-task), then live ownership,
     * then the FLEET-21 pending-row guard (a queued row may mint a session at
     * any instant, so it wins over duty even while the arbiter is momentarily
     * idle).
     */
    fun decide(
        config: ImMonitorConfig,
        ownership: OwnershipSnapshot,
        now: LocalTime = LocalTime.now(),
    ): Decision = when {
        !config.enabled -> Decision(WriteHolder.DUTY_CONFIG, "DUTY_DISABLED", "monitor disabled")
        !config.dutyActive(now) -> Decision(WriteHolder.DUTY_CONFIG, "DUTY_OFF_WINDOW", "outside duty window")
        ImMonitorConfig.PLATFORM_XIANYU !in config.platforms ->
            Decision(WriteHolder.DUTY_CONFIG, "DUTY_PLATFORM_NOT_MONITORED", "xianyu not monitored")
        ownership.activeTaskSessionId != null -> Decision(
            WriteHolder.TASK_SESSION,
            "DUTY_YIELD_TASK_SESSION",
            "task ${ownership.activeTaskSessionId} is RUNNING",
        )
        ownership.activeRemoteSession -> Decision(
            WriteHolder.REMOTE_SESSION, "DUTY_YIELD_REMOTE_SESSION", "remote live grant active",
        )
        ownership.activeEdgeSession -> Decision(
            WriteHolder.EDGE_SESSION, "DUTY_YIELD_EDGE_SESSION", "edge grant active",
        )
        ownership.unfinishedTaskRows -> Decision(
            WriteHolder.TASK_ROW,
            "DUTY_YIELD_TASK_ROW",
            "queued/blocked/running task row may act at any moment (FLEET-21)",
        )
        else -> Decision(WriteHolder.DUTY, "DUTY_WRITE_GRANTED", null)
    }
}
