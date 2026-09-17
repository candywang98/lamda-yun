package com.company.cloudctl.companion.locators

import com.company.cloudctl.companion.media.AlbumCell
import com.company.cloudctl.companion.media.AlbumPageSnapshot
import com.company.cloudctl.companion.observation.Bounds
import com.company.cloudctl.companion.observation.ObservedNode

/**
 * B15X (fleet-first-20260916.1) — device-side supply of the B15 album
 * observation: turns a canonical [ObservedNode] tree (B12, read-only import)
 * into the media package's [AlbumPageSnapshot] plus the canonical tap row of
 * every observed cell, so [AlbumPickDispatcher] can later turn an
 * [com.company.cloudctl.companion.media.AlbumPick] into a gated tap intent.
 *
 * Recognition is by node text/content-desc LINES in the
 * [com.company.cloudctl.companion.automation.XianyuMaintenanceLayout.parseBadge]
 * style: a line that fully looks like a gallery display name (extension
 * included, no path characters) is the cell's marker. Fields the tree cannot
 * honestly provide — mediaStoreId, sha256, dateAddedSec, relativePath — are
 * left null and NEVER fabricated (ui-observation/v1 §4); enriching them is a
 * device-side MediaStore seam, not a parsing guess. Human-rounded sizes like
 * "1.2 MB" are deliberately NOT converted to bytes: a rounded value can never
 * equal the staged exact sizeBytes and would fabricate a contradiction.
 *
 * ObservedNode has no visibility flag in the frozen model; a degenerate
 * rectangle (zero width/height) is the only "not laid out" signal and such
 * nodes are skipped.
 */
object AlbumPageMapper {

    // --- caps (pageSummary style: bound the pass even on pathological trees) ---

    /** Nodes deeper than this are pruning artifacts, not business rows. */
    const val MAX_DEPTH = 30

    /** Hard node budget per observed page. */
    const val MAX_NODES = 400

    /**
     * Row/column clustering tolerance. Same value as
     * [TapAdmissionGate.DRIFT_TOLERANCE_PX] on purpose: a sub-40px edge jitter
     * is the same benign frame noise both sides must tolerate.
     */
    const val GRID_ALIGNMENT_TOLERANCE_PX = 40

    /**
     * Strong edit/crop-screen markers — strings that never appear on the plain
     * album grid page. 「编辑」 alone is NOT a marker: grid pages carry a
     * select-all 编辑 button, so admitting it would flag every grid as overlay.
     */
    private val EDIT_PAGE_MARKERS = listOf("裁剪", "旋转", "滤镜", "调节")

    /** Screenshot markers for the B15 unconditional shutter exclusion. */
    private val SCREENSHOT_MARKERS = listOf("截图", "截屏", "screenshot")

    /** Extensions the media package's GalleryNaming can produce. */
    private val FILENAME_LINE = Regex(
        """^[^/:*?"<>|]{1,160}\.(jpe?g|png|webp|gif|mp4|webm)$""",
        RegexOption.IGNORE_CASE,
    )

    /** Only an explicit byte count is honest enough to become sizeBytes. */
    private val STRICT_BYTES_LINE = Regex("""^(\d{1,15})\s*(B|bytes?|字节)$""", RegexOption.IGNORE_CASE)

    /** One observed cell: snapshot row (media package types) + canonical tap row. */
    data class AlbumCellNode(
        val cellIndex: Int,
        /** The clickable container the dispatcher will re-find and tap. */
        val node: ObservedNode,
        val bounds: Bounds,
        /** [TapAdmissionGate.identityDigestOf] of [node] (geometry excluded). */
        val identityDigest: String,
    )

    /** Mapper output: the B15 snapshot plus the geometry needed to act on it. */
    data class AlbumPageObservation(
        val snapshot: AlbumPageSnapshot,
        /** Parallel to [AlbumPageSnapshot.cells] (same order, same cellIndex). */
        val cellNodes: List<AlbumCellNode>,
        /** Distinct column count observed on this page (grid geometry diagnostic). */
        val columns: Int,
        /** True when depth/node caps truncated the pass — observation is partial. */
        val truncated: Boolean,
    )

