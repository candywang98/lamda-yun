package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.media.AlbumPick
import com.company.cloudctl.companion.observation.Bounds
import com.company.cloudctl.companion.observation.Insets
import com.company.cloudctl.companion.observation.ObservedNode

/**
 * B15X (fleet-first-20260916.1) — turns a planned [AlbumPick] (B15, read-only
 * import) plus its canonical cell row (from [AlbumPageMapper]) into an
 * APPROVED TAP INTENT. No gesture is ever dispatched here: the admission
 * sequence is capture -> resample -> [TapAdmissionGate.decide] -> intent, and
 * the automation layer owns the only tap handle (its executor wires this at
 * the LocalAutomationExecutor coordinate-tap seam).
 *
 * The resample step re-finds the cell in the fresh canonical tree BY IDENTITY
 * DIGEST (B13, geometry excluded). Duplicate cells with identical identity
 * lines are disambiguated by nearest captured bounds; the 40px drift budget
 * then still adjudicates the geometry, so a nearest-match that actually slid
 * is rejected, never tapped.
 */
object AlbumPickDispatcher {

    /** Frame coordinates shared by capture and fresh sample. */
    data class FrameContext(
        val packageName: String,
        val sessionEpoch: Long,
        val windowId: Int,
        val rotation: Int,
        val insets: Insets,
    )

    /** Everything the executor needs to perform the one admitted tap. */
    data class ApprovedTapIntent(
        val pick: AlbumPick,
        /** Center of the ADMITTED fresh bounds (floor-rounded halves). */
        val tapX: Int,
        val tapY: Int,
        val admittedBounds: Bounds,
        /** [TapAdmissionGate.identityDigestOf] of the re-found cell row. */
        val identityDigest: String,
        val admissionReason: String,
    )

    /** Fail-closed outcome; no coordinates are produced. */
    data class Refused(
        val pick: AlbumPick,
        val code: String,
        val reason: String,
    )

    /**
     * Capture-time target of a cell row: what the gate compares the fresh
     * sample against. Call once when the page observation backing the plan was
     * taken; the pick must still be admitted against a frame captured in the
     * same conditions.
     */
    fun capture(frame: FrameContext, cellRow: ObservedNode): CapturedTarget = CapturedTarget(
        packageName = frame.packageName,
        sessionEpoch = frame.sessionEpoch,
        windowId = frame.windowId,
        rotation = frame.rotation,
        insets = frame.insets,
        identityDigest = TapAdmissionGate.identityDigestOf(cellRow),
        bounds = cellRow.bounds,
    )

    /**
     * Re-find the cell row in a fresh canonical tree by identity digest;
     * nearest captured bounds breaks digest ties (duplicate images have
     * byte-equal identity lines — geometry is the only remaining signal, and
     * the drift budget still judges it afterwards). Null when absent.
     */
    fun resample(freshNodes: List<ObservedNode>, cellRow: ObservedNode): ObservedNode? {
        val wanted = TapAdmissionGate.identityDigestOf(cellRow)
        return freshNodes
            .filter { TapAdmissionGate.identityDigestOf(it) == wanted }
            .filter { it.bounds.width > 0 && it.bounds.height > 0 }
            .minWithOrNull(
                compareBy(
                    { TapAdmissionGate.chebyshevEdgeDistance(cellRow.bounds, it.bounds) },
                    { it.depth },
                    { it.index },
                ),
            )
    }

    /**
     * Fallback for the "same place, different node" shape: the nearest
     * non-degenerate row within [TapAdmissionGate.DRIFT_TOLERANCE_PX] of the
     * captured rectangle when no digest match exists anywhere. Its (different)
     * digest is then fed to the gate, which rejects with IDENTITY_DRIFT — a
     * sharper diagnosis than "missing", and exactly the wrong-image swap the
     * fleet must never tap.
     */
    private fun resampleNear(freshNodes: List<ObservedNode>, cellRow: ObservedNode): ObservedNode? =
        freshNodes
            .filter { it.bounds.width > 0 && it.bounds.height > 0 }
            .mapNotNull { node ->
                val distance = TapAdmissionGate.chebyshevEdgeDistance(cellRow.bounds, node.bounds)
                if (distance <= TapAdmissionGate.DRIFT_TOLERANCE_PX) node to distance else null
            }
            .minWithOrNull(compareBy({ (_, distance) -> distance }, { (node, _) -> node.depth }, { (node, _) -> node.index }))
            ?.first

    /**
     * The admission call sequence for one pick: capture the cell row against
     * the observation frame, re-find it in the fresh tree, run the B13 gate,
     * and only on Admitted emit the tap intent (coordinates = center of the
     * FRESH bounds, never the stale capture).
     *
     * @param cellRow the canonical tap row [AlbumPageMapper.AlbumCellNode.node]
     *   of the picked cell.
     * @param captureFrame frame the page observation was taken in.
     * @param freshFrame frame the pre-tap sample was taken in; any drift
     *   between the frames (package/epoch/window/rotation) is itself a gate
     *   rejection, never silently forgiven.
     */
    fun dispatch(
        pick: AlbumPick,
        cellRow: ObservedNode,
        captureFrame: FrameContext,
        freshNodes: List<ObservedNode>,
        freshFrame: FrameContext,
        safeArea: SafeVisibleArea,
    ): DispatchOutcome {
        if (pick.cellIndex < 0) {
            return DispatchOutcome.Refused(
                Refused(pick, "INVALID_PICK", "album pick carries negative cellIndex ${pick.cellIndex}"),
            )
        }
        val captured = capture(captureFrame, cellRow)
        val refound = resample(freshNodes, cellRow) ?: resampleNear(freshNodes, cellRow)
        val fresh = if (refound == null) {
            FreshSample.absent(
                packageName = freshFrame.packageName,
                sessionEpoch = freshFrame.sessionEpoch,
                windowId = freshFrame.windowId,
                rotation = freshFrame.rotation,
                insets = freshFrame.insets,
            )
        } else {
            FreshSample(
                packageName = freshFrame.packageName,
                sessionEpoch = freshFrame.sessionEpoch,
                windowId = freshFrame.windowId,
                rotation = freshFrame.rotation,
                insets = freshFrame.insets,
                identityDigest = TapAdmissionGate.identityDigestOf(refound),
                bounds = refound.bounds,
            )
        }
        return when (val admission = TapAdmissionGate.decide(captured, fresh, safeArea)) {
            is TapAdmission.Admitted -> DispatchOutcome.Approved(
                ApprovedTapIntent(
                    pick = pick,
                    tapX = (admission.bounds.left + admission.bounds.right) / 2,
                    tapY = (admission.bounds.top + admission.bounds.bottom) / 2,
                    admittedBounds = admission.bounds,
                    identityDigest = captured.identityDigest,
                    admissionReason = admission.reason,
                ),
            )
            is TapAdmission.Rejected -> DispatchOutcome.Refused(Refused(pick, admission.code, admission.reason))
        }
    }
}

/** Verdict of [AlbumPickDispatcher.dispatch]. */
sealed interface DispatchOutcome {
    data class Approved(val intent: AlbumPickDispatcher.ApprovedTapIntent) : DispatchOutcome

    data class Refused(val refusal: AlbumPickDispatcher.Refused) : DispatchOutcome
}
