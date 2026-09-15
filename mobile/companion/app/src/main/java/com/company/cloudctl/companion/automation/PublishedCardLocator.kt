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
        val matches = mutableListOf<Pair<Bounds, String>>()
        for (scrollable in scrollables) {
            for (child in scrollable.children) {
                val line = firstMatchingLine(child, titleContains) ?: continue
                if (!child.visible || child.bounds.top < cardAreaTop) continue
                matches += child.bounds to line
            }
        }
        val distinct = matches.distinctBy { (bounds, _) -> bounds }
        return when (distinct.size) {
            0 -> Outcome.NotFound
            1 -> Outcome.Card(distinct.single().first, distinct.single().second)
            else -> Outcome.Ambiguous(distinct.size, distinct.map { it.second })
        }
    }

    /** First own text/desc line in the subtree that contains the fragment, or null. */
    private fun firstMatchingLine(node: UiNode, titleContains: String): String? {
        node.text?.let { if (it.contains(titleContains)) return it }
        node.description?.let { if (it.contains(titleContains)) return it }
        for (child in node.children) {
            firstMatchingLine(child, titleContains)?.let { return it }
        }
        return null
    }
}
