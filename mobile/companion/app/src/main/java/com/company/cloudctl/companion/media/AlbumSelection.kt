package com.company.cloudctl.companion.media

/**
 * B15: ordered album selection planning. The planner turns staged media
 * identities (assetId + sha256 + orderIndex) plus a log of observed album grid
 * pages into an ordered tap plan. Matching is by verifiable business marker
 * (CloudCtl-scoped display name, corroborated by content hash / size) — never
 * "first N cells" or "cell N". Wrong order or wrong image stops the plan
 * (fail-closed); the caller must not publish from a failed plan.
 *
 * Pure logic: the device side feeds observed pages and executes the returned
 * taps. No Android types on purpose so the whole decision table is JVM-testable.
 */

/** One observed album grid cell. Device side fills this from the real picker. */
data class AlbumCell(
    val cellIndex: Int,
    val mediaStoreId: Long? = null,
    val displayName: String? = null,
    val sha256: String? = null,
    val sizeBytes: Long? = null,
    val dateAddedSec: Long? = null,
    val relativePath: String? = null,
    val isScreenshot: Boolean = false,
    val isEditOverlay: Boolean = false,
)

/** One page of the grid observed at a scroll position and timestamp. */
data class AlbumPageSnapshot(
    val cells: List<AlbumCell>,
    val scrollIndex: Int,
    val observedAtMs: Long,
    val isEditOverlayPage: Boolean = false,
)

/**
 * Device profile knowledge about shutter (screenshot) exclusion.
 * [exclusionVerified] is only true for profiles where the album view was
 * verified to hide screenshots; every other device version must re-probe
 * instead of inheriting the assumption.
 */
data class AlbumShutterPolicy(
    val profileId: String,
    val exclusionVerified: Boolean,
)

/** Fresh probe evidence gathered on this concrete device version. */
data class ShutterProbe(
    val profileId: String,
    val screenshotsVisibleInAlbum: Boolean,
    val probedAtMs: Long,
)

/** Hard limits: pages, scrolls and wall clock are all bounded. */
data class SelectionBudget(
    val maxPages: Int,
    val maxScrolls: Int,
    val deadlineMs: Long,
) {
    init {
        require(maxPages >= 1) { "maxPages must be >= 1" }
        require(maxScrolls >= 0) { "maxScrolls must be >= 0" }
        require(deadlineMs > 0) { "deadlineMs must be positive" }
    }
}

enum class MatchBasis { NAME_AND_HASH, NAME_AND_SIZE, NAME_ONLY }

data class AlbumPick(
    val assetId: String,
    val orderIndex: Int,
    val cellIndex: Int,
    val mediaStoreId: Long?,
    val matchedDisplayName: String,
    val basis: MatchBasis,
)

sealed interface AlbumSelectionFailure {
    val detail: String

    data class RequiresShutterProbe(override val detail: String) : AlbumSelectionFailure

    data class InvalidRequest(override val detail: String) : AlbumSelectionFailure

    data class MissingAsset(val assetId: String, override val detail: String) : AlbumSelectionFailure

    data class IdentityMismatch(val assetId: String, override val detail: String) : AlbumSelectionFailure

    data class AmbiguousMarker(val assetId: String, override val detail: String) : AlbumSelectionFailure

    data class PageBudgetExhausted(override val detail: String) : AlbumSelectionFailure

    data class ScrollBudgetExhausted(override val detail: String) : AlbumSelectionFailure

    data class DeadlineExceeded(override val detail: String) : AlbumSelectionFailure

    data class OrderInvariantViolated(override val detail: String) : AlbumSelectionFailure
}

sealed interface AlbumSelectionResult {
    /** Ordered tap plan; picks sequence equals the staged assetIds order. */
    data class Planned(
        val picks: List<AlbumPick>,
        val pagesConsumed: Int,
        val scrollsConsumed: Int,
    ) : AlbumSelectionResult

    data class Failed(val failure: AlbumSelectionFailure) : AlbumSelectionResult
}

object AlbumSelection {

