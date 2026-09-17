package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.automation.PublishedCardLocator
import com.company.cloudctl.companion.observation.Bounds
import com.company.cloudctl.companion.observation.CanonicalTree
import com.company.cloudctl.companion.observation.Insets
import com.company.cloudctl.companion.observation.ObservedNode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * B13 — pre-tap admission gate over the re-sampled target (identity /
 * window / epoch / rotation / safe visible area). The frozen acceptance
 * shapes: a 546px displacement, a window or rotation change, a keyboard or
 * gesture-bar occlusion — all REJECTED with readable reasons; the drift
 * tolerance stays 40px and is never widened to 80.
 */
class TapAdmissionGateTest {
    private val screen = Bounds(0, 0, 1080, 2400)
    private val insets = Insets(0, 132, 0, 84)

    /** The action-button node as frozen at capture time (six identity fields -> digest). */
    private fun buttonNode(text: String = "编辑", bounds: Bounds = Bounds(66, 1380, 226, 1470)) = ObservedNode(
        depth = 4,
        index = 12,
        className = "android.view.View",
        resourceId = "com.taobao.idlefish:id/card_action",
        text = text,
        contentDesc = "",
        bounds = bounds,
        clickable = true,
    )

    private fun capturedOf(node: ObservedNode) = CapturedTarget(
        packageName = "com.taobao.idlefish",
        sessionEpoch = 7L,
        windowId = 12,
        rotation = 0,
        insets = insets,
        identityDigest = TapAdmissionGate.identityDigestOf(node),
        bounds = node.bounds,
    )

    private fun freshOf(
        node: ObservedNode?,
        epoch: Long = 7L,
        windowId: Int = 12,
        rotation: Int = 0,
        pkg: String = "com.taobao.idlefish",
    ) = FreshSample(
        packageName = pkg,
        sessionEpoch = epoch,
        windowId = windowId,
        rotation = rotation,
        insets = insets,
        identityDigest = node?.let { TapAdmissionGate.identityDigestOf(it) },
        bounds = node?.bounds,
    )

    private fun safeArea(vararg occluded: OccludedRegion) = SafeVisibleArea(screen, occluded.toList())

    private fun rejected(admission: TapAdmission): TapAdmission.Rejected =
        admission as TapAdmission.Rejected

    @Test
    fun identicalResampleIsAdmitted() {
        val node = buttonNode()
        val decision = TapAdmissionGate.decide(capturedOf(node), freshOf(node), safeArea())
        val admitted = decision as TapAdmission.Admitted
        assertEquals(node.bounds, admitted.bounds)
        assertTrue("drift 0px" in admitted.reason || "drift 0" in admitted.reason)
    }

    @Test
    fun smallDriftWithinToleranceStillAdmits() {
        val capturedNode = buttonNode(bounds = Bounds(66, 1380, 226, 1470))
        // 30px vertical shift: within the 40px Chebyshev budget.
        val freshNode = buttonNode(bounds = Bounds(66, 1410, 226, 1500))
        val decision = TapAdmissionGate.decide(
            capturedOf(capturedNode),
            freshOf(freshNode),
            safeArea(),
        )
        assertTrue(decision is TapAdmission.Admitted)
        assertEquals(freshNode.bounds, (decision as TapAdmission.Admitted).bounds)
    }

