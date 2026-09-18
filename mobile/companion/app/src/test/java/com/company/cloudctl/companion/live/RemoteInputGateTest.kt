package com.company.cloudctl.companion.live

import com.company.cloudctl.companion.runtime.DeviceArbiter
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * L11 requirement 3/4 and acceptance 2/3/4: every remote gesture is gated by
 * the B10 single writer + the current epoch, frame freshness, the frame
 * geometry inverse, and the unfinished-task-rows probe — with a metadata-only
 * audit event for every rejection (BLK-008 device side; zero-journal remote
 * paths are gone).
 */
class RemoteInputGateTest {

    /** Injectable monotonic clock with an inspectable/advancable now. */
    private class MutableClock(var now: Long = 0L) {
        operator fun invoke(): Long = now
    }

    private class Harness(
        var unfinishedRows: Boolean = false,
        val nowMs: Long = 0L,
    ) {
        val clock = MutableClock(nowMs)
        val machine = LiveClientStateMachine()
        val ledger = FrameLedger()
        val arbiter = DeviceArbiter()
        val audits = mutableListOf<LiveInputAudit>()
        val gate = RemoteInputGate(
            sessionId = "live-1",
            machine = machine,
            ledger = ledger,
            arbiter = arbiter,
            unfinishedTaskRows = { unfinishedRows },
            auditor = { audits.add(it) },
            clock = { clock.now },
        )

        fun open() {
            machine.onOpened()
        }

        fun takeControl(): RemoteLease? = gate.beginRemote()

        /** Records a frame and returns its frameSeq; advances the clock a bit. */
        fun emitFrame(geometry: FrameGeometry, advanceMs: Long = 20): Long {
            val seq = ledger.recordNext(geometry, clock.now).frameSeq
            clock.now += advanceMs
            return seq
        }

        fun tap(fx: Double, fy: Double, seq: Long, frameSeq: Long): RemoteInputDecision =
            gate.evaluate(
                RemoteInputCommand(kind = RemoteInputKind.TAP, seq = seq, frameSeq = frameSeq, x = fx, y = fy),
            )

        fun rejectedCodes(): List<String> = audits.filter { it.code != null }.map { it.code!! }
    }

    private val portrait = FrameGeometry(405, 720, 1080, 1920, 0)
    private val portraitWithStatusBar = FrameGeometry(
        405, 720, 1080, 1920, 0,
        safeArea = SafeAreaRect(left = 0, top = 0, right = 1080, bottom = 96),
    )
    private val rotatedLandscape = FrameGeometry(720, 405, 1920, 1080, 90)

    // ------------------------------------------------------------------
    // Acceptance 4: unfinished rows / non-REMOTE / stale epoch all reject
    // WITH an audit event.
    // ------------------------------------------------------------------

    @Test
    fun nonRemoteStateRejectsWithAudit() {
        val h = Harness()
        h.open()
        val frame = h.emitFrame(portrait)
        val decision = h.tap(202.5, 360.0, seq = 1, frameSeq = frame)
        val rejected = assertIs<RemoteInputDecision.Rejected>(decision)
        assertEquals(RemoteInputRejection.NOT_REMOTE, rejected.rejection)
        assertEquals("LIVE_INPUT_FORBIDDEN", rejected.rejection.code)
        // Audited with the K13 event vocabulary.
        assertTrue(h.audits.any { it.event == "live.session.input.rejected" && it.code == "LIVE_INPUT_FORBIDDEN" })
    }

    @Test
    fun unfinishedTaskRowsRejectRemoteGesturesWithAudit() {
        val h = Harness(unfinishedRows = true)
        h.open()
        assertNotNull(h.takeControl())
        val frame = h.emitFrame(portrait)
        val decision = h.tap(202.5, 360.0, seq = 1, frameSeq = frame)
        val rejected = assertIs<RemoteInputDecision.Rejected>(decision)
        assertEquals(RemoteInputRejection.TASK_ROWS_UNFINISHED, rejected.rejection)
        assertEquals("LIVE_DEVICE_BUSY", rejected.rejection.code)
        assertTrue(h.audits.any { it.code == "LIVE_DEVICE_BUSY" })
    }

