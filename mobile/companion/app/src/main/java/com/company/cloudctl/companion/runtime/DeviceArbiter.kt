package com.company.cloudctl.companion.runtime

import java.util.ArrayDeque

/**
 * B10 single-writer device arbiter (fleet-identity/v1@20260916.1 §6.3):
 * every Companion-side UI write path — Recipe execution, fixed steps, IME
 * text commits, IM duty navigation, remote live gestures, Edge writes — must
 * request arbitration here before touching the device. Passive listeners
 * (node inspection, chat bubbles, order-row reads, screenshots) never
 * navigate and never arbitrate.
 *
 * Ownership model:
 *  - At most one TASK session may be active; it is minted when a claimed task
 *    passes its execution boundary (fresh-claim heartbeat confirmed) and is
 *    returned at a safe boundary ([ReleaseBoundary]) on completion, pause,
 *    cancel, failure, or pre-execution release.
 *  - A REMOTE_LIVE / EDGE session is an epoch-scoped grant (remote
 *    take-control). A remote->auto handover supersedes the grant: the ack
 *    records the acknowledged remote epoch and the new control epoch, and any
 *    late command carrying the superseded epoch is denied (never lands).
 *  - IM_DUTY writes are opportunistic: allowed only while the arbiter is
 *    fully idle. While a task session is RUNNING, every duty launch/back/tap/
 *    text write is denied and recorded.
 *
 * Fencing: [controlEpoch] increases on every ownership change. The task
 * session carries the [TaskSession.fencingToken] observed at begin; task
 * writes present it (explicitly from the integration seams, implicitly from
 * the executor context) and it is re-checked before every write.
 *
 * One-shot irreversible actions additionally require the pre-existing local
 * persistent barrier (automation/IrreversibleActionGate.kt over the
 * AutomationStore action journal) — the arbiter does not duplicate it.
 *
 * Pure Kotlin, thread-safe; unit-testable on the JVM.
 */
