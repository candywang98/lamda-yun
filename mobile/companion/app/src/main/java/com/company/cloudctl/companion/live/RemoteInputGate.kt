package com.company.cloudctl.companion.live

import com.company.cloudctl.companion.runtime.ArbiterDecision
import com.company.cloudctl.companion.runtime.ArbiterDenialReason
import com.company.cloudctl.companion.runtime.DeviceArbiter
import com.company.cloudctl.companion.runtime.UiWriteKind
import com.company.cloudctl.companion.runtime.UiWriter

/**
 * L11 remote-input gate: the single decision point every remote gesture must
 * pass before it is dispatched (K13 live-capabilities/v1@20260917.1 §2–§5,
 * B10 single-writer, BLK-008 device side).
 *
 * This closes the slice1 zero-journal path: remoteTap/remoteSwipe no longer
 * reach the gesture channel on the WS thread's own authority. Every gesture
 * now runs the full pipeline:
 *
 *  1. session state must be REMOTE (else LIVE_INPUT_FORBIDDEN);
 *  2. input seq must advance the session watermark (else INPUT_SEQ_REGRESSION;
 *     the watermark only moves when a gesture actually executes, mirroring
 *     fleet_live.check_input);
 *  3. the targeted frame must still be fresh (watermark + TTL, else
 *     INPUT_EXPIRED — stale-frame clicks never land);
 *  4. the B10 AutomationStore must have no unfinished task rows (else
 *     LIVE_DEVICE_BUSY — remote input never runs concurrently with
 *     automation; the probe is strictly read-only and this gate performs no
 *     resume: PAUSED rows stay PAUSED, recovery follows the existing
 *     pause/resume semantics after handover);
 *  5. coordinates are inverse-transformed against the geometry of the exact
 *     targeted frame (rotation-aware); off-plane or safe-area results are
 *     dropped (never clamped) with a reason code;
 *  6. the B10 [DeviceArbiter] must allow the write: take-control mints an
 *     epoch-scoped remote grant ([beginRemote]), every gesture presents it,
 *     and release/teardown returns it — so a superseded or expired epoch is
 *     denied and journaled (arbiter denial record + audit event), and a
 *     running task session blocks the grant outright.
 *
 * Every outcome — executed or rejected — emits a metadata-only audit event
 * (kind/seq/frameSeq/coords/session; never frame content, K13 §6).
 *
 * Pure Kotlin, JVM-unit-testable; all collaborators are injected.
 */