    @Test
    fun supersededEpochRejectsLateGesturesWithAudit() {
        val h = Harness()
        h.open()
        val lease = assertNotNull(h.takeControl())
        val frame = h.emitFrame(portrait)

        // remote->auto handover races the transport: the server has not sent
        // the state change yet, but a task session already superseded the
        // remote epoch. The arbiter must fence the straggler.
        h.arbiter.beginTaskSession("task-9")
        val decision = h.tap(202.5, 360.0, seq = 1, frameSeq = frame)
        val rejected = assertIs<RemoteInputDecision.Rejected>(decision)
        assertEquals(RemoteInputRejection.ARBITER_EPOCH_STALE, rejected.rejection)
        assertEquals("LIVE_EPOCH_STALE", rejected.rejection.code)
        assertTrue(h.audits.any { it.code == "LIVE_EPOCH_STALE" && it.epoch == lease.epoch })
        // The arbiter journaled the denial too (bounded rejection record).
        assertTrue(h.arbiter.denials().any { it.writer == com.company.cloudctl.companion.runtime.UiWriter.REMOTE_LIVE })
    }

    // ------------------------------------------------------------------
    // Acceptance 2: stale-frame clicks and system-gesture-zone coordinates
    // are rejected with reason codes.
    // ------------------------------------------------------------------

    @Test
    fun clickOnStaleFrameIsRejected() {
        val h = Harness()
        h.open()
        assertNotNull(h.takeControl())
        val oldFrame = h.emitFrame(portrait)
        // 11 newer frames: latest - oldFrame = 11 > threshold 10.
        repeat(11) { h.emitFrame(portrait) }
        val decision = h.tap(202.5, 360.0, seq = 1, frameSeq = oldFrame)
        assertEquals(RemoteInputRejection.FRAME_STALE, assertIs<RemoteInputDecision.Rejected>(decision).rejection)
        assertEquals("INPUT_EXPIRED", assertIs<RemoteInputDecision.Rejected>(decision).rejection.code)
        assertTrue(h.audits.any { it.code == "INPUT_EXPIRED" })
    }

    @Test
    fun clickOnTtlExpiredFrameIsRejected() {
        val h = Harness()
        h.open()
        assertNotNull(h.takeControl())
        val frame = h.emitFrame(portrait)
        h.clock.now += 2_500 // > ttlExpiryMs 2000
        val decision = h.tap(202.5, 360.0, seq = 1, frameSeq = frame)
        assertEquals(RemoteInputRejection.FRAME_TTL, assertIs<RemoteInputDecision.Rejected>(decision).rejection)
        assertEquals("INPUT_EXPIRED", assertIs<RemoteInputDecision.Rejected>(decision).rejection.code)
    }

    @Test
    fun systemGestureZoneCoordinatesAreRejected() {
        val h = Harness()
        h.open()
        assertNotNull(h.takeControl())
        val frame = h.emitFrame(portraitWithStatusBar)
        // fy=20 -> device y≈53: inside the status-bar exclusion strip.
        val decision = h.tap(202.5, 20.0, seq = 1, frameSeq = frame)
        val rejected = assertIs<RemoteInputDecision.Rejected>(decision)
        assertEquals(RemoteInputRejection.SAFE_AREA, rejected.rejection)
        assertEquals("LIVE_INPUT_SAFE_AREA", rejected.rejection.code)
        // Off-frame coordinates reject as out-of-geometry.
        val offFrame = h.tap(9999.0, -5.0, seq = 2, frameSeq = frame)
        assertEquals(
            RemoteInputRejection.OUT_OF_GEOMETRY,
            assertIs<RemoteInputDecision.Rejected>(offFrame).rejection,
        )
    }