    @Test
    fun displacementOf546pxIsRejectedAndTheToleranceIsNotWidenedTo80() {
        // The frozen incident shape: the list shifts under a banner and the
        // capture's rectangle is 546px stale. Rejected with the measured px;
        // the tolerance stays 40 — doubling it is not a fix.
        val capturedNode = buttonNode(bounds = Bounds(66, 1380, 226, 1470))
        val freshNode = buttonNode(bounds = Bounds(66, 1926, 226, 2016))
        assertEquals(546, TapAdmissionGate.chebyshevEdgeDistance(capturedNode.bounds, freshNode.bounds))
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(capturedNode), freshOf(freshNode), safeArea()))
        assertEquals("BOUNDS_DRIFTED", verdict.code)
        assertTrue("546px" in verdict.reason, "reason must state the measured displacement: ${verdict.reason}")
        assertTrue("40" in verdict.reason)
        assertEquals(40, TapAdmissionGate.DRIFT_TOLERANCE_PX)
        // 80px would have admitted a 79px drift — the generic-fix trap.
        assertTrue(TapAdmissionGate.chebyshevEdgeDistance(capturedNode.bounds, freshNode.bounds) > 80)
    }

    @Test
    fun driftToleranceStaysPinnedToTheCardArbiterConstant() {
        // One drift budget across the maintenance path and the gate; parity
        // pinned so neither copy can silently become 80.
        assertEquals(
            PublishedCardLocator.BOUNDS_FRESHNESS_TOLERANCE_PX,
            TapAdmissionGate.DRIFT_TOLERANCE_PX,
        )
    }

    @Test
    fun windowChangeVoidsTheOldCoordinates() {
        val node = buttonNode()
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), freshOf(node, windowId = 13), safeArea()))
        assertEquals("WINDOW_CHANGED", verdict.code)
        assertTrue("window 12 -> 13" in verdict.reason)
    }

    @Test
    fun rotationChangeVoidsTheOldCoordinates() {
        val node = buttonNode()
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), freshOf(node, rotation = 1), safeArea()))
        assertEquals("ROTATION_CHANGED", verdict.code)
        assertTrue("rotation 0 -> 1" in verdict.reason)
    }

    @Test
    fun sessionEpochChangeRefusesTheComparison() {
        val node = buttonNode()
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), freshOf(node, epoch = 8L), safeArea()))
        assertEquals("SESSION_EPOCH_CHANGED", verdict.code)
        assertTrue("epoch" in verdict.reason.lowercase() && "incomparable" in verdict.reason)
    }

    @Test
    fun identityDriftIsRejectedEvenAtIdenticalBounds() {
        val capturedNode = buttonNode(text = "编辑")
        val differentNode = buttonNode(text = "删除")
        val verdict = rejected(
            TapAdmissionGate.decide(capturedOf(capturedNode), freshOf(differentNode), safeArea()),
        )
        assertEquals("IDENTITY_DRIFT", verdict.code)
    }

    @Test
    fun missingNodeInTheFreshTreeIsRejected() {
        val node = buttonNode()
        val fresh = FreshSample.absent(
            packageName = "com.taobao.idlefish",
            sessionEpoch = 7L,
            windowId = 12,
            rotation = 0,
            insets = insets,
        )
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), fresh, safeArea()))
        assertEquals("TARGET_NODE_MISSING", verdict.code)
    }

    @Test
    fun packageChangeIsRejected() {
        val node = buttonNode()
        val verdict = rejected(
            TapAdmissionGate.decide(capturedOf(node), freshOf(node, pkg = "com.other.app"), safeArea()),
        )
        assertEquals("TARGET_PACKAGE_CHANGED", verdict.code)
    }

    @Test
    fun keyboardOccludedTargetIsNeverTapped() {
        val node = buttonNode(bounds = Bounds(66, 1900, 226, 2100))
        val ime = OccludedRegion(OccludedRegion.Kind.KEYBOARD, Bounds(0, 2000, 1080, 2400))
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), freshOf(node), safeArea(ime)))
        assertEquals("TARGET_OCCLUDED", verdict.code)
        assertTrue("keyboard" in verdict.reason)
    }

    @Test
    fun gestureBarOccludedTargetIsNeverTapped() {
        // Device-verified trap: a tap 26px above the screen edge never reaches
        // the app — the bottom gesture zone is an occluder, not a tap area.
        val node = buttonNode(bounds = Bounds(66, 2260, 226, 2340))
        val gesture = OccludedRegion(OccludedRegion.Kind.GESTURE_NAV, Bounds(0, 2280, 1080, 2400))
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), freshOf(node), safeArea(gesture)))
        assertEquals("TARGET_OCCLUDED", verdict.code)
        assertTrue("gesture_nav" in verdict.reason)
    }

    @Test
    fun partiallyOffscreenTargetIsRejected() {
        val node = buttonNode(bounds = Bounds(66, 2300, 226, 2460))
        val verdict = rejected(TapAdmissionGate.decide(capturedOf(node), freshOf(node), safeArea()))
        assertEquals("TARGET_OFFSCREEN", verdict.code)
    }

    @Test
    fun freshSampleCarriesDigestAndBoundsTogether() {
        val failure = kotlin.test.assertFailsWith<IllegalArgumentException> {
            FreshSample("p", 1L, 1, 0, insets, "digest", null)
        }
        assertTrue("together" in failure.message.orEmpty())
    }

    @Test
    fun capturedDigestMayNeverBeBlank() {
        val failure = kotlin.test.assertFailsWith<IllegalArgumentException> {
            CapturedTarget("p", 1L, 1, 0, insets, " ", Bounds(0, 0, 10, 10))
        }
        assertTrue("never blank" in failure.message.orEmpty())
    }

    @Test
    fun identityDigestExcludesGeometryButKeepsTheFrozenFieldSemantics() {
        // Same node moved: identity digest STABLE (drift budget judges the
        // move), full B12 nodeDigest CHANGES (bounds is one of its six
        // fields). This separation is what makes the 40px budget meaningful.
        val still = buttonNode(bounds = Bounds(66, 1380, 226, 1470))
        val moved = buttonNode(bounds = Bounds(66, 1410, 226, 1500))
        assertEquals(TapAdmissionGate.identityDigestOf(still), TapAdmissionGate.identityDigestOf(moved))
        assertNotEquals(CanonicalTree.nodeDigest(still), CanonicalTree.nodeDigest(moved))
        // A real identity change (text) still changes the identity digest.
        val relabelled = buttonNode(text = "删除")
        assertNotEquals(TapAdmissionGate.identityDigestOf(still), TapAdmissionGate.identityDigestOf(relabelled))
    }
}