    /**
     * Plans the ordered selection.
     *
     * @param staged ordered staged assets (typically from [StagedMediaPlan.pinOrder]).
     * @param pages observation log in chronological order (the wait-for-visibility
     *   loop on the device side appends pages as it scrolls/polls).
     * @param resumeFromAlbumIndex business progress from the ledger: selection
     *   continues from this index instead of restarting the whole order.
     */
    fun plan(
        staged: List<StagedMediaAsset>,
        pages: List<AlbumPageSnapshot>,
        policy: AlbumShutterPolicy,
        budget: SelectionBudget,
        resumeFromAlbumIndex: Int = 0,
        probe: ShutterProbe? = null,
    ): AlbumSelectionResult {
        validateStaged(staged, resumeFromAlbumIndex)?.let { return AlbumSelectionResult.Failed(it) }
        if (!policy.exclusionVerified) {
            val valid = probe != null && probe.profileId == policy.profileId
            if (!valid) {
                return AlbumSelectionResult.Failed(
                    AlbumSelectionFailure.RequiresShutterProbe(
                        "profile ${policy.profileId} has no verified shutter exclusion; " +
                            "a fresh probe for this device version is required before planning",
                    ),
                )
            }
        }

        val pending = staged.filter { it.orderIndex >= resumeFromAlbumIndex }
        if (pending.isEmpty()) {
            return AlbumSelectionResult.Planned(emptyList(), pagesConsumed = 0, scrollsConsumed = 0)
        }

        val pool = LinkedHashMap<String, PoolCell>()
        var pagesConsumed = 0
        var scrollsConsumed = 0
        var previousScroll: Int? = null
        var budgetStop: AlbumSelectionFailure? = null

        for (page in pages) {
            if (page.observedAtMs > budget.deadlineMs) {
                budgetStop = AlbumSelectionFailure.DeadlineExceeded(
                    "page observed at ${page.observedAtMs} after deadline ${budget.deadlineMs} " +
                        "with ${pending.countUnmatched(pool)} assets unmatched",
                )
                break
            }
            if (pagesConsumed >= budget.maxPages) {
                budgetStop = budgetStop ?: AlbumSelectionFailure.PageBudgetExhausted(
                    "consumed $pagesConsumed pages (max ${budget.maxPages}) " +
                        "with ${pending.countUnmatched(pool)} assets unmatched",
                )
                break
            }
            val delta = previousScroll?.let { page.scrollIndex - it }?.coerceAtLeast(0) ?: 0
            previousScroll = page.scrollIndex
            if (scrollsConsumed + delta > budget.maxScrolls) {
                budgetStop = budgetStop ?: AlbumSelectionFailure.ScrollBudgetExhausted(
                    "scrolls ${scrollsConsumed + delta} would exceed max ${budget.maxScrolls} " +
                        "with ${pending.countUnmatched(pool)} assets unmatched",
                )
                break
            }
            scrollsConsumed += delta
            pagesConsumed += 1
            if (!page.isEditOverlayPage) {
                page.cells.filterNot { it.isEditOverlay }.forEach { cell ->
                    pool.merge(poolKeyOf(page.scrollIndex, pagesConsumed, cell), PoolCell(cell)) { old, new ->
                        if (old.informationRank >= new.informationRank) old else new
                    }
                }
            }
            // Early success is only trusted when every remaining asset is pinned
            // by name + content hash; weaker bases keep consuming pages because
            // a later page can still corroborate or contradict them.
            val tentative = match(pending, pool)
            if (tentative is MatchOutcome.Complete && tentative.picks.all { it.basis == MatchBasis.NAME_AND_HASH }) {
                return finish(tentative.picks, pending, pagesConsumed, scrollsConsumed)
            }
        }

        return when (val outcome = match(pending, pool)) {
            is MatchOutcome.Complete -> finish(outcome.picks, pending, pagesConsumed, scrollsConsumed)
            is MatchOutcome.Incomplete -> AlbumSelectionResult.Failed(preferFailure(outcome, budgetStop))
        }
    }

    // --- internals -----------------------------------------------------------

    private const val OWNED_RELATIVE_DIR = "Pictures/CloudCtl"

