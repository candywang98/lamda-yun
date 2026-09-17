package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.media.AlbumPick
import com.company.cloudctl.companion.media.AlbumSelection
import com.company.cloudctl.companion.media.AlbumSelectionResult
import com.company.cloudctl.companion.media.AlbumShutterPolicy
import com.company.cloudctl.companion.media.MatchBasis
import com.company.cloudctl.companion.media.SelectionBudget
import com.company.cloudctl.companion.media.StagedMediaAsset
import com.company.cloudctl.companion.observation.Bounds
import com.company.cloudctl.companion.observation.Insets
import com.company.cloudctl.companion.observation.ObservedNode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B15X — gated pick dispatch. The mapper's canonical cell row plus the B15
 * pick become an APPROVED TAP INTENT only through the B13 TapAdmissionGate;
 * every drift/occlusion/identity/absence shape refuses with the gate's stable
 * code and never produces coordinates.
 */
class AlbumPickDispatcherTest {

    private val screen = Bounds(0, 0, 1080, 2400)
    private val insets = Insets(0, 132, 0, 84)

    private fun frame(pkg: String = "com.android.gallery3d") =
        AlbumPickDispatcher.FrameContext(
            packageName = pkg,
            sessionEpoch = 41L,
            windowId = 7,
            rotation = 0,
            insets = insets,
        )

    /** The clickable cell row as the mapper freezes it (slot 1 of row 0). */
    private fun cellRow(
        desc: String = "asset-2.jpg",
        bounds: Bounds = Bounds(360, 400, 710, 750),
    ) = ObservedNode(
        depth = 2,
        index = 1,
        className = "android.view.View",
        resourceId = "com.android.gallery3d:id/grid_item",
        text = "",
        contentDesc = desc,
        bounds = bounds,
        clickable = true,
    )

    private fun pick(cellIndex: Int = 1) = AlbumPick(
        assetId = "asset-2",
        orderIndex = 0,
        cellIndex = cellIndex,
        mediaStoreId = null,
        matchedDisplayName = "asset-2.jpg",
        basis = MatchBasis.NAME_ONLY,
    )

    private fun safeArea(vararg occluded: OccludedRegion) = SafeVisibleArea(screen, occluded.toList())

    // --- admission sequence (gate linkage) -----------------------------------

    @Test
    fun identicalResampleIsApprovedWithFreshCenterCoordinates() {
        val row = cellRow()
        val outcome = AlbumPickDispatcher.dispatch(
            pick = pick(),
            cellRow = row,
            captureFrame = frame(),
            freshNodes = listOf(cellRow()),
            freshFrame = frame(),
            safeArea = safeArea(),
        )
        val approved = assertIs<DispatchOutcome.Approved>(outcome).intent
        // Center of the admitted bounds, floor-rounded halves.
        assertEquals(535, approved.tapX)
        assertEquals(575, approved.tapY)
        assertEquals(row.bounds, approved.admittedBounds)
        assertEquals(TapAdmissionGate.identityDigestOf(row), approved.identityDigest)
        assertEquals("asset-2", approved.pick.assetId)
    }

    @Test
    fun bannerDisplacementOf546pxIsRefusedAsBoundsDrift() {
        // Gate linkage 1: the frozen incident shape. The re-found row is the
        // same identity, but 546px lower — refuse, no coordinates.
        val captured = cellRow(bounds = Bounds(360, 400, 710, 750))
        val shifted = cellRow(bounds = Bounds(360, 946, 710, 1296))
        assertEquals(546, TapAdmissionGate.chebyshevEdgeDistance(captured.bounds, shifted.bounds))

        val outcome = AlbumPickDispatcher.dispatch(
            pick(), captured, frame(), listOf(shifted), frame(), safeArea(),
        )
        val refusal = assertIs<DispatchOutcome.Refused>(outcome).refusal
        assertEquals("BOUNDS_DRIFTED", refusal.code)
        assertTrue("546px" in refusal.reason)
    }

    @Test
    fun keyboardOccludedCellIsRefused() {
        // Gate linkage 2: the cell slid under the IME — never tappable.
        val row = cellRow(bounds = Bounds(360, 1900, 710, 2250))
        val ime = OccludedRegion(OccludedRegion.Kind.KEYBOARD, Bounds(0, 2000, 1080, 2400))
        val outcome = AlbumPickDispatcher.dispatch(
            pick(), row, frame(), listOf(row), frame(), safeArea(ime),
        )
        assertEquals("TARGET_OCCLUDED", assertIs<DispatchOutcome.Refused>(outcome).refusal.code)
    }

    @Test
    fun relabelledCellIsRefusedAsIdentityDrift() {
        // Gate linkage 3: same place, different node — the pick's marker row
        // was replaced by another cell's row (重复图 swap shape).
        val captured = cellRow(desc = "asset-2.jpg")
        val swapped = cellRow(desc = "asset-1.jpg")
        val outcome = AlbumPickDispatcher.dispatch(
            pick(), captured, frame(), listOf(swapped), frame(), safeArea(),
        )
        assertEquals("IDENTITY_DRIFT", assertIs<DispatchOutcome.Refused>(outcome).refusal.code)
    }