class DeviceArbiter(
    private val maxRecordedDenials: Int = DEFAULT_MAX_DENIALS,
    private val onDenial: ((ArbiterDenial) -> Unit)? = null,
) {
    private val lock = Any()

    private var epoch: Long = 0L
    private var task: TaskSession? = null
    private var remoteEpoch: Long? = null
    private var edgeEpoch: Long? = null

    // Superseded ownership markers: a straggler write presenting one of these
    // is a late command from an already-ended/already-handed-over owner and
    // is reported as EPOCH_STALE (never NOT_HOLDER, never allowed).
    private var lastEndedTaskToken: Long? = null
    private var supersededRemoteEpoch: Long? = null
    private var supersededEdgeEpoch: Long? = null

    private val recordedDenials = ArrayDeque<ArbiterDenial>()
    private var denialSeq: Long = 0L

    /** Monotonic control epoch; advances on every ownership change. */
    val controlEpoch: Long get() = synchronized(lock) { epoch }

    fun hasActiveTaskSession(): Boolean = synchronized(lock) { task != null }

    fun activeTaskSession(): TaskSession? = synchronized(lock) { task }

    fun activeRemoteSessionEpoch(): Long? = synchronized(lock) { remoteEpoch }

    fun activeEdgeSessionEpoch(): Long? = synchronized(lock) { edgeEpoch }

    /**
     * Remote (live) take-control grant. Returns the granted epoch; remote
     * writes must present it. Refused while a task session is active — auto
     * owns the device during RUNNING.
     */
    fun beginRemoteSession(): Long = synchronized(lock) {
        check(task == null) { "a task session is active; remote cannot take the device" }
        epoch += 1
        remoteEpoch = epoch
        epoch
    }

    /** Ends the remote grant; a late (already-superseded) end is a no-op. */
    fun endRemoteSession(grantedEpoch: Long): Boolean = synchronized(lock) {
        if (remoteEpoch != grantedEpoch) return false
        epoch += 1
        remoteEpoch = null
        true
    }

    /** Edge-write grant, mirroring the remote session semantics. */
    fun beginEdgeSession(): Long = synchronized(lock) {
        check(task == null) { "a task session is active; edge cannot take the device" }
        epoch += 1
        edgeEpoch = epoch
        epoch
    }

    fun endEdgeSession(grantedEpoch: Long): Boolean = synchronized(lock) {
        if (edgeEpoch != grantedEpoch) return false
        epoch += 1
        edgeEpoch = null
        true
    }

    /**
     * Begins the single task session (execution boundary crossed). Any active
     * remote/edge grant is superseded — this IS the remote->auto handover.
     * The returned session carries the ack for the superseded grant (null
     * when none was active), the new control epoch, and the fencing token.
     */
    fun beginTaskSession(taskId: String): TaskSession = synchronized(lock) {
        check(task == null) { "task session already active for ${task?.taskId}; single writer per device" }
        val ackedRemote = remoteEpoch
        val ackedEdge = edgeEpoch
        epoch += 1
        remoteEpoch = null
        edgeEpoch = null
        if (ackedRemote != null) supersededRemoteEpoch = ackedRemote
        if (ackedEdge != null) supersededEdgeEpoch = ackedEdge
        val ack = if (ackedRemote == null && ackedEdge == null) {
            null
        } else {
            HandoverAck(
                taskId = taskId,
                ackedRemoteEpoch = ackedRemote,
                ackedEdgeEpoch = ackedEdge,
                controlEpoch = epoch,
                fencingToken = epoch,
            )
        }
        TaskSession(
            taskId = taskId,
            fencingToken = epoch,
            handoverAck = ack,
        ).also { task = it }
    }

    /**
     * Returns the device at a safe boundary. A late or duplicate release
     * (stale token, no session) is ignored — the device is never freed twice
     * and a straggler cannot free a successor's session.
     */
    fun endTaskSession(fencingToken: Long, boundary: ReleaseBoundary): Boolean = synchronized(lock) {
        val current = task ?: return false
        if (current.fencingToken != fencingToken) return false
        epoch += 1
        task = null
        lastEndedTaskToken = fencingToken
        true
    }

    /**
     * The single arbitration point, evaluated before every UI write.
     * Rejections are recorded (bounded) and surfaced to [onDenial].
     */
    fun request(
        writer: UiWriter,
        kind: UiWriteKind,
        fencingToken: Long? = null,
        detail: String? = null,
    ): ArbiterDecision = synchronized(lock) {
        val deniedReason = arbitrateLocked(writer, kind, fencingToken)
        if (deniedReason != null) {
            denialSeq += 1
            val denial = ArbiterDenial(
                seq = denialSeq,
                writer = writer,
                kind = kind,
                reason = deniedReason,
                controlEpoch = epoch,
                fencingToken = fencingToken,
                detail = detail,
            )
            if (recordedDenials.size >= maxRecordedDenials) recordedDenials.pollFirst()
            recordedDenials.addLast(denial)
            onDenial?.invoke(denial)
            ArbiterDecision.Denied(deniedReason, denial)
        } else {
            ArbiterDecision.Allowed
        }
    }

    /** Snapshot of the bounded rejection record (oldest first). */
    fun denials(): List<ArbiterDenial> = synchronized(lock) { recordedDenials.toList() }

    fun clearRecordedDenials() = synchronized(lock) { recordedDenials.clear() }

    /** Returns the denial reason, or null when the write is allowed. */
    private fun arbitrateLocked(
        writer: UiWriter,
        kind: UiWriteKind,
        fencingToken: Long?,
    ): ArbiterDenialReason? {
        return when (writer) {
            UiWriter.TASK -> {
                val current = task
                when {
                    current != null && fencingToken != null && fencingToken != current.fencingToken ->
                        // Late write after the session was returned at a safe
                        // boundary (cancel/pause/rebind/handover): must not land.
                        ArbiterDenialReason.EPOCH_STALE
                    current != null -> null
                    // No active session, but the token names the most recently
                    // ended one: a straggler from a finished run.
                    fencingToken != null && fencingToken == lastEndedTaskToken ->
                        ArbiterDenialReason.EPOCH_STALE
                    else -> ArbiterDenialReason.NOT_HOLDER
                }
            }
            UiWriter.IM_DUTY -> when {
                // RUNNING owns the device: duty launch/back/tap/text-input are
                // all rejected (fleet-identity §6.3).
                task != null -> ArbiterDenialReason.DEVICE_BUSY
                remoteEpoch != null || edgeEpoch != null -> ArbiterDenialReason.DEVICE_BUSY
                else -> null
            }
            UiWriter.REMOTE_LIVE -> when {
                // A command carrying an epoch explicitly superseded by a
                // remote->auto handover is late — that verdict wins even while
                // the successor task is RUNNING.
                fencingToken != null && fencingToken == supersededRemoteEpoch ->
                    ArbiterDenialReason.EPOCH_STALE
                task != null -> ArbiterDenialReason.DEVICE_BUSY
                // No registered grant yet (legacy live wiring): preserve the
                // current permissive behaviour while idle. Once the live
                // adapter registers its session, the epoch check below gates
                // every command.
                remoteEpoch == null && fencingToken == null -> null
                remoteEpoch == null -> ArbiterDenialReason.NOT_HOLDER
                fencingToken == null || fencingToken != remoteEpoch ->
                    // Late command after the grant ended or was superseded:
                    // the stale epoch never lands.
                    ArbiterDenialReason.EPOCH_STALE
                else -> null
            }
            UiWriter.EDGE -> when {
                fencingToken != null && fencingToken == supersededEdgeEpoch ->
                    ArbiterDenialReason.EPOCH_STALE
                task != null -> ArbiterDenialReason.DEVICE_BUSY
                remoteEpoch != null -> ArbiterDenialReason.DEVICE_BUSY
                edgeEpoch == null && fencingToken == null -> null
                edgeEpoch == null -> ArbiterDenialReason.NOT_HOLDER
                fencingToken == null || fencingToken != edgeEpoch ->
                    ArbiterDenialReason.EPOCH_STALE
                else -> null
            }
        }
    }

    companion object {
        const val DEFAULT_MAX_DENIALS = 64
    }
}