    @Test
    fun seqRegressionRejectedAndWatermarkOnlyAdvancesOnExecution() {
        val h = Harness()
        h.open()
        assertNotNull(h.takeControl())
        val frame = h.emitFrame(portrait)
        val first = assertIs<RemoteInputDecision.Approved>(h.tap(202.5, 360.0, seq = 7, frameSeq = frame))
        assertEquals(540, first.startDx)
        assertEquals(960, first.startDy)

        // Replayed seq 7 and regressed seq 3 both reject...
        assertEquals(
            RemoteInputRejection.SEQ_REGRESSION,
            assertIs<RemoteInputDecision.Rejected>(h.tap(100.0, 100.0, seq = 7, frameSeq = frame)).rejection,
        )
        // ...and a REJECTED later input must not have advanced the watermark
        // (server semantics: watermark moves at commit only).
        h.unfinishedRows = true
        assertEquals(
            RemoteInputRejection.TASK_ROWS_UNFINISHED,
            assertIs<RemoteInputDecision.Rejected>(h.tap(100.0, 100.0, seq = 8, frameSeq = frame)).rejection,
        )
        h.unfinishedRows = false
        val next = assertIs<RemoteInputDecision.Approved>(h.tap(100.0, 100.0, seq = 8, frameSeq = frame))
        assertEquals(8, next.command.seq)
        // seq 8 executed exactly once: a repeat still regresses.
        assertEquals(
            RemoteInputRejection.SEQ_REGRESSION,
            assertIs<RemoteInputDecision.Rejected>(h.tap(100.0, 100.0, seq = 8, frameSeq = frame)).rejection,
        )
    }

    // ------------------------------------------------------------------
    // Acceptance 3: release cleans up the arbiter holder/epoch; paused rows
    // are never auto-resumed by the live side.
    // ------------------------------------------------------------------

    @Test
    fun releaseReturnsArbiterLeaseAndLateInputsReject() {
        val h = Harness()
        h.open()
        val lease = assertNotNull(h.takeControl())
        assertEquals(lease.epoch, h.arbiter.activeRemoteSessionEpoch())
        val frame = h.emitFrame(portrait)
        assertIs<RemoteInputDecision.Approved>(h.tap(202.5, 360.0, seq = 1, frameSeq = frame))

        assertTrue(h.gate.endRemote())
        // Holder cleaned: no remote session/epoch left with the arbiter.
        assertNull(h.arbiter.activeRemoteSessionEpoch())
        // Late input from the released lease: state machine is VIEWING.
        assertEquals(
            RemoteInputRejection.NOT_REMOTE,
            assertIs<RemoteInputDecision.Rejected>(h.tap(202.5, 360.0, seq = 2, frameSeq = frame)).rejection,
        )
        // Even if the state were still REMOTE (transport race), the ended
        // lease no longer holds the device: re-entering REMOTE on the state
        // machine without a new arbiter lease still fences the input.
        h.machine.onTakeControl()
        assertEquals(
            RemoteInputRejection.ARBITER_NOT_HOLDER,
            assertIs<RemoteInputDecision.Rejected>(h.tap(202.5, 360.0, seq = 3, frameSeq = frame)).rejection,
        )
        assertTrue(h.audits.any { it.event == "live.session.release" })
    }

