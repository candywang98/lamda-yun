package com.company.cloudctl.companion.automation

/**
 * W4 maintenance v2 title-located card selection (contract
 * xianyu-anchors-20260915 §1/§2), pure JVM in the OrderRowParser style.
 *
 * The published-goods lists expose each card's full text to the accessibility
 * tree (在卖: 托管/降价/编辑/诊断 + 标题 + 曝光/浏览/想要 + ¥价格; 已下架: 下架原因 +
 * 删除/重新上架 + 标题 + 浏览N + ¥价格), and card heights are uneven, so the
 * ONLY reliable card address is the title text. A card is the ancestor block
 * of the title line, modeled here as a direct child of a scrollable list
 * container; the today-data card and the right-hand promo slot sit ABOVE the
 * tabs and are excluded by the live tab-strip bottom edge (never a hardcoded
 * y, per contract §0).
 *
 * Every miss fails safe: zero matches -> NotFound, several distinct matching
 * cards -> Ambiguous; the caller then aborts the step before any gesture.
 */
object PublishedCardLocator {

    /** Screen rectangle in raw pixels (android.graphics.Rect stays out of the JVM tests). */
    data class Bounds(val left: Int, val top: Int, val right: Int, val bottom: Int) {
        val centerX: Float get() = (left + right) / 2f
        val centerY: Float get() = (top + bottom) / 2f
    }

    /** Read-only snapshot of one accessibility node (own text/desc only, children separate). */
    data class UiNode(
        val text: String?,
        val description: String?,
        val visible: Boolean,
        val bounds: Bounds,
        val children: List<UiNode>,
    )

    sealed interface Outcome {
        /** Exactly one matching card; tap the bounds center. */
        data class Card(val bounds: Bounds, val matchedLine: String) : Outcome

        /** Searched the visible cards under every scrollable; no text matched. */
        data object NotFound : Outcome

        /** Several distinct cards matched the fragment; tapping would be a guess. */
        data class Ambiguous(val count: Int, val matchedLines: List<String>) : Outcome

        /** Text matched, but no structurally safe card rectangle could be proved. */
        data class UnverifiedBounds(val matchedLines: List<String>) : Outcome
    }

    /**
     * @param scrollables snapshots of the outermost visible scrollable containers
     *   (the service stops descending at the first scrollable per branch).
     * @param cardAreaTop live bottom edge of the published tab strip; card
     *   candidates must start at or below it (promo/today blocks sit above).
     * @param titleContains 1..64 char fragment matched against every visible
     *   node's own text or content description inside a card.
     */
    fun locate(scrollables: List<UiNode>, cardAreaTop: Int, titleContains: String): Outcome {
        // Device-verified 2026-09-16 (incident: wrong-card delist): the live tree
        // nests ALL cards under ONE full-list wrapper child of the scrollable
        // (uiautomator flattens them into siblings, the accessibility tree does
        // not), and the card text blob itself carries the card rectangle. Match
        // every own-text node subtree-wide, then resolve the tap rectangle as
        // the matched node's own bounds or its nearest ancestor that starts at
        // or below the tab strip — never the scrollable itself. Nested
        // parent/child matches for one card collapse into the smallest bounds.
        val matches = mutableListOf<Pair<Bounds, String>>()
        val unverified = mutableListOf<String>()
        for (scrollable in scrollables) {
            for (child in scrollable.children) {
                collectMatches(
                    node = child,
                    ancestors = emptyList(),
                    scrollBounds = scrollable.bounds,
                    cardAreaTop = cardAreaTop,
                    titleContains = titleContains,
                    out = matches,
                    unverified = unverified,
                )
            }
        }
        val distinct = collapseNested(matches)
        return when (distinct.size) {
            0 -> if (unverified.isEmpty()) Outcome.NotFound else Outcome.UnverifiedBounds(unverified.distinct())
            1 -> Outcome.Card(distinct.single().first, distinct.single().second)
            else -> Outcome.Ambiguous(distinct.size, distinct.map { it.second })
        }
    }