    private fun validateStaged(staged: List<StagedMediaAsset>, resumeFromAlbumIndex: Int): AlbumSelectionFailure? {
        if (staged.isEmpty()) return AlbumSelectionFailure.InvalidRequest("staged asset list is empty")
        val orderIndexes = staged.map { it.orderIndex }.sorted()
        if (orderIndexes != List(staged.size) { it }) {
            return AlbumSelectionFailure.InvalidRequest("staged order indexes must be contiguous from 0")
        }
        if (staged.map { it.assetId }.toSet().size != staged.size) {
            return AlbumSelectionFailure.InvalidRequest("staged asset IDs must be unique")
        }
        if (resumeFromAlbumIndex !in 0..staged.size) {
            return AlbumSelectionFailure.InvalidRequest(
                "resume album_index $resumeFromAlbumIndex outside [0, ${staged.size}]",
            )
        }
        return null
    }

    private fun List<StagedMediaAsset>.countUnmatched(pool: LinkedHashMap<String, PoolCell>): Int {
        val taken = HashSet<String>()
        return count { asset -> matchOne(asset, pool, taken) !is SingleMatch.Picked }
    }

    private fun preferFailure(
        outcome: MatchOutcome.Incomplete,
        budgetStop: AlbumSelectionFailure?,
    ): AlbumSelectionFailure {
        // Identity problems are terminal and sharper than budget exhaustion:
        // more scrolling cannot fix a provably wrong or ambiguous marker.
        outcome.failures.firstOrNull { failure ->
            failure is AlbumSelectionFailure.IdentityMismatch || failure is AlbumSelectionFailure.AmbiguousMarker
        }?.let { return it }
        return budgetStop ?: outcome.failures.first()
    }

    private fun finish(
        picks: List<AlbumPick>,
        pending: List<StagedMediaAsset>,
        pagesConsumed: Int,
        scrollsConsumed: Int,
    ): AlbumSelectionResult {
        if (picks.map { it.assetId } != pending.map { it.assetId }) {
            return AlbumSelectionResult.Failed(
                AlbumSelectionFailure.OrderInvariantViolated(
                    "pick order ${picks.map { it.assetId }} does not equal requested ${pending.map { it.assetId }}",
                ),
            )
        }
        return AlbumSelectionResult.Planned(picks, pagesConsumed, scrollsConsumed)
    }

    /** Identity of an observed cell inside the pool. */
    private fun poolKeyOf(scrollIndex: Int, pageOrdinal: Int, cell: AlbumCell): String = when {
        cell.isEditOverlay -> "overlay:$pageOrdinal:${cell.cellIndex}"
        cell.mediaStoreId != null -> "id:${cell.mediaStoreId}"
        else -> "slot:$scrollIndex:${cell.cellIndex}"
    }

    private data class PoolCell(val cell: AlbumCell) {
        val informationRank: Int =
            (if (cell.sha256 != null) 2 else 0) + (if (cell.sizeBytes != null) 1 else 0)
    }

    private sealed interface MatchOutcome {
        data class Complete(val picks: List<AlbumPick>) : MatchOutcome

        data class Incomplete(val failures: List<AlbumSelectionFailure>) : MatchOutcome
    }

    private fun match(pending: List<StagedMediaAsset>, pool: LinkedHashMap<String, PoolCell>): MatchOutcome {
        val taken = HashSet<String>()
        val picks = mutableListOf<AlbumPick>()
        val failures = mutableListOf<AlbumSelectionFailure>()
        pending.forEach { asset ->
            when (val single = matchOne(asset, pool, taken)) {
                is SingleMatch.Picked -> picks += single.pick
                is SingleMatch.Failed -> failures += single.failure
            }
        }
        return if (failures.isEmpty()) MatchOutcome.Complete(picks) else MatchOutcome.Incomplete(failures)
    }

    private sealed interface SingleMatch {
        data class Picked(val pick: AlbumPick) : SingleMatch

        data class Failed(val failure: AlbumSelectionFailure) : SingleMatch
    }

