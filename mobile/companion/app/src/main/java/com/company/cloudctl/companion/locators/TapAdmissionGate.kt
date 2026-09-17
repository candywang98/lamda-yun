package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.observation.Bounds
import com.company.cloudctl.companion.observation.CanonicalTree
import com.company.cloudctl.companion.observation.Insets
import com.company.cloudctl.companion.observation.ObservedNode

/**
 * B13 (fleet-first-20260916.1) — pre-tap admission gate over a RE-SAMPLED
 * target. Everything a tap decision needs is compared between the capture
 * (match time) and the fresh sample (immediately before the gesture):
 *
 * 1. target package — a different foreground package means the capture is
 *    from another app entirely;
 * 2. sessionEpoch — cross-epoch frames are incomparable (ui-observation/v1
 *    §2/§6, same rule as the fleet-identity AuthorizationEnvelope), so a
 *    changed epoch invalidates the capture instead of being "drift";
 * 3. windowId — a different accessibility window (dialog, split screen)
 *    moved or replaced the target;
 * 4. rotation — the old coordinates are frame-relative and now meaningless;
 * 5. node identity — [identityDigestOf] (the B12 canonical node lines minus
 *    the bounds line) must be byte-equal; geometry is NOT identity here,
 *    it is adjudicated by the drift budget below;
 * 6. bounds drift — Chebyshev edge distance within
 *    [DRIFT_TOLERANCE_PX]. Widening 40→80px is FORBIDDEN as a generic fix:
 *    a large displacement (the 546px banner/list shift shape) is a rejected
 *    capture, never a tolerated one;
 * 7. safe visible area — the fresh rectangle must sit fully on screen and
 *    not intersect the keyboard/gesture occlusions sampled with it.
 *
 * Every rejection carries a readable reason string; the caller fails closed.
 */
object TapAdmissionGate {

    /**
     * Single drift budget for the pre-tap bounds recheck. Must stay equal to
     * [com.company.cloudctl.companion.automation.PublishedCardLocator
     * .BOUNDS_FRESHNESS_TOLERANCE_PX] (40px); parity is pinned by test.
     * Deliberately NOT 80: doubling the tolerance to swallow a real
     * displacement is exactly the wrong-card incident shape.
     */
    const val DRIFT_TOLERANCE_PX = 40

    /** Chebyshev edge distance between two rectangles. */
    fun chebyshevEdgeDistance(a: Bounds, b: Bounds): Int = maxOf(
        kotlin.math.abs(a.left - b.left),
        kotlin.math.abs(a.top - b.top),
        kotlin.math.abs(a.right - b.right),
        kotlin.math.abs(a.bottom - b.bottom),
    )

    /**
     * Adjudicate one tap. [captured] is what the locator proved at match
     * time; [fresh] is the same target re-sampled immediately before the
     * gesture, together with the live [safeArea]. Pure; no I/O, no clock.
     */
    fun decide(captured: CapturedTarget, fresh: FreshSample, safeArea: SafeVisibleArea): TapAdmission {
        if (fresh.packageName != captured.packageName) {
            return TapAdmission.Rejected(
                code = "TARGET_PACKAGE_CHANGED",
                reason = "capture was taken in '${captured.packageName}' but the fresh sample is " +
                    "'${fresh.packageName}'",
            )
        }
        if (fresh.sessionEpoch != captured.sessionEpoch) {
            return TapAdmission.Rejected(
                code = "SESSION_EPOCH_CHANGED",
                reason = "sessionEpoch ${captured.sessionEpoch} -> ${fresh.sessionEpoch}: frames across " +
                    "epochs are incomparable (ui-observation/v1 §2/§6); re-locate from a fresh capture " +
                    "instead of tapping",
            )
        }
        if (fresh.windowId != captured.windowId) {
            return TapAdmission.Rejected(
                code = "WINDOW_CHANGED",
                reason = "accessibility window ${captured.windowId} -> ${fresh.windowId}; the capture's " +
                    "coordinates belong to another window and are void",
            )
        }
        if (fresh.rotation != captured.rotation) {
            return TapAdmission.Rejected(
                code = "ROTATION_CHANGED",
                reason = "rotation ${captured.rotation} -> ${fresh.rotation}; old coordinates are " +
                    "frame-relative and must not be tapped after a rotation",
            )
        }
        val freshDigest = fresh.identityDigest
        val freshBounds = fresh.bounds
        if (freshDigest == null || freshBounds == null) {
            return TapAdmission.Rejected(
                code = "TARGET_NODE_MISSING",
                reason = "target node with identity digest ${captured.identityDigest.take(12)}… is no " +
                    "longer present in the fresh tree",
            )
        }
        if (freshDigest != captured.identityDigest) {
            return TapAdmission.Rejected(
                code = "IDENTITY_DRIFT",
                reason = "node identity changed (digest ${captured.identityDigest.take(12)}… -> " +
                    "${freshDigest.take(12)}…); the node at this place is not the matched target",
            )
        }
        val drift = chebyshevEdgeDistance(captured.bounds, freshBounds)
        if (drift > DRIFT_TOLERANCE_PX) {
            return TapAdmission.Rejected(
                code = "BOUNDS_DRIFTED",
                reason = "bounds drifted ${drift}px (tolerance $DRIFT_TOLERANCE_PX px, deliberately not " +
                    "widened): capture=${captured.bounds.wire} fresh=${freshBounds.wire}; refusing to tap " +
                    "a displaced rectangle",
            )
        }
        safeArea.occluderOf(freshBounds)?.let { occluder ->
            return TapAdmission.Rejected(
                code = "TARGET_OCCLUDED",
                reason = "target ${freshBounds.wire} intersects the ${occluder.kind.wire} occlusion " +
                    "${occluder.region.wire} sampled with the fresh frame; not safely tappable",
            )
        }
        if (!safeArea.screen.contains(freshBounds)) {
            return TapAdmission.Rejected(
                code = "TARGET_OFFSCREEN",
                reason = "target ${freshBounds.wire} is not fully inside the live screen " +
                    "${safeArea.screen.wire}",
            )
        }
        return TapAdmission.Admitted(
            bounds = freshBounds,
            reason = "identity+window+epoch+rotation stable, drift ${drift}px ≤ $DRIFT_TOLERANCE_PX, " +
                "clear of occlusions",
        )
    }