    /**
     * Maps one observed album page.
     *
     * @param nodes canonical tree of the page (B12 flat list; order irrelevant,
     *   re-sorted by (depth, index) like CanonicalTree does).
     * @param scrollIndex scroll position the page was observed at (B15 key).
     * @param observedAtMs wall-clock of the observation (B15 budget key).
     * @param viewport live screen rectangle when known; cells with no overlap
     *   are dropped (recycled/offscreen), PARTIALLY visible cells are kept.
     */
    fun map(
        nodes: List<ObservedNode>,
        scrollIndex: Int,
        observedAtMs: Long,
        viewport: Bounds? = null,
    ): AlbumPageObservation {
        val capped = nodes
            .filter { it.depth in 0..MAX_DEPTH }
            .sortedWith(compareBy({ it.depth }, { it.index }))
        val considered = capped.take(MAX_NODES)
        val truncated = considered.size < capped.size || nodes.any { it.depth > MAX_DEPTH }

        val laidOut = considered.filter { it.bounds.width > 0 && it.bounds.height > 0 }
        val isEditOverlayPage = laidOut.any { node -> node.lines().any { line -> line.isEditMarker() } }

        // Candidate marker nodes -> the deepest clickable container that wraps
        // them (the actual tap row); grouped so one cell contributes once even
        // when both the image desc and a label text carry the marker.
        data class Group(
            var displayName: String? = null,
            var sizeBytes: Long? = null,
            var isScreenshot: Boolean = false,
        )

        val groups = LinkedHashMap<Pair<Int, Int>, Pair<ObservedNode, Group>>()
        for (candidate in laidOut) {
            val lines = candidate.lines()
            val fileName = lines.firstOrNull { FILENAME_LINE.matches(it) }
            val screenshot = lines.any { line -> SCREENSHOT_MARKERS.any { line.contains(it, ignoreCase = true) } }
            if (fileName == null && !screenshot) continue
            val tapRow = tapRowOf(candidate, laidOut)
            val group = groups.getOrPut(tapRow.depth to tapRow.index) { tapRow to Group() }.second
            if (group.displayName == null && fileName != null) group.displayName = fileName
            if (group.sizeBytes == null) {
                lines.firstNotNullOfOrNull { line ->
                    STRICT_BYTES_LINE.matchEntire(line)?.groupValues?.get(1)?.toLong()
                }?.let { group.sizeBytes = it }
            }
            if (screenshot) group.isScreenshot = true
        }

        // Cells outside the live viewport were recycled/offscreen; PARTIALLY
        // visible cells stay (they are on screen and B15's pool keeps the
        // better observation when the same slot reappears fully later).
        val visible = groups.values
            .filter { (tapRow, _) -> viewport == null || viewport.intersects(tapRow.bounds) }

        // Grid geometry: cluster rows by top edge, columns by left edge, index
        // row-major (reading order). Stable for a re-observed identical page.
        val rowClusters = cluster(visible.map { it.first.bounds.top })
        val colClusters = cluster(visible.map { it.first.bounds.left })
        val columns = colClusters.size
        val indexed = visible
            .map { (tapRow, group) ->
                val row = rowClusters.indexOfFirst { tapRow.bounds.top in it }
                val col = colClusters.indexOfFirst { tapRow.bounds.left in it }
                IndexedValue(row * columns + col, tapRow to group)
            }
            .sortedBy { it.index }

        val snapshotCells = indexed.map { (slot, tapRowAndGroup) ->
            val (tapRow, group) = tapRowAndGroup
            AlbumCell(
                cellIndex = slot,
                // Not readable from the accessibility tree — never fabricated.
                mediaStoreId = null,
                displayName = group.displayName,
                sha256 = null,
                sizeBytes = group.sizeBytes,
                dateAddedSec = null,
                relativePath = null,
                isScreenshot = group.isScreenshot,
                // Whole page is a crop/edit overlay: every cell on it is a
                // film-strip thumbnail, not a selectable grid cell (B15).
                isEditOverlay = isEditOverlayPage,
            )
        }

        val cellNodes = indexed.map { (slot, tapRowAndGroup) ->
            val (tapRow, _) = tapRowAndGroup
            AlbumCellNode(
                cellIndex = slot,
                node = tapRow,
                bounds = tapRow.bounds,
                identityDigest = TapAdmissionGate.identityDigestOf(tapRow),
            )
        }

        return AlbumPageObservation(
            snapshot = AlbumPageSnapshot(
                cells = snapshotCells,
                scrollIndex = scrollIndex,
                observedAtMs = observedAtMs,
                isEditOverlayPage = isEditOverlayPage,
            ),
            cellNodes = cellNodes,
            columns = columns,
            truncated = truncated,
        )
    }

    // --- internals -----------------------------------------------------------

    /**
     * The tap row of a marker node: the DEEPEST clickable node (including the
     * node itself) whose rectangle fully contains the marker's rectangle.
     * Deepest wins because a cell sits inside the grid container, both may be
     * clickable, and the cell is the one a tap must select.
     */
    private fun tapRowOf(marker: ObservedNode, laidOut: List<ObservedNode>): ObservedNode =
        laidOut
            .filter { it.clickable && it.bounds.contains(marker.bounds) }
            .maxWithOrNull(compareBy({ it.depth }, { it.index }))
            ?: marker

    /** Sequential edge clustering within [GRID_ALIGNMENT_TOLERANCE_PX]. */
    private fun cluster(edges: List<Int>): List<IntRange> {
        if (edges.isEmpty()) return emptyList()
        val clusters = ArrayList<IntRange>()
        var start = edges.min()
        var prev = start
        for (value in edges.sorted()) {
            if (value - prev > GRID_ALIGNMENT_TOLERANCE_PX) {
                clusters += start..prev
                start = value
            }
            prev = value
        }
        clusters += start..prev
        return clusters
    }

    private fun ObservedNode.lines(): List<String> =
        listOf(text, contentDesc)
            .flatMap { it.split('\n') }
            .map { it.trim() }
            .filter { it.isNotEmpty() }

    private fun String.isEditMarker(): Boolean = EDIT_PAGE_MARKERS.any { contains(it) }

    /** Intersection test absent from the frozen observation Bounds (kept read-only). */
    private fun Bounds.intersects(other: Bounds): Boolean =
        left < other.right && other.left < right && top < other.bottom && other.top < bottom
}
