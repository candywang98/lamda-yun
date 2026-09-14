package com.company.cloudctl.companion.im

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Bubble-reader gap (device acceptance 2026-09-14): the fixed swipe started at
 * (540,1600), inside the IME window once the chat keyboard was open, so the
 * stroke was consumed and the peer's inbound bubbles were never revealed.
 * Strokes must therefore be derived from the scrollable conversation-list node
 * bounds, which compress together with the keyboard.
 */
class ConversationListSwipeTest {
    /** Full-screen list bounds without a keyboard (the [0,0][1080,2352] node). */
    private val fullScreen = ConversationListSwipe.Bounds(left = 0, top = 0, right = 1080, bottom = 2352)

    /** Keyboard-open list bounds: the visible list compresses to roughly y 200-1200. */
    private val keyboardCompressed = ConversationListSwipe.Bounds(left = 0, top = 200, right = 1080, bottom = 1200)

    @Test
    fun `backward drags down inside the list band to reveal older bubbles`() {
        val stroke = ConversationListSwipe.stroke(fullScreen, backward = true)
        // Finger moves down (start above end), on the center-x line.
        assertEquals(540f, stroke.startX, 0.01f)
        assertEquals(540f, stroke.endX, 0.01f)
        assertEquals(fullScreen.top + fullScreen.height * 0.30f, stroke.startY, 0.01f)
        assertEquals(fullScreen.top + fullScreen.height * 0.70f, stroke.endY, 0.01f)
        assertTrue(stroke.startY < stroke.endY, "backward must drag the content down")
    }

    @Test
    fun `forward drags up to return to the newest replies at the bottom`() {
        val stroke = ConversationListSwipe.stroke(fullScreen, backward = false)
        assertEquals(540f, stroke.startX, 0.01f)
        assertEquals(540f, stroke.endX, 0.01f)
        assertEquals(fullScreen.top + fullScreen.height * 0.70f, stroke.startY, 0.01f)
        assertEquals(fullScreen.top + fullScreen.height * 0.30f, stroke.endY, 0.01f)
        assertTrue(stroke.startY > stroke.endY, "forward must drag the content up")
    }

    @Test
    fun `keyboard-compressed bounds keep the whole stroke above the IME region`() {
        val backward = ConversationListSwipe.stroke(keyboardCompressed, backward = true)
        // 200 + 1000*0.3 = 500 start, 200 + 1000*0.7 = 900 end: both inside the
        // visible list (200..1200), far from the old fixed start y=1600 that the
        // IME consumed.
        assertEquals(500f, backward.startY, 0.01f)
        assertEquals(900f, backward.endY, 0.01f)
        assertTrue(backward.startY >= keyboardCompressed.top && backward.endY <= keyboardCompressed.bottom)

        val forward = ConversationListSwipe.stroke(keyboardCompressed, backward = false)
        assertEquals(900f, forward.startY, 0.01f)
        assertEquals(500f, forward.endY, 0.01f)
        assertTrue(forward.startY <= keyboardCompressed.bottom && forward.endY >= keyboardCompressed.top)
    }

    @Test
    fun `missing or degenerate bounds fall back to the legacy fixed pair`() {
        val backward = ConversationListSwipe.stroke(null, backward = true)
        assertEquals(540f, backward.startX, 0.01f)
        assertEquals(700f, backward.startY, 0.01f)
        assertEquals(540f, backward.endX, 0.01f)
        assertEquals(1_600f, backward.endY, 0.01f)

        val forward = ConversationListSwipe.stroke(null, backward = false)
        assertEquals(1_600f, forward.startY, 0.01f)
        assertEquals(700f, forward.endY, 0.01f)

        // Degenerate rectangles (zero or negative extents) must not produce
        // strokes anchored at impossible coordinates.
        val degenerate = ConversationListSwipe.Bounds(left = 10, top = 10, right = 10, bottom = 400)
        assertEquals(
            ConversationListSwipe.stroke(null, backward = true),
            ConversationListSwipe.stroke(degenerate, backward = true),
        )
        val inverted = ConversationListSwipe.Bounds(left = 100, top = 900, right = 50, bottom = 100)
        assertEquals(
            ConversationListSwipe.stroke(null, backward = false),
            ConversationListSwipe.stroke(inverted, backward = false),
        )
    }

    @Test
    fun `strokes follow the list horizontally even when it is not centered`() {
        val offset = ConversationListSwipe.Bounds(left = 60, top = 200, right = 1020, bottom = 1200)
        val stroke = ConversationListSwipe.stroke(offset, backward = true)
        assertEquals((60f + 1020f) / 2f, stroke.startX, 0.01f)
        assertEquals(stroke.startX, stroke.endX, 0.01f)
        assertEquals(500f, stroke.startY, 0.01f)
        assertEquals(900f, stroke.endY, 0.01f)
    }

    @Test
    fun `every stroke stays inside the 30 to 70 percent band of its list`() {
        val cases = listOf(
            fullScreen,
            keyboardCompressed,
            ConversationListSwipe.Bounds(left = 0, top = 312, right = 1080, bottom = 2176),
        )
        for (bounds in cases) {
            for (backward in listOf(true, false)) {
                val stroke = ConversationListSwipe.stroke(bounds, backward = backward)
                val upper = bounds.top + bounds.height * 0.30f
                val lower = bounds.top + bounds.height * 0.70f
                assertTrue(stroke.startY >= upper - 0.01f && stroke.startY <= lower + 0.01f)
                assertTrue(stroke.endY >= upper - 0.01f && stroke.endY <= lower + 0.01f)
                assertTrue(stroke.startX >= bounds.left && stroke.startX <= bounds.right)
            }
        }
    }
}
