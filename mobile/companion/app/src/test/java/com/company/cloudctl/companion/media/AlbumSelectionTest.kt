package com.company.cloudctl.companion.media

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * B15 acceptance table, as pure JVM decisions over observed album pages:
 * old images, duplicate images, reverse ordering, shutter (screenshots),
 * edit/crop overlays, bounded pages/scrolls/deadline, fail-closed on wrong
 * image or wrong order, and album_index resume semantics.
 */
class AlbumSelectionTest {

    private val budget = SelectionBudget(maxPages = 10, maxScrolls = 10, deadlineMs = 100_000L)
    private val verifiedPolicy = AlbumShutterPolicy("yuyou-verified", exclusionVerified = true)
    private val unverifiedPolicy = AlbumShutterPolicy("other-build-77", exclusionVerified = false)

    // --- happy path, waiting, strict order ---------------------------------

    @Test
    fun waitsForVisibilityAndReturnsPicksInRequestedOrder() {
        val staged = staged("asset-0", "asset-1", "asset-2")
        val page1 = page(
            listOf(
                foreignCell(index = 0, id = 90, name = "IMG_0001.jpg"),
                cell(1, 30, "asset-2.jpg", sha = sha("asset-2"), size = 102L),
            ),
            scroll = 0,
        )
        // 反序排列: newest export (asset-2) lives in the first screen; the grid
        // lists asset-1 before asset-0 even though the request order differs.
        val page2 = page(
            listOf(
                cell(0, 20, "asset-1.jpg", sha = sha("asset-1"), size = 101L),
                cell(1, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L),
            ),
            scroll = 1,
        )

        val result = AlbumSelection.plan(staged, listOf(page1, page2), verifiedPolicy, budget)

        val planned = assertIs<AlbumSelectionResult.Planned>(result)
        assertEquals(listOf("asset-0", "asset-1", "asset-2"), planned.picks.map { it.assetId })
        assertEquals(List(3) { it }, planned.picks.map { it.orderIndex })
        assertEquals(listOf(10L, 20L, 30L), planned.picks.map { it.mediaStoreId })
        assertEquals(2, planned.pagesConsumed)
        assertEquals(1, planned.scrollsConsumed)
        planned.picks.forEach { assertEquals(MatchBasis.NAME_AND_HASH, it.basis) }
    }

    @Test
    fun oldImagesAndForeignScopeNeverMatch() {
        val staged = staged("asset-0")
        val pages = listOf(
            page(
                listOf(
                    // 旧图: camera pictures that predate the delivery.
                    foreignCell(index = 0, id = 91, name = "IMG_20250101.jpg", added = 50L),
                    foreignCell(index = 1, id = 92, name = "IMG_20250102.jpg", added = 60L),
                    // Same display name but outside Pictures/CloudCtl — foreign scope.
                    foreignCell(index = 2, id = 93, name = "asset-0.jpg", added = 70L),
                    cell(3, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L, added = 80L),
                ),
            ),
        )

        val planned = assertIs<AlbumSelectionResult.Planned>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        assertEquals(10L, planned.picks.single().mediaStoreId)
    }

    @Test
    fun duplicateIdenticalCellsResolveToTheNewestDeterministically() {
        val staged = staged("asset-0")
        val pages = listOf(
            page(
                listOf(
                    cell(0, 11, "asset-0.jpg", sha = sha("asset-0"), size = 100L, added = 9L),
                    cell(1, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L, added = 5L),
                ),
            ),
        )

        val planned = assertIs<AlbumSelectionResult.Planned>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        // Same bytes: either cell publishes the right image; pick is deterministic.
        assertEquals(11L, planned.picks.single().mediaStoreId)
    }

    @Test
    fun duplicateCellsWithoutDistinguishingEvidenceFailClosed() {
        val staged = staged("asset-0")
        val pages = listOf(
            page(
                listOf(
                    cell(0, 10, "asset-0.jpg"),
                    cell(1, 11, "asset-0.jpg"),
                ),
            ),
        )

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        val failure = assertIs<AlbumSelectionFailure.AmbiguousMarker>(failed.failure)
        assertEquals("asset-0", failure.assetId)
    }