    /**
     * Record one match per own-text/desc hit. [ancestors] excludes the
     * scrollable root, so a match whose whole chain sits above the tab strip
     * (promo block) is rejected instead of climbing onto the container.
     */
    private fun collectMatches(
        node: UiNode,
        ancestors: List<UiNode>,
        scrollBounds: Bounds,
        cardAreaTop: Int,
        titleContains: String,
        out: MutableList<Pair<Bounds, String>>,
        unverified: MutableList<String>,
    ) {
        if (!node.visible) return
        val line = node.text?.takeIf { it.contains(titleContains) }
            ?: node.description?.takeIf { it.contains(titleContains) }
        if (line != null) {
            val chain = listOf(node) + ancestors
            val rect = chain
                .firstOrNull { isCardBounds(it, scrollBounds, cardAreaTop) }
                ?.bounds
            if (rect != null) {
                out += rect to line
            } else if (chain.any { it.visible && it.bounds.bottom > cardAreaTop }) {
                unverified += line
            }
        }
        for (child in node.children) {
            collectMatches(
                child,
                listOf(node) + ancestors,
                scrollBounds,
                cardAreaTop,
                titleContains,
                out,
                unverified,
            )
        }
    }

    /**
     * The title is only an anchor. A tap rectangle must be a substantial region
     * inside the live list; full-list wrappers and tiny text leaves fail closed.
     */
    private fun isCardBounds(node: UiNode, scroll: Bounds, cardAreaTop: Int): Boolean {
        if (!node.visible) return false
        val bounds = node.bounds
        val scrollWidth = scroll.right - scroll.left
        val scrollHeight = scroll.bottom - scroll.top
        val width = bounds.right - bounds.left
        val height = bounds.bottom - bounds.top
        if (scrollWidth <= 0 || scrollHeight <= 0 || width <= 0 || height <= 0) return false
        if (bounds.top < cardAreaTop || !contains(scroll, bounds) || bounds == scroll) return false
        if (bounds.top <= cardAreaTop && bounds.bottom >= scroll.bottom) return false

        // Published product cards are horizontal content blocks. A candidate
        // taller than its own width is a remaining-list wrapper, not one card.
        if (height > width) return false

        // Ratios keep the guard independent of screen resolution.
        if (width * 5 < scrollWidth * 3 || height * 12 < scrollHeight) return false
        if (height * 4 > scrollHeight * 3) return false
        return true
    }

    /** Drop matches whose bounds fully contain another match (aggregated parents). */
    private fun collapseNested(matches: List<Pair<Bounds, String>>): List<Pair<Bounds, String>> {
        val distinct = matches.distinctBy { (bounds, _) -> bounds }
        return distinct.filterNot { (outer, _) ->
            distinct.any { (inner, _) -> inner !== outer && contains(outer, inner) }
        }
    }

    private fun contains(outer: Bounds, inner: Bounds): Boolean =
        outer.left <= inner.left && outer.top <= inner.top &&
            outer.right >= inner.right && outer.bottom >= inner.bottom

    // -------------------------------------------------------------------------
    // Wrong-card defenses (2026-09-16 incident: a post-scroll card match kept
    // stale bounds, the tap opened a DIFFERENT product's detail page and the
    // gated delete ran against the wrong object). Two pure, JVM-testable
    // guards back the maintenance v2 path: bounds freshness before the tap and
    // detail-page title verification after it.
    // -------------------------------------------------------------------------

    /** Chebyshev px tolerance for the pre-tap bounds freshness recheck. */
    const val BOUNDS_FRESHNESS_TOLERANCE_PX = 40

    /** Max re-match rounds when consecutive live readings keep disagreeing. */
    const val BOUNDS_FRESHNESS_REMATCH_ROUNDS = 2

