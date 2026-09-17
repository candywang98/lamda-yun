package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import com.company.cloudctl.companion.automation.SkippedOrderRow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * O10 验收用例（Android 侧）——去重与降级标记：
 * 跨页重复、置顶订单、断网重传同页重放 → 不重复计数；缺 ID 降级 MISSING_ID、
 * 不拼凑假 ID；状态变化 upsert；部分可见行计数。
 */
class OrderDedupeTest {
    private val direction = OrderDirection.SOLD

    private fun snapshot(
        key: String,
        status: String? = "交易成功",
        title: String? = "闲置键盘",
        buyer: String? = "买家A",
        amount: Long? = 2500,
        occurred: String? = "2026-09-15T10:00:00+08:00",
        rawLines: List<String> = listOf("$buyer", "$title", "¥2500"),
    ): OrderRowSnapshot = OrderRowSnapshot(
        direction = direction,
        orderKey = key,
        itemTitle = title,
        buyerName = buyer,
        amountCents = amount,
        statusText = status,
        occurredAt = occurred,
        rawLines = rawLines,
    )

    @Test
    fun crossPageDuplicatesAreAbsorbedWithoutDoubleCounting() {
        val registry = OrderSeenRegistry()
        val page1 = registry.absorbPage(
            1,
            listOf(snapshot("SOLD|买家A|闲置键盘|2500"), snapshot("SOLD|买家B|闲置鼠标|3000")),
        )
        val page2 = registry.absorbPage(
            2,
            listOf(snapshot("SOLD|买家B|闲置鼠标|3000"), snapshot("SOLD|买家C|闲置屏幕|4000")),
        )
        assertEquals(listOf("SOLD|买家A|闲置键盘|2500", "SOLD|买家B|闲置鼠标|3000"), page1.newRows.map { it.orderKey })
        // 跨页重复（滚动惯性重叠）：B 重现被吸收，只有 C 是新键。
        assertEquals(listOf("SOLD|买家C|闲置屏幕|4000"), page2.newRows.map { it.orderKey })
        assertEquals(1, page2.overlapCount)
        assertEquals(3, registry.size)
    }

    @Test
    fun pinnedOrderReappearingOnEveryPageCountsOnce() {
        val registry = OrderSeenRegistry()
        val pinned = snapshot("SOLD|置顶卖家|置顶商品|9900")
        registry.absorbPage(1, listOf(pinned, snapshot("SOLD|买家A|闲置键盘|2500")))
        val page2 = registry.absorbPage(2, listOf(pinned, snapshot("SOLD|买家B|闲置鼠标|3000")))
        val page3 = registry.absorbPage(3, listOf(pinned))
        // 置顶订单每页重现：只在第 1 屏计一次；第 2 屏的新键是买家B，置顶行是重叠。
        assertEquals(1, page2.overlapCount)
        assertEquals(listOf("SOLD|买家B|闲置鼠标|3000"), page2.newRows.map { it.orderKey })
        assertEquals(1, page3.overlapCount)
        assertEquals(0, page3.newRows.size)
        assertEquals(3, registry.size)
    }

    @Test
    fun offlineReplayOfTheSamePageProducesNoNewKeys() {
        val registry = OrderSeenRegistry()
        val rows = listOf(snapshot("SOLD|买家A|闲置键盘|2500"), snapshot("SOLD|买家B|闲置鼠标|3000"))
        val first = registry.absorbPage(2, rows)
        // 断网重传：同一屏原样再放一遍 → 全部重叠，不重复计数。
        val replay = registry.absorbPage(2, rows)
        assertEquals(2, first.newRows.size)
        assertEquals(0, replay.newRows.size)
        assertEquals(2, replay.overlapCount)
        assertEquals(0, replay.updatedRows.size)
        assertEquals(2, registry.size)
    }

    @Test
    fun missingIdDegradesWithMarkerAndNeverFabricatesAnId() {
        val registry = OrderSeenRegistry()
        val key = registry.dedupeKeyOf(snapshot("SOLD|买家A|闲置键盘|2500"))
        // 列表页勘测事实：无平台订单号 → 降级标记 MISSING_ID，键值就是复合键本身。
        assertEquals(OrderDedupe.MARKER_MISSING_ID, key.marker)
        assertEquals("SOLD|买家A|闲置键盘|2500", key.value)
        // 不拼凑假 ID：普通行文本里提不出真实订单号。
        assertEquals(null, OrderDedupe.realOrderId(listOf("买家A", "闲置键盘", "¥25.00", "2026-09-15")))
        assertEquals(null, OrderDedupe.realOrderId(listOf("1234567890"))) // 太短，宁缺勿假
    }