    @Test
    fun cellGoneFromTheFreshTreeIsRefusedAsMissing() {
        val outcome = AlbumPickDispatcher.dispatch(
            pick(), cellRow(), frame(), emptyList(), frame(), safeArea(),
        )
        assertEquals("TARGET_NODE_MISSING", assertIs<DispatchOutcome.Refused>(outcome).refusal.code)
    }

    @Test
    fun crossEpochFreshFrameIsRefusedByTheGate() {
        // The capture epoch and the pre-tap epoch differ: incomparable frames.
        val outcome = AlbumPickDispatcher.dispatch(
            pick(), cellRow(), frame(), listOf(cellRow()), frame().copy(sessionEpoch = 42L), safeArea(),
        )
        assertEquals("SESSION_EPOCH_CHANGED", assertIs<DispatchOutcome.Refused>(outcome).refusal.code)
    }

    @Test
    fun negativeCellIndexRefusesBeforeAnySampling() {
        val outcome = AlbumPickDispatcher.dispatch(
            pick(cellIndex = -1), cellRow(), frame(), listOf(cellRow()), frame(), safeArea(),
        )
        assertEquals("INVALID_PICK", assertIs<DispatchOutcome.Refused>(outcome).refusal.code)
    }

    // --- resample ------------------------------------------------------------

    @Test
    fun resampleFindsTheRowByDigestAndBreaksTiesByNearestBounds() {
        val captured = cellRow(bounds = Bounds(360, 400, 710, 750))
        // 重复图: byte-equal identity lines, two on-screen copies.
        val nearCopy = cellRow(bounds = Bounds(360, 860, 710, 1210)) // 460px away
        val farCopy = cellRow(bounds = Bounds(720, 1780, 1070, 2130)) // 1380px away
        val found = AlbumPickDispatcher.resample(listOf(farCopy, nearCopy), captured)!!
        assertEquals(nearCopy.bounds, found.bounds)
    }

    @Test
    fun resampleSkipsDegenerateRows() {
        val captured = cellRow()
        val collapsed = cellRow(bounds = Bounds(360, 400, 360, 750)) // width 0
        assertNull(AlbumPickDispatcher.resample(listOf(collapsed), captured))
    }

    // --- end to end: mapper -> planner -> dispatcher --------------------------

    @Test
    fun plannedPicksDispatchApproveOnTheIdenticalFreshPage() {
        val root = ObservedNode(
            0, 0, "android.view.View", "", "最近项目", "", screen, false,
        )
        val nodes = listOf(root) + listOf(
            gridCell(0, 1, "asset-2.jpg"),
            gridCell(1, 0, "asset-1.jpg"),
            gridCell(1, 1, "asset-0.jpg"),
        ).flatMap { (container, marker) -> listOf(container, marker) }

        val observation = AlbumPageMapper.map(nodes, scrollIndex = 0, observedAtMs = 1_000L)
        val staged = listOf(
            StagedMediaAsset("asset-0", 0, "asset-0.jpg", "sha-0", 100L, "image/jpeg"),
            StagedMediaAsset("asset-1", 1, "asset-1.jpg", "sha-1", 101L, "image/jpeg"),
            StagedMediaAsset("asset-2", 2, "asset-2.jpg", "sha-2", 102L, "image/jpeg"),
        )
        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(
                staged, listOf(observation.snapshot),
                AlbumShutterPolicy("yuyou-verified", exclusionVerified = true),
                SelectionBudget(10, 10, 100_000L),
            ),
        )
        assertEquals(3, planned.picks.size)

        // Fresh frame identical to the capture: every pick approves and taps
        // the center of its own cell.
        planned.picks.forEach { pick ->
            val cellNode = observation.cellNodes.first { it.cellIndex == pick.cellIndex }
            val outcome = AlbumPickDispatcher.dispatch(
                pick, cellNode.node, frame(), nodes, frame(), safeArea(),
            )
            val intent = assertIs<DispatchOutcome.Approved>(outcome).intent
            assertEquals(cellNode.bounds, intent.admittedBounds)
            assertEquals(
                (cellNode.bounds.left + cellNode.bounds.right) / 2,
                intent.tapX,
            )
            assertEquals(
                (cellNode.bounds.top + cellNode.bounds.bottom) / 2,
                intent.tapY,
            )
        }
    }

    /** Clickable container + marker child for the end-to-end grid. */
    private fun gridCell(row: Int, col: Int, desc: String): Pair<ObservedNode, ObservedNode> {
        val left = col * 360
        val top = 400 + row * 460
        val bounds = Bounds(left, top, left + 350, top + 350)
        return ObservedNode(
            depth = 2, index = row * 3 + col, className = "android.view.View",
            resourceId = "com.android.gallery3d:id/grid_item", text = "", contentDesc = "",
            bounds = bounds, clickable = true,
        ) to ObservedNode(
            depth = 3, index = row * 3 + col, className = "android.widget.ImageView",
            resourceId = "", text = "", contentDesc = desc,
            bounds = bounds, clickable = false,
        )
    }
}
