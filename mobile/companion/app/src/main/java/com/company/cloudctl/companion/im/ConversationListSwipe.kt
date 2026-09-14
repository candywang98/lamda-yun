package com.company.cloudctl.companion.im

/**
 * Bubble-reader gap (device acceptance 2026-09-14): the legacy fixed swipe
 * started at (540,1600), which sits inside the IME window once the chat
 * keyboard is open, so the stroke was consumed by the keyboard and the
 * conversation list never scrolled — the peer's inbound bubbles stayed out of
 * the semantics tree (bubbles=17, all our own right-side replies).
 *
 * Strokes are therefore derived from the scrollable conversation-list node
 * bounds: that node compresses together with the keyboard, so a stroke inside
 * its 30%-70% height band on the center-x line always stays within the
 * visible list and can never start on an IME key.
 *
 * Directions follow the drag physics of a chat list resting at the bottom:
 * dragging the finger DOWN pulls older (peer) bubbles into view
 * (backward=true), dragging UP returns to the newest replies at the bottom
 * (backward=false — the start y=top+0.7h / end y=top+0.3h stroke required to
 * make our latest reply visible again). The fixed legacy pair remains only as
 * a fallback when no scrollable node can be resolved.
 */
object ConversationListSwipe {
    /** On-screen rectangle of a node, decoupled from android.graphics.Rect for JVM tests. */
    data class Bounds(
        val left: Int,
        val top: Int,
        val right: Int,
        val bottom: Int,
    ) {
        val width: Int get() = right - left
        val height: Int get() = bottom - top

        fun isValid(): Boolean = width > 0 && height > 0
    }

    data class Stroke(
        val startX: Float,
        val startY: Float,
        val endX: Float,
        val endY: Float,
    )

    /**
     * @param bounds bounds of the visible scrollable conversation-list node,
     *   or null when it could not be resolved (then the legacy fixed pair is used).
     * @param backward true drags older content into view, false returns to the newest.
     */
    fun stroke(bounds: Bounds?, backward: Boolean): Stroke {
        if (bounds == null || !bounds.isValid()) return legacy(backward)
        val centerX = (bounds.left + bounds.right) / 2f
        val upperY = bounds.top + bounds.height * UPPER_BAND
        val lowerY = bounds.top + bounds.height * LOWER_BAND
        return if (backward) {
            Stroke(centerX, upperY, centerX, lowerY)
        } else {
            Stroke(centerX, lowerY, centerX, upperY)
        }
    }

    private fun legacy(backward: Boolean): Stroke = if (backward) {
        Stroke(FALLBACK_X, FALLBACK_UPPER_Y, FALLBACK_X, FALLBACK_LOWER_Y)
    } else {
        Stroke(FALLBACK_X, FALLBACK_LOWER_Y, FALLBACK_X, FALLBACK_UPPER_Y)
    }

    /** Stroke band inside the list bounds: 30% (upper) to 70% (lower) of the height. */
    const val UPPER_BAND = 0.30f
    const val LOWER_BAND = 0.70f

    /** Legacy verified fixed pair (bubble-reader baseline); fallback only. */
    const val FALLBACK_X = 540f
    const val FALLBACK_UPPER_Y = 700f
    const val FALLBACK_LOWER_Y = 1_600f
}