    @Test
    fun realVisibleOrderIdWinsOverCompositeKey() {
        val registry = OrderSeenRegistry()
        val detailRow = snapshot(
            key = "SOLD|买家A|闲置键盘|2500",
            rawLines = listOf("订单编号", "371234567890123456"),
        )
        val key = registry.dedupeKeyOf(detailRow)
        // 真实可见订单号（15..24 位整段数字）→ REAL_ID，键值就是订单号本身。
        assertEquals(OrderDedupe.MARKER_REAL_ID, key.marker)
        assertEquals("371234567890123456", key.value)
        assertEquals("371234567890123456", OrderDedupe.realOrderId(listOf("371234567890123456")))
        // markerFor 与 realOrderId 口径一致。
        assertEquals(OrderDedupe.MARKER_REAL_ID, OrderDedupe.markerFor("371234567890123456"))
        assertEquals(OrderDedupe.MARKER_MISSING_ID, OrderDedupe.markerFor("SOLD|买家A|闲置键盘|2500"))
    }

    @Test
    fun statusChangeUpsertsMergedSnapshot() {
        val registry = OrderSeenRegistry()
        registry.absorbPage(1, listOf(snapshot("SOLD|买家A|闲置键盘|2500", status = "待发货")))
        // 同键状态变化 → Updated，合并后的快照持有新状态。
        val page2 = registry.absorbPage(2, listOf(snapshot("SOLD|买家A|闲置键盘|2500", status = "已发货")))
        assertEquals(1, page2.updatedRows.size)
        assertEquals("已发货", page2.updatedRows.single().statusText)
        // upsert 后再次同状态重放 → 纯重复。
        val page3 = registry.absorbPage(3, listOf(snapshot("SOLD|买家A|闲置键盘|2500", status = "已发货")))
        assertEquals(0, page3.updatedRows.size)
        assertEquals(1, page3.overlapCount)
    }

    @Test
    fun upsertFillsPreviouslyMissingFields() {
        val registry = OrderSeenRegistry()
        // 第 1 屏只读到金额（部分渲染）：标题/买家缺失。
        registry.absorbPage(1, listOf(snapshot("SOLD|||2500", title = null, buyer = null)))
        // 第 2 屏完整重现：补齐字段属于 upsert，不是纯重复。
        val page2 = registry.absorbPage(2, listOf(snapshot("SOLD|||2500")))
        assertEquals(1, page2.updatedRows.size)
        val merged = registry.snapshots().single()
        assertEquals("闲置键盘", merged.itemTitle)
        assertEquals("买家A", merged.buyerName)
    }

    @Test
    fun partiallyVisibleRowsAreCountedButKeptAsObservedFacts() {
        val registry = OrderSeenRegistry()
        val partial = snapshot("SOLD|||1800", title = null, buyer = null)
        val full = snapshot("SOLD|买家B|闲置鼠标|3000")
        val page = registry.absorbPage(1, listOf(partial, full))
        // 部分可见行（昵称标题都缺）计数，但行本身照常吸收上报（宁缺勿假 ≠ 丢弃观测事实）。
        assertEquals(1, page.partiallyVisibleRows)
        assertEquals(2, page.newRows.size)
        assertTrue(full !in page.updatedRows)
    }

    @Test
    fun emptyPageAndSkippedRowsShapeTheReading() {
        val registry = OrderSeenRegistry()
        val empty = registry.absorbPage(1, emptyList())
        assertTrue(empty.empty)
        assertEquals(0, empty.overlapCount)
        val skippedOnly = registry.absorbPage(2, emptyList(), skipped = listOf(SkippedOrderRow(0, "NO_KEY")))
        // 只有跳过行的屏不算空页（页面有内容，只是解析不了）。
        assertEquals(false, skippedOnly.empty)
        assertEquals(1, skippedOnly.skippedRows.size)
    }
}
