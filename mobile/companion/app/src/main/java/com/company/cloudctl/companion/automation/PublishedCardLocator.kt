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
        for (scrollable in scrollables) {
            for (child in scrollable.children) {
                collectMatches(child, emptyList(), cardAreaTop, titleContains, matches)
            }
        }
        val distinct = collapseNested(matches)
        return when (distinct.size) {
            0 -> Outcome.NotFound
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
        cardAreaTop: Int,
        titleContains: String,
        out: MutableList<Pair<Bounds, String>>,
    ) {
        val line = node.text?.takeIf { it.contains(titleContains) }
            ?: node.description?.takeIf { it.contains(titleContains) }
        if (line != null) {
            val rect = (listOf(node) + ancestors)
                .firstOrNull { it.visible && it.bounds.top >= cardAreaTop }
                ?.bounds
            if (rect != null) out += rect to line
        }
        for (child in node.children) {
            collectMatches(child, listOf(node) + ancestors, cardAreaTop, titleContains, out)
        }
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
}