    @Test
    fun provablyWrongImageStopsInsteadOfPicking() {
        val staged = staged("asset-0")
        val pages = listOf(
            page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("not-the-asset"), size = 100L))),
        )

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        val failure = assertIs<AlbumSelectionFailure.IdentityMismatch>(failed.failure)
        assertEquals("asset-0", failure.assetId)
    }

    // --- shutter (screenshot) policy ----------------------------------------

    @Test
    fun verifiedProfileProceedsWithoutProbeAndExcludesScreenshotCells() {
        val staged = staged("asset-0")
        val pages = listOf(
            page(
                listOf(
                    cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L),
                    cell(1, 11, "Screenshot_20260916.jpg", screenshot = true),
                ),
            ),
        )

        val planned = assertIs<AlbumSelectionResult.Planned>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        assertEquals(10L, planned.picks.single().mediaStoreId)
    }

    @Test
    fun unverifiedProfileWithoutProbeFailsClosed() {
        val staged = staged("asset-0")
        val pages = listOf(page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L))))

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, pages, unverifiedPolicy, budget))
        assertIs<AlbumSelectionFailure.RequiresShutterProbe>(failed.failure)
    }

    @Test
    fun probeFromADifferentProfileDoesNotVouch() {
        val staged = staged("asset-0")
        val pages = listOf(page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L))))
        val foreignProbe = ShutterProbe("yuyou-verified", screenshotsVisibleInAlbum = false, probedAtMs = 1L)

        val failed = assertIs<AlbumSelectionResult.Failed>(
            AlbumSelection.plan(staged, pages, unverifiedPolicy, budget, probe = foreignProbe),
        )
        assertIs<AlbumSelectionFailure.RequiresShutterProbe>(failed.failure)
    }

    @Test
    fun unverifiedProfileWithFreshProbeExposesScreenshotsAndStillMatches() {
        val staged = staged("asset-0")
        // A screenshot stole the marker name on this device version; the probe
        // says screenshots are visible, so the flag must gate the candidate.
        val pages = listOf(
            page(
                listOf(
                    cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L),
                    cell(1, 11, "asset-0.jpg", sha = sha("imposter"), size = 100L, screenshot = true),
                ),
            ),
        )
        val probe = ShutterProbe("other-build-77", screenshotsVisibleInAlbum = true, probedAtMs = 1L)

        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(staged, pages, unverifiedPolicy, budget, probe = probe),
        )
        assertEquals(10L, planned.picks.single().mediaStoreId)
    }

    // --- edit / crop overlay pages -------------------------------------------

    @Test
    fun editOverlayPagesContributeNoCellsButConsumeBudget() {
        val staged = staged("asset-0")
        val overlay = page(
            listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)),
            scroll = 0,
            at = 1_000L,
            overlay = true,
        )
        val grid = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)), scroll = 1)

        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(staged, listOf(overlay, grid), verifiedPolicy, budget),
        )
        assertEquals(10L, planned.picks.single().mediaStoreId)
        assertEquals(2, planned.pagesConsumed)
    }

    @Test
    fun editOverlayOnlySearchFailsExplicitlyWithoutRestarting() {
        val staged = staged("asset-0")
        val overlayOnly = page(
            listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)),
            overlay = true,
        )

        val failed = assertIs<AlbumSelectionResult.Failed>(
            AlbumSelection.plan(staged, listOf(overlayOnly), verifiedPolicy, budget),
        )
        assertIs<AlbumSelectionFailure.MissingAsset>(failed.failure)
    }

    // --- bounded search ------------------------------------------------------

    @Test
    fun pageBudgetExhaustionFailsExplicitly() {
        val staged = staged("asset-0")
        val empty = page(listOf(foreignCell(0, 90, "IMG_0001.jpg")))
        val match = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)), scroll = 1)
        val tight = budget.copy(maxPages = 1)

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, listOf(empty, match), verifiedPolicy, tight))
        assertIs<AlbumSelectionFailure.PageBudgetExhausted>(failed.failure)
    }

    @Test
    fun scrollBudgetExhaustionFailsExplicitly() {
        val staged = staged("asset-0")
        val first = page(listOf(foreignCell(0, 90, "IMG_0001.jpg")), scroll = 0)
        val match = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)), scroll = 1)
        val tight = budget.copy(maxScrolls = 0)

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, listOf(first, match), verifiedPolicy, tight))
        assertIs<AlbumSelectionFailure.ScrollBudgetExhausted>(failed.failure)
    }

    @Test
    fun pageObservedAfterDeadlineIsNotUsedEvenIfItMatches() {
        val staged = staged("asset-0")
        val first = page(listOf(foreignCell(0, 90, "IMG_0001.jpg")), at = 1_000L)
        val late = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)), at = 9_999L)
        val tight = budget.copy(deadlineMs = 5_000L)

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, listOf(first, late), verifiedPolicy, tight))
        assertIs<AlbumSelectionFailure.DeadlineExceeded>(failed.failure)
    }

    @Test
    fun missingAssetIsAnExplicitFailureNotARestart() {
        val staged = staged("asset-0")
        val pages = listOf(page(listOf(foreignCell(0, 90, "IMG_0001.jpg"))))

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        val failure = assertIs<AlbumSelectionFailure.MissingAsset>(failed.failure)
        assertEquals("asset-0", failure.assetId)
    }

    @Test
    fun identityFailureWinsOverBudgetExhaustion() {
        val staged = staged("asset-0")
        val wrong = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("wrong"), size = 100L)))
        val tight = budget.copy(maxPages = 1)

        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(staged, listOf(wrong, wrong), verifiedPolicy, tight))
        assertIs<AlbumSelectionFailure.IdentityMismatch>(failed.failure)
    }

    @Test
    fun earlySuccessStopsConsumingPages() {
        val staged = staged("asset-0")
        val match = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)))
        val noise = page(listOf(foreignCell(0, 91, "IMG_0002.jpg")), scroll = 1)

        val planned = assertIs<AlbumSelectionResult.Planned>(AlbumSelection.plan(staged, listOf(match, noise), verifiedPolicy, budget))
        assertEquals(1, planned.pagesConsumed)
    }

    // --- basis evolution ------------------------------------------------------

    @Test
    fun weakFirstObservationIsUpgradedByLaterCorroboration() {
        val staged = staged("asset-0")
        val weak = page(listOf(cell(0, 10, "asset-0.jpg")), at = 1_000L)
        val corroborated = page(listOf(cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L)), at = 2_000L)

        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(staged, listOf(weak, corroborated), verifiedPolicy, budget),
        )
        assertEquals(MatchBasis.NAME_AND_HASH, planned.picks.single().basis)
        assertEquals(2, planned.pagesConsumed)
    }

    @Test
    fun sizeCorroborationPicksWhenHashIsUnknown() {
        val staged = staged("asset-0")
        val pages = listOf(page(listOf(cell(0, 10, "asset-0.jpg", size = 100L))))

        val planned = assertIs<AlbumSelectionResult.Planned>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        assertEquals(MatchBasis.NAME_AND_SIZE, planned.picks.single().basis)
    }

    @Test
    fun markerAlonePicksWhenItIsTheOnlyCandidate() {
        val staged = staged("asset-0")
        val pages = listOf(page(listOf(cell(0, 10, "asset-0.jpg"))))

        val planned = assertIs<AlbumSelectionResult.Planned>(AlbumSelection.plan(staged, pages, verifiedPolicy, budget))
        assertEquals(MatchBasis.NAME_ONLY, planned.picks.single().basis)
    }

    // --- album_index resume ----------------------------------------------------

    @Test
    fun resumeFromAlbumIndexContinuesInsteadOfRestarting() {
        val staged = staged("asset-0", "asset-1", "asset-2")
        val pages = listOf(
            page(
                listOf(
                    cell(0, 10, "asset-0.jpg", sha = sha("asset-0"), size = 100L),
                    cell(1, 20, "asset-1.jpg", sha = sha("asset-1"), size = 101L),
                    cell(2, 30, "asset-2.jpg", sha = sha("asset-2"), size = 102L),
                ),
            ),
        )

        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(staged, pages, verifiedPolicy, budget, resumeFromAlbumIndex = 2),
        )
        // 断点后从该 index 继续: only the unfinished tail is planned.
        assertEquals(listOf("asset-2"), planned.picks.map { it.assetId })
        assertEquals(listOf(2), planned.picks.map { it.orderIndex })
    }

    @Test
    fun resumeIndexOutOfRangeFailsClosed() {
        val staged = staged("asset-0")
        val failed = assertIs<AlbumSelectionResult.Failed>(
            AlbumSelection.plan(staged, emptyList(), verifiedPolicy, budget, resumeFromAlbumIndex = 4),
        )
        assertIs<AlbumSelectionFailure.InvalidRequest>(failed.failure)
    }

    @Test
    fun stagedListMustBeContiguousAndUnique() {
        val gapped = listOf(
            StagedMediaAsset("asset-0", 0, "asset-0.jpg", sha("asset-0"), 100L, "image/jpeg"),
            StagedMediaAsset("asset-2", 2, "asset-2.jpg", sha("asset-2"), 102L, "image/jpeg"),
        )
        val failed = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(gapped, emptyList(), verifiedPolicy, budget))
        assertIs<AlbumSelectionFailure.InvalidRequest>(failed.failure)

        val duplicatedIds = listOf(
            StagedMediaAsset("asset-0", 0, "asset-0.jpg", sha("asset-0"), 100L, "image/jpeg"),
            StagedMediaAsset("asset-0", 1, "asset-0b.jpg", sha("asset-0"), 101L, "image/jpeg"),
        )
        val failedTwice = assertIs<AlbumSelectionResult.Failed>(AlbumSelection.plan(duplicatedIds, emptyList(), verifiedPolicy, budget))
        assertIs<AlbumSelectionFailure.InvalidRequest>(failedTwice.failure)
    }

    @Test
    fun fullyResumedSelectionPlansNothing() {
        val staged = staged("asset-0")
        val planned = assertIs<AlbumSelectionResult.Planned>(
            AlbumSelection.plan(staged, emptyList(), verifiedPolicy, budget, resumeFromAlbumIndex = 1),
        )
        assertNull(planned.picks.singleOrNull())
        assertTrue(planned.picks.isEmpty())
    }

    // --- helpers --------------------------------------------------------------

    private fun staged(vararg ids: String): List<StagedMediaAsset> =
        ids.mapIndexed { index, id ->
            StagedMediaAsset(
                assetId = id,
                orderIndex = index,
                fileName = "$id.jpg",
                sha256 = sha(id),
                sizeBytes = 100L + index,
                contentType = "image/jpeg",
            )
        }

    private fun page(
        cells: List<AlbumCell>,
        scroll: Int = 0,
        at: Long = 1_000L,
        overlay: Boolean = false,
    ) = AlbumPageSnapshot(cells = cells, scrollIndex = scroll, observedAtMs = at, isEditOverlayPage = overlay)

    private fun cell(
        index: Int,
        id: Long,
        name: String,
        sha: String? = null,
        size: Long? = null,
        added: Long? = null,
        screenshot: Boolean = false,
    ) = AlbumCell(
        cellIndex = index,
        mediaStoreId = id,
        displayName = name,
        sha256 = sha,
        sizeBytes = size,
        dateAddedSec = added,
        relativePath = "Pictures/CloudCtl/",
        isScreenshot = screenshot,
    )

    /** An unrelated picture from outside the delivery's owned scope. */
    private fun foreignCell(index: Int, id: Long, name: String, added: Long? = null) = AlbumCell(
        cellIndex = index,
        mediaStoreId = id,
        displayName = name,
        dateAddedSec = added,
        relativePath = "DCIM/Camera/",
    )

    private fun sha(value: String): String = java.security.MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