class RemoteInputGate(
    sessionId: String,
    private val machine: LiveClientStateMachine,
    private val ledger: FrameLedger,
    private val arbiter: DeviceArbiter,
    private val unfinishedTaskRows: () -> Boolean,
    private val auditor: (LiveInputAudit) -> Unit,
    private val clock: () -> Long,
) {
    private val lock = Any()

    /** The epoch-scoped remote lease minted at take-control; null while not REMOTE. */
    var leaseEpoch: Long? = null
        private set

    /** Session id, bindable once (blank until the REST poll names the session). */
    var sessionId: String = sessionId
        private set

    /**
     * Binds the real session id once it is known (the controller builds the
     * gate before the REST poll returns the sid). Must happen before any
     * take-control/input event; refuses a re-bind to a different session.
     */
    fun bind(sessionId: String) {
        synchronized(lock) {
            check(this.sessionId.isBlank() || this.sessionId == sessionId) {
                "gate already bound to ${this.sessionId}"
            }
            this.sessionId = sessionId
        }
    }

    /**
     * Take-control: mints the arbiter remote grant FIRST (a RUNNING task
     * session owns the device and refuses the grant — automation and remote
     * input never run concurrently), then mirrors the server transition into
     * REMOTE. Returns the lease, or null when the device cannot hand over
     * (arbiter refusal; the session stays VIEWING and inputs are rejected).
     */
    fun beginRemote(): RemoteLease? = synchronized(lock) {
        val now = clock()
        if (machine.state != LiveClientState.VIEWING) {
            audit(now, EVENT_TAKE_CONTROL_REJECTED, code = CODE_NOT_REMOTE, detail = "state=${machine.state}")
            return null
        }
        val epoch = try {
            arbiter.beginRemoteSession()
        } catch (error: IllegalStateException) {
            // A task session (or another grant) owns the device right now.
            audit(now, EVENT_TAKE_CONTROL_REJECTED, code = CODE_DEVICE_BUSY, detail = error.message)
            return null
        }
        machine.onTakeControl()
        leaseEpoch = epoch
        audit(now, EVENT_TAKE_CONTROL, epoch = epoch)
        RemoteLease(sessionId = sessionId, epoch = epoch)
    }

    /**
     * Release / teardown: mirrors the state back to VIEWING and returns the
     * arbiter grant. Safe to call from any state (idempotent); a lease that
     * was already superseded by a remote->auto handover is a no-op on the
     * arbiter side. PAUSED task rows are deliberately left untouched.
     */
    fun endRemote(cause: String = CAUSE_RELEASE): Boolean = synchronized(lock) {
        val epoch = leaseEpoch ?: return false
        if (machine.state == LiveClientState.REMOTE) {
            machine.onRelease()
        }
        arbiter.endRemoteSession(epoch)
        leaseEpoch = null
        audit(clock(), EVENT_RELEASE, epoch = epoch, detail = cause)
        true
    }

    /**
     * Terminal teardown (server CLOSED / projection revoked): no state-machine
     * transition is attempted from CLOSED, the lease is returned, and the
     * session stays terminal.
     */
    fun terminate(cause: String): Boolean = synchronized(lock) {
        val epoch = leaseEpoch ?: return false
        if (machine.state == LiveClientState.REMOTE) {
            machine.onRelease()
        }
        machine.onClosed()
        arbiter.endRemoteSession(epoch)
        leaseEpoch = null
        audit(clock(), EVENT_CLOSED, epoch = epoch, detail = cause)
        true
    }

    /** Full pipeline for one remote input; see the class KDoc for the order. */
    fun evaluate(command: RemoteInputCommand): RemoteInputDecision = synchronized(lock) {
        val now = clock()

        fun reject(rejection: RemoteInputRejection, detail: String? = null): RemoteInputDecision.Rejected {
            val event = LiveInputAudit(
                event = EVENT_INPUT_REJECTED,
                sessionId = sessionId,
                seq = command.seq,
                frameSeq = command.frameSeq,
                kind = command.kind,
                code = rejection.code,
                detail = detail,
                epoch = leaseEpoch,
                atMs = now,
            )
            auditor(event)
            return RemoteInputDecision.Rejected(rejection, event)
        }

        // Rule 4 first (mirrors fleet_live.check_input): non-REMOTE rejects
        // any input regardless of content.
        if (machine.state != LiveClientState.REMOTE) {
            return reject(RemoteInputRejection.NOT_REMOTE, "state=${machine.state}")
        }
        if (command.kind == RemoteInputKind.TEXT) {
            // slice1 device channel executes tap/swipe only; text must go
            // through the replaceText pipeline with its own confirmation
            // gates, never a blind gesture.
            return reject(RemoteInputRejection.UNSUPPORTED_KIND, "text inputs are not executed by the gesture channel")
        }
        if (command.kind != RemoteInputKind.TAP && command.kind != RemoteInputKind.SWIPE) {
            return reject(RemoteInputRejection.UNSUPPORTED_KIND, "kind=${command.kind}")
        }
        // Rule 1: seq must advance the watermark. Peek only — the watermark
        // moves at commit time (server semantics), not at check time.
        if (command.seq <= 0 || command.seq <= machine.guard.last) {
            return reject(
                RemoteInputRejection.SEQ_REGRESSION,
                "seq=${command.seq} watermark=${machine.guard.last}",
            )
        }
        // Rules 2/3: frame freshness (watermark staleness, then TTL).
        when (val freshness = ledger.checkFreshness(command.frameSeq, now)) {
            is FrameFreshness.StaleWatermark -> return reject(
                RemoteInputRejection.FRAME_STALE,
                "frameSeq=${command.frameSeq} latest=${freshness.latestFrameSeq} threshold=${freshness.threshold}",
            )
            is FrameFreshness.ExpiredTtl -> return reject(
                RemoteInputRejection.FRAME_TTL,
                "frameSeq=${command.frameSeq} ageMs=${freshness.ageMs} ttlMs=${freshness.ttlMs}",
            )
            is FrameFreshness.Fresh -> Unit
        }
        // B10/BLK-008 device side: unfinished automation rows (queued,
        // running, paused, resume-check, reconciling, blocked, unresolved
        // one-shot actions) block remote gestures. Read-only probe; nothing
        // is resumed or written here.
        if (unfinishedTaskRows()) {
            return reject(
                RemoteInputRejection.TASK_ROWS_UNFINISHED,
                "AutomationStore reports unfinished task rows; resolve or stop automation before remote control",
            )
        }
        // Geometry: strict inverse against the exact targeted frame.
        val stamp = (ledger.checkFreshness(command.frameSeq, now) as FrameFreshness.Fresh).stamp
        val geometry = stamp.geometry
        val start = geometry.inverse(command.x, command.y)
        val end = when (command.kind) {
            RemoteInputKind.SWIPE -> geometry.inverse(command.x2, command.y2)
            else -> null
        }
        for (point in listOfNotNull(start, end)) {
            if (point is GeometryPoint.Rejected) {
                val rejection = when (point.reason) {
                    GeometryRejection.OUT_OF_BOUNDS -> RemoteInputRejection.OUT_OF_GEOMETRY
                    GeometryRejection.SAFE_AREA -> RemoteInputRejection.SAFE_AREA
                }
                return reject(rejection, "frameSpace=(${command.x},${command.y})-(${command.x2},${command.y2}) reason=${point.reason}")
            }
        }
        // Arbiter: the epoch-scoped remote grant must still be the holder.
        val epoch = leaseEpoch ?: return reject(
            RemoteInputRejection.ARBITER_NOT_HOLDER,
            "no active remote lease while state=REMOTE",
        )
        val writeKind = when (command.kind) {
            RemoteInputKind.TAP -> UiWriteKind.TAP
            RemoteInputKind.SWIPE -> UiWriteKind.SWIPE
            else -> return reject(RemoteInputRejection.UNSUPPORTED_KIND)
        }
        val decision = arbiter.request(
            UiWriter.REMOTE_LIVE,
            writeKind,
            epoch,
            "live sid=$sessionId seq=${command.seq} frameSeq=${command.frameSeq}",
        )
        if (decision is ArbiterDecision.Denied) {
            val rejection = when (decision.reason) {
                ArbiterDenialReason.DEVICE_BUSY -> RemoteInputRejection.ARBITER_DEVICE_BUSY
                ArbiterDenialReason.EPOCH_STALE -> RemoteInputRejection.ARBITER_EPOCH_STALE
                ArbiterDenialReason.NOT_HOLDER -> RemoteInputRejection.ARBITER_NOT_HOLDER
            }
            return reject(
                rejection,
                "arbiter reason=${decision.reason} controlEpoch=${decision.denial.controlEpoch}",
            )
        }
        // Commit: the watermark only now advances.
        machine.guard.accept(command.seq.toInt())
        val mappedStart = start as GeometryPoint.Mapped
        val audit = LiveInputAudit(
            event = EVENT_INPUT,
            sessionId = sessionId,
            seq = command.seq,
            frameSeq = command.frameSeq,
            kind = command.kind,
            code = null,
            detail = "executed",
            deviceX = mappedStart.dx,
            deviceY = mappedStart.dy,
            epoch = epoch,
            atMs = now,
        )
        auditor(audit)
        RemoteInputDecision.Approved(
            command = command,
            startDx = mappedStart.dx,
            startDy = mappedStart.dy,
            endDx = (end as? GeometryPoint.Mapped)?.dx,
            endDy = (end as? GeometryPoint.Mapped)?.dy,
            epoch = epoch,
        )
    }

    private fun audit(
        nowMs: Long,
        event: String,
        code: String? = null,
        epoch: Long? = leaseEpoch,
        detail: String? = null,
    ) {
        auditor(
            LiveInputAudit(
                event = event,
                sessionId = sessionId,
                seq = 0,
                frameSeq = 0,
                kind = null,
                code = code,
                detail = detail,
                epoch = epoch,
                atMs = nowMs,
            ),
        )
    }

    companion object {
        const val EVENT_INPUT = "live.session.input"
        const val EVENT_INPUT_REJECTED = "live.session.input.rejected"
        const val EVENT_TAKE_CONTROL = "live.session.take-control"
        const val EVENT_TAKE_CONTROL_REJECTED = "live.session.take-control.rejected"
        const val EVENT_RELEASE = "live.session.release"
        const val EVENT_CLOSED = "live.session.closed"

        const val CODE_NOT_REMOTE = "LIVE_INPUT_FORBIDDEN"
        const val CODE_DEVICE_BUSY = "LIVE_DEVICE_BUSY"
        const val CAUSE_RELEASE = "release"
    }
}

