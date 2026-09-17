package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.media.AlbumSelection
import com.company.cloudctl.companion.media.AlbumSelectionFailure
import com.company.cloudctl.companion.media.AlbumSelectionResult
import com.company.cloudctl.companion.media.AlbumShutterPolicy
import com.company.cloudctl.companion.media.MatchBasis
import com.company.cloudctl.companion.media.SelectionBudget
import com.company.cloudctl.companion.media.StagedMediaAsset
import com.company.cloudctl.companion.observation.Bounds
import com.company.cloudctl.companion.observation.ObservedNode
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B15X — device-side supply of the B15 album observation. Real-shaped picker
 * fixtures (grid cells with clickable containers, filename markers in the
 * image desc, screenshot cells, edit/crop overlay pages, partially visible
 * rows, duplicate images) are mapped to [com.company.cloudctl.companion.media.AlbumPageSnapshot]
 * rows and, end to end, actually drive the B15 planner.
 */
class AlbumPageMapperTest {

    private val screen = Bounds(0, 0, 1080, 2400)
    private val budget = SelectionBudget(maxPages = 10, maxScrolls = 10, deadlineMs = 100_000L)
    private val verifiedPolicy = AlbumShutterPolicy("yuyou-verified", exclusionVerified = true)

    // --- fixture builders (canonical-tree shape of a picker grid page) ------

    private fun node(
        depth: Int,
        index: Int,
        bounds: Bounds,
        text: String = "",
        desc: String = "",
        clickable: Boolean = false,
    ) = ObservedNode(
        depth = depth,
        index = index,
        className = "android.view.View",
        resourceId = "com.android.gallery3d:id/grid_item",
        text = text,
        contentDesc = desc,
        bounds = bounds,
        clickable = clickable,
    )

    /** One grid cell: clickable container (depth 2) + marker image child (depth 3). */
    private fun cell(row: Int, col: Int, desc: String, clickable: Boolean = true): List<ObservedNode> {
        val left = col * 360
        val top = 400 + row * 460
        val container = Bounds(left, top, left + 350, top + 350)
        return listOf(
            node(2, row * 3 + col, container, clickable = clickable),
            node(3, row * 3 + col, container, desc = desc),
        )
    }

    /**
     * Realistic mixed first page (2 rows x 3 cols): a foreign camera photo, a
     * human-rounded size line, a screenshot cell, an exact byte line, and two
     * duplicate-marker cells.
     */
    private fun mixedGridPage(): List<ObservedNode> = listOf(
        node(0, 0, screen, text = "最近项目"),
        node(1, 0, Bounds(0, 100, 1080, 380), text = "相册"),
    ) + cell(0, 0, "IMG_20250101.jpg") + // 旧图 (camera photo)
        cell(0, 1, "asset-2.jpg\n1.2 MB") + // rounded size is NOT bytes
        cell(0, 2, "Screenshot_20260916_102301.png\n屏幕截图") + // 快门 cell
        cell(1, 0, "asset-1.jpg\n102400 字节") + // strict byte line
        cell(1, 1, "asset-0.jpg") +
        cell(1, 2, "asset-0.jpg") // 重复图

    // --- mapping -------------------------------------------------------------

    @Test
    fun mapsGridRowsRowMajorWithHonestFields() {
        val observation = AlbumPageMapper.map(mixedGridPage(), scrollIndex = 0, observedAtMs = 1_000L)

        val snapshot = observation.snapshot
        assertEquals(0, snapshot.scrollIndex)
        assertEquals(1_000L, snapshot.observedAtMs)
        assertEquals(false, snapshot.isEditOverlayPage)
        assertEquals(3, observation.columns)
        assertEquals(false, observation.truncated)

        // Row-major reading order: (row,col) -> 3*row + col.
        assertEquals(
            listOf(0, 1, 2, 3, 4, 5),
            snapshot.cells.map { it.cellIndex },
        )
        assertEquals("IMG_20250101.jpg", snapshot.cells[0].displayName)
        assertEquals("asset-2.jpg", snapshot.cells[1].displayName)

        // Fields the tree cannot honestly provide stay null — never fabricated.
        snapshot.cells.forEach { cellRow ->
            assertNull(cellRow.mediaStoreId)
            assertNull(cellRow.sha256)
            assertNull(cellRow.dateAddedSec)
            assertNull(cellRow.relativePath)
        }
        // "1.2 MB" is rounded — converting it would invent a contradicting size.
        assertNull(snapshot.cells[1].sizeBytes)
        // An explicit byte line parses.
        assertEquals(102400L, snapshot.cells[3].sizeBytes)
        // Screenshot recognized by both its filename and the 截图 desc line.
        assertTrue(snapshot.cells[2].isScreenshot)
        assertTrue(snapshot.cells[0].displayName!!.startsWith("IMG_"))
        assertEquals(false, snapshot.cells[0].isScreenshot)
    }

    @Test
    fun duplicateMarkerCellsAreBothMappedNotCollapsed() {
        val snapshot = AlbumPageMapper.map(mixedGridPage(), 0, 1_000L).snapshot
        val duplicates = snapshot.cells.filter { it.displayName == "asset-0.jpg" }
        assertEquals(2, duplicates.size)
        assertEquals(listOf(4, 5), duplicates.map { it.cellIndex })
    }

    @Test
    fun tapRowIsTheClickableContainerNotTheMarkerChild() {
        val observation = AlbumPageMapper.map(mixedGridPage(), 0, 1_000L)
        // The canonical row of slot 1 is the depth-2 clickable container.
        val cellNode = observation.cellNodes.first { it.cellIndex == 1 }
        assertTrue(cellNode.node.clickable)
        assertEquals(2, cellNode.node.depth)
        assertEquals(TapAdmissionGate.identityDigestOf(cellNode.node), cellNode.identityDigest)
        // cellNodes stay parallel to snapshot.cells.
        assertEquals(observation.snapshot.cells.map { it.cellIndex }, observation.cellNodes.map { it.cellIndex })
    }