    @Test
    fun pausedRowsAreNotAutoResumedByHandover() {
        // A paused task row exists; remote cannot gesture over it; release
        // leaves it exactly as it was — recovery follows the existing
        // pause/resume semantics elsewhere (no blind REQUEUE_AUTO from the
        // live side).
        var rows = true
        val clock = MutableClock(0L)
        val machine = LiveClientStateMachine()
        val ledger = FrameLedger()
        val arbiter = DeviceArbiter()
        val audits = mutableListOf<LiveInputAudit>()
        val gate = RemoteInputGate("live-1", machine, ledger, arbiter, { rows }, { audits.add(it) }, { clock.now })
        machine.onOpened()
        assertNotNull(gate.beginRemote())
        val frame = ledger.recordNext(portrait, clock()).frameSeq
        clock.now += 20
        assertEquals(
            RemoteInputRejection.TASK_ROWS_UNFINISHED,
            assertIs<RemoteInputDecision.Rejected>(
                gate.evaluate(RemoteInputCommand(RemoteInputKind.TAP, 1, frame, 202.5, 360.0)),
            ).rejection,
        )
        assertTrue(gate.endRemote())
        // The probe is strictly read-only: the row is still unfinished and
        // nothing in the gate mutates task state — no resume API even exists
        // on the gate surface.
        assertTrue(rows)
        assertNull(arbiter.activeRemoteSessionEpoch())
    }

    // ------------------------------------------------------------------
    // Requirement 4: VIEWING coexists with automation; remote never runs
    // concurrently with a RUNNING task session.
    // ------------------------------------------------------------------

    @Test
    fun viewingStreamsFramesWhileTaskSessionRuns() {
        val h = Harness()
        h.open()
        // A task session holds the device; passive VIEWING keeps streaming:
        // frames are recorded, nothing is arbitrated, no denials.
        h.arbiter.beginTaskSession("task-1")
        assertTrue(h.arbiter.hasActiveTaskSession())
        repeat(3) { h.emitFrame(portrait) }
        assertEquals(3, h.ledger.latestFrameSeq)
        assertTrue(h.arbiter.denials().isEmpty())
        // And inputs are, of course, still refused (not REMOTE).
        assertEquals(
            RemoteInputRejection.NOT_REMOTE,
            assertIs<RemoteInputDecision.Rejected>(h.tap(10.0, 10.0, seq = 1, frameSeq = 3)).rejection,
        )
    }

    @Test
    fun takeControlRefusedWhileTaskSessionRuns() {
        val h = Harness()
        h.open()
        h.arbiter.beginTaskSession("task-2")
        assertNull(h.takeControl()) // device stays VIEWING
        assertEquals(LiveClientState.VIEWING, h.machine.state)
        assertNull(h.arbiter.activeRemoteSessionEpoch())
        assertTrue(h.audits.any { it.event == "live.session.take-control.rejected" && it.code == "LIVE_DEVICE_BUSY" })
        // After the task completes, take-control succeeds.
        val session = h.arbiter.activeTaskSession()!!
        assertTrue(h.arbiter.endTaskSession(session.fencingToken, com.company.cloudctl.companion.runtime.ReleaseBoundary.COMPLETED))
        assertNotNull(h.takeControl())
        assertEquals(LiveClientState.REMOTE, h.machine.state)
    }

    @Test
    fun terminateClosesEverythingOnProjectionRevoked() {
        val h = Harness()
        h.open()
        assertNotNull(h.takeControl())
        val frame = h.emitFrame(portrait)
        assertIs<RemoteInputDecision.Approved>(h.tap(202.5, 360.0, seq = 1, frameSeq = frame))
        assertTrue(h.gate.terminate("PROJECTION_REVOKED"))
        assertEquals(LiveClientState.CLOSED, h.machine.state)
        assertNull(h.arbiter.activeRemoteSessionEpoch())
        assertTrue(h.audits.any { it.event == "live.session.closed" && it.detail == "PROJECTION_REVOKED" })
        assertEquals(
            RemoteInputRejection.NOT_REMOTE,
            assertIs<RemoteInputDecision.Rejected>(h.tap(202.5, 360.0, seq = 2, frameSeq = frame)).rejection,
        )
    }

    // ------------------------------------------------------------------
    // Acceptance 5 through the full gate: rotation-bound geometry with the
    // K13 90-degree table (device-side end-to-end transform).
    // ------------------------------------------------------------------