/** Writer channels that must arbitrate; passive listeners are absent by design. */
enum class UiWriter { TASK, IM_DUTY, REMOTE_LIVE, EDGE }

/** The UI write families the arbiter is asked about. */
enum class UiWriteKind { LAUNCH, BACK, TAP, TEXT_INPUT, SWIPE }

sealed interface ArbiterDecision {
    data object Allowed : ArbiterDecision
    data class Denied(val reason: ArbiterDenialReason, val denial: ArbiterDenial) : ArbiterDecision
}

enum class ArbiterDenialReason { DEVICE_BUSY, EPOCH_STALE, NOT_HOLDER }

/** Bounded, ordered rejection record (arbiter rejects AND records). */
data class ArbiterDenial(
    val seq: Long,
    val writer: UiWriter,
    val kind: UiWriteKind,
    val reason: ArbiterDenialReason,
    val controlEpoch: Long,
    val fencingToken: Long?,
    val detail: String?,
)

/** The device write lease held by one RUNNING task between safe boundaries. */
data class TaskSession(
    val taskId: String,
    val fencingToken: Long,
    val handoverAck: HandoverAck?,
)

/**
 * remote->auto handover ack: the superseded remote/edge grant epoch(s) are
 * acknowledged, the control epoch advances, and the task fencing token is
 * minted from the new epoch. Late commands carrying the acknowledged epoch
 * are denied from this point on.
 */
data class HandoverAck(
    val taskId: String,
    val ackedRemoteEpoch: Long?,
    val ackedEdgeEpoch: Long?,
    val controlEpoch: Long,
    val fencingToken: Long,
)

/**
 * Safe boundaries at which the task session is returned. Cancel, pause, and
 * rebind hand the device back only at these points; writes between the
 * boundary decision and the session release are still fenced by the token.
 */
enum class ReleaseBoundary { COMPLETED, PAUSED_CHECKPOINT, CANCELLED, FAILED, RELEASED_PRE_EXECUTION }

/** Process-wide single arbiter (main process: sync service, accessibility, duty, live). */
object DeviceArbiterHolder {
    @Volatile
    private var instance: DeviceArbiter? = null

    @JvmStatic
    fun get(): DeviceArbiter = instance ?: synchronized(this) {
        instance ?: DeviceArbiter(onDenial = { denial ->
            android.util.Log.w(
                "DeviceArbiter",
                "ARBITER_DENY seq=${denial.seq} writer=${denial.writer} kind=${denial.kind} " +
                    "reason=${denial.reason} epoch=${denial.controlEpoch} detail=${denial.detail}",
            )
        }).also { instance = it }
    }
}