    /** True when every edge of [a] and [b] sits within [tolerancePx] pixels. */
    fun boundsWithinTolerance(a: Bounds, b: Bounds, tolerancePx: Int = BOUNDS_FRESHNESS_TOLERANCE_PX): Boolean =
        maxOf(
            kotlin.math.abs(a.left - b.left),
            kotlin.math.abs(a.top - b.top),
            kotlin.math.abs(a.right - b.right),
            kotlin.math.abs(a.bottom - b.bottom),
        ) <= tolerancePx

    /**
     * Secondary defense — pre-tap bounds freshness arbiter. The caller seeds
     * the bounds captured at match time, then feeds each fresh re-query of the
     * SAME title (a full re-locate, not a node-handle refresh). Two agreeing
     * readings prove the rectangle is live; a drifted reading adopts the fresh
     * bounds and forces a re-match; after [maxRematches] re-matches the
     * rectangle is unstable and the caller must fail closed
     * (CARD_BOUNDS_UNSTABLE) instead of tapping a guess.
     */
    class BoundsFreshnessArbiter(
        matched: Bounds,
        private val tolerancePx: Int = BOUNDS_FRESHNESS_TOLERANCE_PX,
        private val maxRematches: Int = BOUNDS_FRESHNESS_REMATCH_ROUNDS,
    ) {
        private var reference = matched
        private var rematches = 0

        fun requery(fresh: Bounds): FreshnessDecision {
            if (boundsWithinTolerance(reference, fresh, tolerancePx)) {
                return FreshnessDecision.Stable(fresh)
            }
            rematches += 1
            if (rematches > maxRematches) return FreshnessDecision.Unstable
            reference = fresh
            return FreshnessDecision.Rematch
        }
    }

    sealed interface FreshnessDecision {
        /** Two agreeing live readings: tap [bounds] (the fresh one). */
        data class Stable(val bounds: Bounds) : FreshnessDecision

        /** Reading drifted: adopt it and re-match once more. */
        data object Rematch : FreshnessDecision

        /** Still drifting after the re-match budget: never tap. */
        data object Unstable : FreshnessDecision
    }

    /**
     * Main defense — detail-page title verdict with the same-source
     * `contains` semantics as the card search: the just-opened detail page is
     * the right product only when one of its visible lines carries the target
     * fragment. No readable content yet means the page is still rendering
     * (poll again); readable content without the fragment means the WRONG
     * product is open — fail closed with the actual line for the log.
     */
    sealed interface DetailTitleVerdict {
        data class Matched(val line: String) : DetailTitleVerdict
        data class Mismatch(val expected: String, val actual: String?) : DetailTitleVerdict
        data object NoReadableContent : DetailTitleVerdict
    }

    fun verifyDetailTitle(titleContains: String, visibleLines: List<String>): DetailTitleVerdict {
        visibleLines.firstOrNull { it.contains(titleContains) }?.let { return DetailTitleVerdict.Matched(it) }
        if (visibleLines.isEmpty()) return DetailTitleVerdict.NoReadableContent
        // The actual line is operator log material, not a control signal: the
        // longest visible line is the most title-shaped line on a detail page.
        return DetailTitleVerdict.Mismatch(titleContains, visibleLines.maxByOrNull { it.length })
    }

    /**
     * The visible page's own text/content-desc lines in tree order, from the
     * same UiNode snapshot model as the card search. Invisible branches are
     * pruned: a covered-but-attached list page must never leak its card titles
     * into the detail-page verdict.
     */
    fun visibleLines(root: UiNode): List<String> {
        val out = mutableListOf<String>()
        fun visit(node: UiNode) {
            if (!node.visible) return
            val text = node.text?.trim()?.takeIf { it.isNotBlank() }
            val description = node.description?.trim()?.takeIf { it.isNotBlank() }
            when {
                text != null && description != null && text == description -> out += text
                else -> {
                    text?.let(out::add)
                    description?.let(out::add)
                }
            }
            node.children.forEach(::visit)
        }
        visit(root)
        return out
    }
}
