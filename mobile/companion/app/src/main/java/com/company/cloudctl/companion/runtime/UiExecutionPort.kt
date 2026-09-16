package com.company.cloudctl.companion.runtime

/**
 * B10 narrow, arbitrated UI write port. New writers (feature/adapter
 * directories built by later agents) must go through this port — never
 * around it — so that Recipe execution, fixed steps, IME text commits, IM
 * duty navigation, remote live gestures, and Edge writes all arbitrate
 * through the single [DeviceArbiter] (fleet-identity/v1@20260916.1 §6.3).
 *
 * Semantics:
 *  - [launchTarget]/[back]/[replaceText] suspend and throw
 *    [ArbiterDenialException] when the write is rejected; the caller fails
 *    closed and the rejection is already recorded by the arbiter.
 *  - [submitGestureTap]/[submitGestureSwipe] are fire-and-forget: they
 *    return false when rejected and never dispatch (a late remote command
 *    must not land, and must not crash the transport thread).
 *  - Task-channel callers pass the [TaskSession.fencingToken]; remote/edge
 *    callers pass their granted epoch. The token is checked before EVERY
 *    write, not once per run.
 *  - One-shot irreversible actions must additionally pass the pre-existing
 *    local persistent barrier (automation/IrreversibleActionGate.kt over the
 *    AutomationStore action journal) before their single strike.
 *  - Passive listeners (node inspection, bubble reads, order rows,
 *    screenshots) never navigate and never use this port.
 */
interface UiExecutionPort {
    val arbiter: DeviceArbiter

    suspend fun launchTarget(
        writer: UiWriter,
        targetPackage: String,
        fencingToken: Long? = null,
    )

    suspend fun back(writer: UiWriter, fencingToken: Long? = null)

    suspend fun replaceText(
        writer: UiWriter,
        targetPackage: String,
        locatorRef: String,
        value: String,
        fencingToken: Long? = null,
    )

    /** Returns false (and records) when the gesture write is rejected. */
    fun submitGestureTap(
        writer: UiWriter,
        x: Double,
        y: Double,
        epoch: Long? = null,
        detail: String? = null,
    ): Boolean

    /** Returns false (and records) when the gesture write is rejected. */
    fun submitGestureSwipe(
        writer: UiWriter,
        x1: Double,
        y1: Double,
        x2: Double,
        y2: Double,
        epoch: Long? = null,
    ): Boolean
}

/** Raw, un-arbitrated device operations supplied by the accessibility adapter. */
interface RawUiOps {
    suspend fun launchTargetApp(targetPackage: String)

    fun globalBack()

    fun submitGestureTap(x: Double, y: Double)

    fun submitGestureSwipe(x1: Double, y1: Double, x2: Double, y2: Double)

    suspend fun replaceText(targetPackage: String, locatorRef: String, value: String)
}

/** Raised by the suspending port writes when the arbiter rejects them. */
class ArbiterDenialException(
    val denial: ArbiterDenial,
) : RuntimeException("arbiter rejected ${denial.writer}/${denial.kind}: ${denial.reason}")

/**
 * Pure JVM adapter: arbitration wrapped around [RawUiOps]. The accessibility
 * service plugs its existing (already device-tested) operations in as the
 * [RawUiOps] adapter — no behaviour is reimplemented here.
 */
class ArbiterGuardedUiExecutionPort(
    override val arbiter: DeviceArbiter,
    private val ops: RawUiOps,
) : UiExecutionPort {

    override suspend fun launchTarget(
        writer: UiWriter,
        targetPackage: String,
        fencingToken: Long?,
    ) {
        demand(arbiter.request(writer, UiWriteKind.LAUNCH, fencingToken, "launch $targetPackage"))
        ops.launchTargetApp(targetPackage)
    }

    override suspend fun back(writer: UiWriter, fencingToken: Long?) {
        demand(arbiter.request(writer, UiWriteKind.BACK, fencingToken, "back"))
        ops.globalBack()
    }

    override suspend fun replaceText(
        writer: UiWriter,
        targetPackage: String,
        locatorRef: String,
        value: String,
        fencingToken: Long?,
    ) {
        demand(arbiter.request(writer, UiWriteKind.TEXT_INPUT, fencingToken, "replaceText $locatorRef"))
        ops.replaceText(targetPackage, locatorRef, value)
    }

    override fun submitGestureTap(
        writer: UiWriter,
        x: Double,
        y: Double,
        epoch: Long?,
        detail: String?,
    ): Boolean {
        val decision = arbiter.request(writer, UiWriteKind.TAP, epoch, detail ?: "tap $x,$y")
        if (decision is ArbiterDecision.Denied) return false
        ops.submitGestureTap(x, y)
        return true
    }

    override fun submitGestureSwipe(
        writer: UiWriter,
        x1: Double,
        y1: Double,
        x2: Double,
        y2: Double,
        epoch: Long?,
    ): Boolean {
        val decision = arbiter.request(writer, UiWriteKind.SWIPE, epoch, "swipe $x1,$y1->$x2,$y2")
        if (decision is ArbiterDecision.Denied) return false
        ops.submitGestureSwipe(x1, y1, x2, y2)
        return true
    }

    private fun demand(decision: ArbiterDecision) {
        if (decision is ArbiterDecision.Denied) {
            throw ArbiterDenialException(decision.denial)
        }
    }
}