/** Epoch-scoped remote ownership minted at take-control (B10 DeviceArbiter). */
data class RemoteLease(val sessionId: String, val epoch: Long)

enum class RemoteInputKind { TAP, SWIPE, TEXT }

/**
 * A remote input as delivered by the server relay (mirror of the L10
 * FleetLiveInputRequest the WS forwards): frame-space coordinates, the seq
 * of the input and the frameSeq of the frame the operator was looking at.
 */
data class RemoteInputCommand(
    val kind: RemoteInputKind,
    val seq: Long,
    val frameSeq: Long,
    val x: Double,
    val y: Double,
    val x2: Double = 0.0,
    val y2: Double = 0.0,
    val text: String? = null,
)

/** Device-side rejection codes (K13 §9 names where they exist). */
enum class RemoteInputRejection(val code: String) {
    NOT_REMOTE("LIVE_INPUT_FORBIDDEN"),
    UNSUPPORTED_KIND("LIVE_INPUT_UNSUPPORTED"),
    SEQ_REGRESSION("INPUT_SEQ_REGRESSION"),
    FRAME_STALE("INPUT_EXPIRED"),
    FRAME_TTL("INPUT_EXPIRED"),
    TASK_ROWS_UNFINISHED("LIVE_DEVICE_BUSY"),
    OUT_OF_GEOMETRY("LIVE_INPUT_OUT_OF_GEOMETRY"),
    SAFE_AREA("LIVE_INPUT_SAFE_AREA"),
    ARBITER_DEVICE_BUSY("LIVE_DEVICE_BUSY"),
    ARBITER_EPOCH_STALE("LIVE_EPOCH_STALE"),
    ARBITER_NOT_HOLDER("LIVE_NOT_HOLDER"),
}

sealed interface RemoteInputDecision {
    /** Device-space coordinates, ready for the gesture sink with the lease epoch. */
    data class Approved(
        val command: RemoteInputCommand,
        val startDx: Int,
        val startDy: Int,
        val endDx: Int?,
        val endDy: Int?,
        val epoch: Long,
    ) : RemoteInputDecision

    data class Rejected(
        val rejection: RemoteInputRejection,
        val audit: LiveInputAudit,
    ) : RemoteInputDecision
}

/**
 * Metadata-only audit record (K13 §6: authorization records and frame
 * content are separate; audits never carry pixels or screenshots).
 */
data class LiveInputAudit(
    val event: String,
    val sessionId: String,
    val seq: Long,
    val frameSeq: Long,
    val kind: RemoteInputKind?,
    val code: String?,
    val detail: String? = null,
    val deviceX: Int? = null,
    val deviceY: Int? = null,
    val epoch: Long? = null,
    val atMs: Long,
)