    @Test
    fun rotatedFrameInputUsesItsOwnGeometry() {
        val h = Harness()
        h.open()
        assertNotNull(h.takeControl())
        // Pre-rotation frame, then the display turned: the input aimed at
        // the OLD frame must use the OLD geometry (and still be fresh).
        val oldFrame = h.emitFrame(portrait)
        val newFrame = h.emitFrame(rotatedLandscape)
        val approvedOld = assertIs<RemoteInputDecision.Approved>(h.tap(202.5, 360.0, seq = 1, frameSeq = oldFrame))
        assertEquals(540, approvedOld.startDx)
        assertEquals(960, approvedOld.startDy)
        // The NEW frame transforms with the 90-degree table: frame center
        // (360, 202.5) of 720x405 over device 1920x1080 -> (960, 539).
        val approvedNew = assertIs<RemoteInputDecision.Approved>(h.tap(360.0, 202.5, seq = 2, frameSeq = newFrame))
        assertEquals(960, approvedNew.startDx)
        assertEquals(539, approvedNew.startDy)
    }

    @Test
    fun swipeBothEndpointsTransformedAndFenced() {
        val h = Harness()
        h.open()
        val lease = assertNotNull(h.takeControl())
        val frame = h.emitFrame(rotatedLandscape)
        val decision = h.gate.evaluate(
            RemoteInputCommand(
                kind = RemoteInputKind.SWIPE,
                seq = 1,
                frameSeq = frame,
                x = 360.0, y = 202.5, // -> device (960, 539)
                x2 = 0.0, y2 = 0.0,   // -> device (0, 1079)
            ),
        )
        val approved = assertIs<RemoteInputDecision.Approved>(decision)
        assertEquals(960, approved.startDx)
        assertEquals(539, approved.startDy)
        assertEquals(0, approved.endDx)
        assertEquals(1079, approved.endDy)
        assertEquals(lease.epoch, approved.epoch)
        // An endpoint off the plane rejects the whole gesture.
        val bad = h.gate.evaluate(
            RemoteInputCommand(RemoteInputKind.SWIPE, seq = 2, frameSeq = frame, x = 360.0, y = 202.5, x2 = 9999.0, y2 = 0.0),
        )
        assertEquals(RemoteInputRejection.OUT_OF_GEOMETRY, assertIs<RemoteInputDecision.Rejected>(bad).rejection)
    }

    @Test
    fun executedInputEmitsMetadataOnlyAuditEvent() {
        val h = Harness()
        h.open()
        val lease = assertNotNull(h.takeControl())
        val frame = h.emitFrame(portrait)
        assertIs<RemoteInputDecision.Approved>(h.tap(202.5, 360.0, seq = 1, frameSeq = frame))
        val executed = h.audits.single { it.event == "live.session.input" }
        assertEquals("live-1", executed.sessionId)
        assertEquals(1, executed.seq)
        assertEquals(frame, executed.frameSeq)
        assertEquals(RemoteInputKind.TAP, executed.kind)
        assertNull(executed.code)
        assertEquals(540, executed.deviceX)
        assertEquals(960, executed.deviceY)
        assertEquals(lease.epoch, executed.epoch)
        // K13 §6: audit carries metadata only — the type carries no bitmap,
        // JPEG bytes, or screenshot field by construction.
    }

    @Test
    fun bindRefusesRebindingToADifferentSession() {
        val gate = RemoteInputGate(
            sessionId = "",
            machine = LiveClientStateMachine(),
            ledger = FrameLedger(),
            arbiter = DeviceArbiter(),
            unfinishedTaskRows = { false },
            auditor = {},
            clock = { 0L },
        )
        gate.bind("live-a")
        assertFailsWith<IllegalStateException> { gate.bind("live-b") }
        gate.bind("live-a") // idempotent same-session rebind is fine
    }
}