    private fun matchOne(asset: StagedMediaAsset, pool: LinkedHashMap<String, PoolCell>, taken: MutableSet<String>): SingleMatch {
        val marker = asset.businessDisplayName
        // Screenshots never carry our marker legitimately; the flag also covers
        // verified-profile anomalies, so shutter exclusion is unconditional.
        val candidates = pool.entries
            .filterNot { it.key in taken }
            .filterNot { it.value.cell.isEditOverlay }
            .filterNot { it.value.cell.isScreenshot }
            .filter { it.value.cell.displayName == marker }
            .filter { inOwnedScope(it.value.cell) }
        if (candidates.isEmpty()) {
            return SingleMatch.Failed(
                AlbumSelectionFailure.MissingAsset(
                    asset.assetId,
                    "no in-scope album cell carries marker '$marker' (consumed ${pool.size} cells)",
                ),
            )
        }
        val hashMatches = candidates.filter { it.value.cell.sha256 == asset.sha256 }
        if (hashMatches.isNotEmpty()) {
            val pick = hashMatches.maxWithOrNull(
                compareBy(
                    { it.value.cell.dateAddedSec ?: Long.MIN_VALUE },
                    { it.value.cell.mediaStoreId ?: Long.MIN_VALUE },
                    { it.key },
                ),
            ) ?: return SingleMatch.Failed(
                AlbumSelectionFailure.IdentityMismatch(
                    asset.assetId,
                    "marker '$marker' only matches screenshot-flagged cells",
                ),
            )
            taken += pick.key
            return SingleMatch.Picked(
                AlbumPick(
                    assetId = asset.assetId,
                    orderIndex = asset.orderIndex,
                    cellIndex = pick.value.cell.cellIndex,
                    mediaStoreId = pick.value.cell.mediaStoreId,
                    matchedDisplayName = marker,
                    basis = MatchBasis.NAME_AND_HASH,
                ),
            )
        }
        val contradicting = candidates.count { cell ->
            val sha = cell.value.cell.sha256
            val size = cell.value.cell.sizeBytes
            (sha != null && sha != asset.sha256) || (size != null && size != asset.sizeBytes)
        }
        if (contradicting == candidates.size) {
            return SingleMatch.Failed(
                AlbumSelectionFailure.IdentityMismatch(
                    asset.assetId,
                    "every marker-matching cell for '$marker' contradicts the staged identity",
                ),
            )
        }
        val sizeMatches = candidates.filter { it.value.cell.sizeBytes != null && it.value.cell.sizeBytes == asset.sizeBytes }
        if (sizeMatches.size == 1) {
            val entry = sizeMatches.single()
            taken += entry.key
            return SingleMatch.Picked(
                AlbumPick(
                    assetId = asset.assetId,
                    orderIndex = asset.orderIndex,
                    cellIndex = entry.value.cell.cellIndex,
                    mediaStoreId = entry.value.cell.mediaStoreId,
                    matchedDisplayName = marker,
                    basis = MatchBasis.NAME_AND_SIZE,
                ),
            )
        }
        val evidences = candidates.filter { it.value.cell.sizeBytes == null && it.value.cell.sha256 == null }
        if (sizeMatches.isEmpty() && evidences.size == 1) {
            val entry = evidences.single()
            taken += entry.key
            return SingleMatch.Picked(
                AlbumPick(
                    assetId = asset.assetId,
                    orderIndex = asset.orderIndex,
                    cellIndex = entry.value.cell.cellIndex,
                    mediaStoreId = entry.value.cell.mediaStoreId,
                    matchedDisplayName = marker,
                    basis = MatchBasis.NAME_ONLY,
                ),
            )
        }
        return SingleMatch.Failed(
            AlbumSelectionFailure.AmbiguousMarker(
                asset.assetId,
                "marker '$marker' matches ${candidates.size} cells without a distinguishing hash " +
                    "(${sizeMatches.size} size matches, ${evidences.size} evidence-free)",
            ),
        )
    }

    private fun inOwnedScope(cell: AlbumCell): Boolean {
        val path = cell.relativePath ?: return true
        return path == OWNED_RELATIVE_DIR || path.startsWith("$OWNED_RELATIVE_DIR/")
    }
}