    /**
     * Identity digest over the B12 frozen canonical node lines EXCLUDING the
     * `bounds=` line (composed from [CanonicalTree]'s public primitives —
     * the frozen rendering itself is not duplicated). Geometry is adjudicated
     * separately by the drift budget: the full [CanonicalTree.nodeDigest]
     * mixes bounds into identity, which would make "same node, scrolled 30px"
     * indistinguishable from "different node" and the tolerance meaningless.
     */
    fun identityDigestOf(node: ObservedNode): String =
        CanonicalTree.digest(
            CanonicalTree.nodeLines(node).filterNot { it.startsWith("bounds=") }.joinToString("\n"),
        )
}

/** Everything captured about a tap target at match time. */
data class CapturedTarget(
    val packageName: String,
    val sessionEpoch: Long,
    val windowId: Int,
    val rotation: Int,
    val insets: Insets,
    /** [TapAdmissionGate.identityDigestOf] at capture time (geometry excluded). */
    val identityDigest: String,
    val bounds: Bounds,
) {
    init {
        require(identityDigest.isNotBlank()) { "captured node digest must be a real digest, never blank" }
    }
}

/** The same target re-sampled immediately before the tap. */
data class FreshSample(
    val packageName: String,
    val sessionEpoch: Long,
    val windowId: Int,
    val rotation: Int,
    val insets: Insets,
    val identityDigest: String?,
    val bounds: Bounds?,
) {
    init {
        // The re-found node carries both identity and geometry, or neither.
        require((identityDigest == null) == (bounds == null)) {
            "fresh sample must carry digest and bounds together (digest=$identityDigest bounds=$bounds)"
        }
    }

    companion object {
        /** A fresh frame in which the target node simply is not there. */
        fun absent(
            packageName: String,
            sessionEpoch: Long,
            windowId: Int,
            rotation: Int,
            insets: Insets,
        ) = FreshSample(packageName, sessionEpoch, windowId, rotation, insets, null, null)
    }
}

/** One occluding region sampled with the fresh frame. */
data class OccludedRegion(
    val kind: Kind,
    val region: Bounds,
) {
    enum class Kind(val wire: String) {
        KEYBOARD("keyboard"),
        GESTURE_NAV("gesture_nav"),
        SYSTEM_BAR("system_bar"),
    }
}

/**
 * The safely tappable region of the live frame: the screen minus the
 * occlusions (IME, gesture navigation bar, system bars) sampled with it. A
 * target is admissible only when its whole rectangle sits on screen and
 * intersects no occluder — a half-covered button is a rejected button.
 */
data class SafeVisibleArea(
    val screen: Bounds,
    val occluded: List<OccludedRegion>,
) {
    /** The occluder intersecting [bounds], or null when the rectangle is clear. */
    fun occluderOf(bounds: Bounds): OccludedRegion? =
        occluded.firstOrNull { it.region.intersects(bounds) }
}

/** Intersection test absent from the frozen observation Bounds (kept there read-only). */
private fun Bounds.intersects(other: Bounds): Boolean =
    left < other.right && other.left < right && top < other.bottom && other.top < bottom

/** Verdict of [TapAdmissionGate.decide]. */
sealed interface TapAdmission {
    data class Admitted(val bounds: Bounds, val reason: String) : TapAdmission

    /** Fail-closed verdict; [code] is stable for logs, [reason] is human-readable. */
    data class Rejected(val code: String, val reason: String) : TapAdmission
}
