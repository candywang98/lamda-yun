package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * O10 验收用例（Android 侧）——历史切片：
 * 采集窗口（起止）+ 缺失页标注；断网重传同屏合并不重复计数；空页/部分可见如实标注。
 */
class OrderHistoryWindowTest {
    private fun summary(
        screen: Int,
        newKeys: Int = 1,
        empty: Boolean = false,
        partial: Int = 0,
        collectedAt: String = "2026-09-15T10:0$screen:00+08:00",
    ): OrderPageSummary = OrderPageSummary(
        screen = screen,
        rowsSeen = newKeys,
        newKeys = newKeys,
        updatedKeys = 0,
        overlap = 0,
        skipped = 0,
        partiallyVisible = partial,
        empty = empty,
        collectedAt = collectedAt,
    )

    @Test
    fun fullCoverageWindowHasNoMissingScreens() {
        val window = OrderHistoryWindow.of(
            "run-1",
            OrderDirection.SOLD,
            listOf(summary(1, 3), summary(2, 2), summary(3, 1, partial = 1)),
        )
        assertEquals(listOf(1, 2, 3), window.screensPresent)
        assertTrue(window.missingScreens.isEmpty())
        assertEquals("2026-09-15T10:01:00+08:00", window.startedAt)
        assertEquals("2026-09-15T10:03:00+08:00", window.endedAt)
        assertEquals(6, window.totalNewKeys)
        assertEquals(listOf(3), window.partialScreens)
        val text = OrderHistoryWindow.annotate(window)
        assertTrue(text.contains("已采第 1、2、3 屏"))
        assertTrue(text.contains("新增 6 键"))
        assertTrue(text.contains("部分可见行"))
        assertTrue(text.contains("窗口 2026-09-15T10:01:00+08:00 ~ 2026-09-15T10:03:00+08:00"))
        assertTrue(!text.contains("缺失"))
    }

    @Test
    fun gapInScreenOrdinalsIsReportedAsMissingPages() {
        // 屏 1 之后直接是屏 3（第 2 屏断网丢了）：缺失页必须标注，不能默默当全集。
        val window = OrderHistoryWindow.of(
            "run-2",
            OrderDirection.BOUGHT,
            listOf(summary(1, 2), summary(3, 1)),
        )
        assertEquals(listOf(2), window.missingScreens)
        val text = OrderHistoryWindow.annotate(window)
        assertTrue(text.contains("缺失第 2 屏"))
    }

    @Test
    fun offlineReplayMergesSameScreenWithoutDoubleCounting() {
        val firstAttempt = summary(2, 2)
        val replay = summary(2, 2)
        val window = OrderHistoryWindow.of(
            "run-3",
            OrderDirection.SOLD,
            listOf(summary(1, 3), firstAttempt, replay),
        )
        // 同屏重传只算一屏、键不重复计。
        assertEquals(listOf(1, 2), window.screensPresent)
        assertEquals(5, window.totalNewKeys)
        assertTrue(window.missingScreens.isEmpty())
    }

    @Test
    fun emptyScreenIsTerminalAndAnnotated() {
        val window = OrderHistoryWindow.of(
            "run-4",
            OrderDirection.SOLD,
            listOf(summary(1, 2), summary(2, 0, empty = true)),
        )
        assertEquals(listOf(2), window.emptyScreens)
        assertTrue(OrderHistoryWindow.annotate(window).contains("第 2 屏为空页"))
    }

    @Test
    fun emptyRunAndMissingTimestampsAreHonest() {
        val empty = OrderHistoryWindow.of("run-5", OrderDirection.SOLD, emptyList())
        assertEquals(0, empty.screensPresent.size)
        assertEquals(null, empty.startedAt)
        assertTrue(OrderHistoryWindow.annotate(empty).contains("已采 0 屏"))
        assertTrue(OrderHistoryWindow.annotate(empty).contains("窗口时间缺失"))
        // collectedAt 空文本 = 时间未知，不伪造。
        val noTime = OrderHistoryWindow.of(
            "run-6",
            OrderDirection.SOLD,
            listOf(summary(1, 1, collectedAt = "")),
        )
        assertEquals(null, noTime.startedAt)
        assertTrue(OrderHistoryWindow.annotate(noTime).contains("窗口时间缺失"))
    }
}