    @Test
    fun editOverlayPageIsFlaggedAndItsCellsAreOverlayCells() {
        // Crop screen: strong markers (裁剪/旋转/滤镜) + a horizontal film strip.
        val cropPage = listOf(
            node(0, 0, screen, text = "编辑图片"),
            node(1, 0, Bounds(0, 120, 1080, 220), text = "裁剪\n旋转\n滤镜"),
            node(2, 0, Bounds(0, 300, 1080, 1800), desc = "asset-0.jpg\n预览"), // main preview
        ) + cell(3, 0, "asset-0.jpg") + cell(3, 1, "asset-1.jpg") + cell(3, 2, "asset-2.jpg")

        val observation = AlbumPageMapper.map(cropPage, 0, 1_000L)

        assertTrue(observation.snapshot.isEditOverlayPage)
        // Film-strip thumbs map as cells but carry the B15 overlay semantics:
        // one row of 3 columns, every cell an edit-overlay cell.
        assertEquals(3, observation.columns)
        assertTrue(observation.snapshot.cells.isNotEmpty())
        observation.snapshot.cells.forEach { assertTrue(it.isEditOverlay, "cell ${it.cellIndex}") }
    }

    @Test
    fun partiallyVisibleRowsStayAndFullyOffscreenCellsDrop() {
        // cell() rows: top = 400 + row*460 -> row 4 spans 2240..2590 (clipped
        // by the 2400 screen bottom but visible: STAYS) and row 5 spans
        // 2700..3050 (fully offscreen / recycled: DROPS).
        val page = mixedGridPage() +
            cell(4, 0, "asset-9.jpg") +
            cell(5, 0, "asset-8.jpg")

        val observation = AlbumPageMapper.map(page, 0, 1_000L, viewport = screen)

        val names = observation.snapshot.cells.map { it.displayName }
        assertTrue("asset-9.jpg" in names, "clipped-but-visible cell must stay")
        assertTrue("asset-8.jpg" !in names, "fully offscreen cell must drop")
    }

    @Test
    fun degenerateBoundsAndDepthCapAreSkippedAndFlagged() {
        // Not laid out (zero-size) marker node: invisible to the mapper.
        val zeroSize = node(9, 99, Bounds(0, 0, 0, 0), desc = "ghost.jpg")
        // Beyond the depth cap: pruning artifact carrying a real-looking marker.
        val tooDeep = node(AlbumPageMapper.MAX_DEPTH + 1, 98, Bounds(0, 400, 350, 750), desc = "deep.jpg")
        val page = cell(0, 0, "asset-0.jpg") + listOf(zeroSize, tooDeep)

        val observation = AlbumPageMapper.map(page, 0, 1_000L)

        val names = observation.snapshot.cells.map { it.displayName }
        assertEquals(listOf("asset-0.jpg"), names)
        assertTrue(observation.truncated, "depth cap hit must set the truncated flag")
    }

    @Test
    fun nodeCapBoundsThePassOnPathologicalTrees() {
        val flood = (0 until AlbumPageMapper.MAX_NODES + 50).map { i ->
            node(1, i, Bounds(0, 0, 10, 10), desc = "flood_$i.jpg")
        }
        val observation = AlbumPageMapper.map(flood, 0, 1_000L)
        assertTrue(observation.truncated)
        assertTrue(observation.snapshot.cells.size <= AlbumPageMapper.MAX_NODES)
    }

    // --- end-to-end supply into the B15 planner ------------------------------

    @Test
    fun mappedSnapshotDrivesThePlannerWithoutFabricatedIdentity() {
        // Same grid minus the duplicate cells: name-only matching must succeed
        // because each marker is unique on the page.
        val page = listOf(
            node(0, 0, screen, text = "最近项目"),
        ) + cell(0, 1, "asset-2.jpg") +
            cell(1, 0, "asset-1.jpg") +
            cell(1, 1, "asset-0.jpg") +
            cell(0, 2, "Screenshot_20260916_102301.png\n屏幕截图") // 快门 cell stays excluded

        val observation = AlbumPageMapper.map(page, scrollIndex = 0, observedAtMs = 1_000L)
        val staged = listOf(
            stagedAsset("asset-0", 0),
            stagedAsset("asset-1", 1),
            stagedAsset("asset-2", 2),
        )

        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(staged, listOf(observation.snapshot), verifiedPolicy, budget),
        )
        assertEquals(listOf("asset-0", "asset-1", "asset-2"), planned.picks.map { it.assetId })
        // No hash/size from the tree: every pick is name-only, honestly weak.
        planned.picks.forEach { assertEquals(MatchBasis.NAME_ONLY, it.basis) }
    }

    @Test
    fun duplicateCellsFromTheTreeFailClosedInThePlanner() {
        val observation = AlbumPageMapper.map(mixedGridPage(), 0, 1_000L)
        val staged = listOf(stagedAsset("asset-0", 0))

        val failed = assertIs<AlbumSelectionResult.Failed>(
            AlbumSelection.plan(staged, listOf(observation.snapshot), verifiedPolicy, budget),
        )
        // 重复图: two evidence-free marker cells -> ambiguity, not first-match.
        assertIs<AlbumSelectionFailure.AmbiguousMarker>(failed.failure)
    }

    private fun stagedAsset(id: String, order: Int) = StagedMediaAsset(
        assetId = id,
        orderIndex = order,
        fileName = "$id.jpg",
        sha256 = "sha-$id",
        sizeBytes = 100L + order,
        contentType = "image/jpeg",
    )
}
