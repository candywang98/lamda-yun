package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * O10 验收用例（Android 侧）——分页三件套防无限滚动：
 * 空页即停、连续停滞即停、超屏数上限即停；游标编码 fail-closed。
 */
class OrderPaginationTest {
    private fun summary(
        screen: Int,
        newKeys: Int,
        empty: Boolean = false,
        updatedKeys: Int = 0,
    ): OrderPageSummary = OrderPageSummary(
        screen = screen,
        rowsSeen = newKeys + 1,
        newKeys = newKeys,
        updatedKeys = updatedKeys,
        overlap = 1,
        skipped = 0,
        partiallyVisible = 0,
        empty = empty,
        collectedAt = "2026-09-15T10:0$screen:00+08:00",
    )

    @Test
    fun emptyPageStopsTheScrollImmediately() {
        val history = listOf(summary(1, 3), summary(2, 2), summary(3, 0, empty = true))
        val decision = OrderScrollPolicy.decide(history, nextScreen = 4)
        val stop = assertIs<OrderScrollDecision.Stop>(decision)
        assertEquals(OrderScrollDecision.REASON_EMPTY_PAGE, stop.reason)
    }

    @Test
    fun stagnantPagesStopTheScrollBeforeInfiniteLooping() {
        // 屏 1 有新键，屏 2/3 都非空但零新键（列表没前进）→ 停。
        val history = listOf(summary(1, 3), summary(2, 0), summary(3, 0))
        val decision = OrderScrollPolicy.decide(history, nextScreen = 4)
        val stop = assertIs<OrderScrollDecision.Stop>(decision)
        assertEquals(OrderScrollDecision.REASON_STAGNANT, stop.reason)
    }

    @Test
    fun singleOverlapPageStillAllowsOneMoreScreen() {
        // 只有 1 屏停滞（惯性重叠）→ 还允许再读一屏。
        val history = listOf(summary(1, 3), summary(2, 0))
        assertIs<OrderScrollDecision.Continue>(OrderScrollPolicy.decide(history, nextScreen = 3))
    }

    @Test
    fun screenCapStopsEvenWhenPagesKeepYieldingKeys() {
        // 每屏都有新键也不能超过 MAX_SCREENS（与后端 v2 冻结上限一致）。
        val history = listOf(summary(1, 3), summary(2, 3), summary(3, 3))
        val decision = OrderScrollPolicy.decide(history, nextScreen = 4)
        val stop = assertIs<OrderScrollDecision.Stop>(decision)
        assertEquals(OrderScrollDecision.REASON_MAX_SCREENS, stop.reason)
    }

    @Test
    fun emptyPageWinsOverStagnancyOrder() {
        // 空页 + 停滞同时成立时报空页（到底），语义更准确。
        val history = listOf(summary(1, 3), summary(2, 0, empty = true))
        val decision = OrderScrollPolicy.decide(history, nextScreen = 3)
        val stop = assertIs<OrderScrollDecision.Stop>(decision)
        assertEquals(OrderScrollDecision.REASON_EMPTY_PAGE, stop.reason)
    }

    @Test
    fun pageSummaryCarriesAllCounters() {
        val registry = OrderSeenRegistry()
        val page = registry.absorbPage(
            2,
            listOf(
                OrderRowSnapshot(OrderDirection.SOLD, "SOLD|买家A|闲置键盘|2500"),
                OrderRowSnapshot(OrderDirection.SOLD, "SOLD|买家B|闲置鼠标|3000"),
            ),
        )
        val s = page.toSummary(collectedAt = "2026-09-15T10:02:00+08:00")
        assertEquals(2, s.screen)
        assertEquals(2, s.rowsSeen)
        assertEquals(2, s.newKeys)
        assertEquals(0, s.updatedKeys)
        assertEquals(0, s.overlap)
        assertEquals(false, s.empty)
        assertEquals("2026-09-15T10:02:00+08:00", s.collectedAt)
    }

    @Test
    fun cursorEncodesAndDecodesRoundTrip() {
        val page = OrderPageReading(
            screen = 2,
            newRows = listOf(
                OrderRowSnapshot(OrderDirection.SOLD, "SOLD|买家A|闲置键盘|2500"),
                OrderRowSnapshot(OrderDirection.SOLD, "SOLD|买家B|闲置鼠标|3000"),
                OrderRowSnapshot(OrderDirection.SOLD, "SOLD|买家C|闲置屏幕|4000"),
                OrderRowSnapshot(OrderDirection.SOLD, "SOLD|买家D|闲置线缆|5000"),
            ),
            updatedRows = emptyList(),
            overlapCount = 1,
            skippedRows = emptyList(),
            partiallyVisibleRows = 0,
            empty = false,
        )
        val cursor = OrderPageCursor.of("run-20260917-a", OrderDirection.SOLD, page)
        // 锚点截断到 3 个。
        assertEquals(3, cursor.anchorKeys.size)
        assertEquals(listOf("SOLD|买家A|闲置键盘|2500", "SOLD|买家B|闲置鼠标|3000", "SOLD|买家C|闲置屏幕|4000"), cursor.anchorKeys)
        val decoded = OrderPageCursor.decode(cursor.encode())
        assertEquals(cursor, decoded)
    }

    @Test
    fun cursorDecodeFailsClosedOnGarbage() {
        assertNull(OrderPageCursor.decode(""))
        assertNull(OrderPageCursor.decode("not-base64!!"))
        // 格式标记不对。
        assertNull(OrderPageCursor.decode(encodeControlSeparated("otherfmt", "run", "SOLD", "1", "")))
        // 屏号越界 / 非数字 / 方向非法。
        assertNull(OrderPageCursor.decode(encodeControlSeparated(OrderPageCursor.FORMAT, "run", "SOLD", "9", "")))
        assertNull(OrderPageCursor.decode(encodeControlSeparated(OrderPageCursor.FORMAT, "run", "SOLD", "zero", "")))
        assertNull(OrderPageCursor.decode(encodeControlSeparated(OrderPageCursor.FORMAT, "run", "REFUNDED", "1", "")))
    }

    @Test
    fun compositeKeysWithSeparatorCharactersSurviveEncoding() {
        // 复合键自带 | 和中文，编码必须无损。
        val cursor = OrderPageCursor(
            runKey = "run|键",
            direction = OrderDirection.BOUGHT,
            lastScreen = 3,
            anchorKeys = listOf("BOUGHT|卖家甲|《复杂|标题》|12500", "BOUGHT|卖家乙|闲置|物品|300"),
        )
        val decoded = OrderPageCursor.decode(cursor.encode())
        assertEquals(cursor, decoded)
        assertTrue(decoded!!.anchorKeys.first().contains("《复杂|标题》"))
    }
}
