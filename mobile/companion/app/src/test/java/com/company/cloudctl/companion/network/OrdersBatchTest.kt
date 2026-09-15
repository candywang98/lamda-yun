package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import org.json.JSONObject
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * order-sync/20260915.1 §3：sendOrders 请求体形状与响应处理
 * （纯函数模式，同 buildClaimedTaskPayload 的测试写法；HTTP 层走既有 pinned transport）。
 */
class OrdersBatchTest {

    @Test
    fun buildsContractShapedBatchPayload() {
        val payload = buildOrdersBatchPayload(
            listOf(
                OrderRowSnapshot(
                    direction = OrderDirection.SOLD,
                    orderKey = "2861547390123456789",
                    itemTitle = "自用九成新相机镜头套装",
                    buyerName = "小鱼干很忙",
                    amountCents = 129_900L,
                    statusText = "已发货",
                    occurredAt = "2026-09-12T14:30:00+08:00",
                    rawLines = listOf("订单号：2861547390123456789", "自用九成新相机镜头套装"),
                ),
                OrderRowSnapshot(
                    direction = OrderDirection.SOLD,
                    orderKey = "1837746589012345670",
                ),
            ),
            collectedAt = Instant.parse("2026-09-15T08:00:00Z"),
        )

        assertEquals("2026-09-15T08:00:00Z", payload.getString("collected_at"))
        val orders = payload.getJSONArray("orders")
        assertEquals(2, orders.length())

        val full = orders.getJSONObject(0)
        assertEquals("SOLD", full.getString("direction"))
        assertEquals("2861547390123456789", full.getString("order_key"))
        assertEquals("自用九成新相机镜头套装", full.getString("item_title"))
        assertEquals("小鱼干很忙", full.getString("buyer_name"))
        assertEquals(129_900L, full.getLong("amount_cents"))
        assertEquals("已发货", full.getString("status_text"))
        assertEquals("2026-09-12T14:30:00+08:00", full.getString("occurred_at"))
        val raw = full.getJSONObject("raw")
        assertEquals("订单号：2861547390123456789", raw.getJSONArray("lines").getString(0))

        // 可空字段缺省时直接省略键（backend 侧按 None 处理）。
        val minimal = orders.getJSONObject(1)
        assertFalse(minimal.has("item_title"))
        assertEquals("1837746589012345670", minimal.getString("order_key"))
        assertFalse(minimal.has("buyer_name"))
        assertFalse(minimal.has("amount_cents"))
        assertFalse(minimal.has("status_text"))
        assertFalse(minimal.has("occurred_at"))
        assertFalse(minimal.has("raw"))
    }

    @Test
    fun enforcesTheOneToTwentyBatchContract() {
        val row = OrderRowSnapshot(direction = OrderDirection.BOUGHT, orderKey = "2861547390123456789")
        assertFailsWith<IllegalArgumentException> { buildOrdersBatchPayload(emptyList(), Instant.now()) }
        assertFailsWith<IllegalArgumentException> { buildOrdersBatchPayload(List(21) { row }, Instant.now()) }
        // maxRows ≤ 10 → 单批足够；20 行边界合法。
        assertEquals(20, buildOrdersBatchPayload(List(20) { row }, Instant.now()).getJSONArray("orders").length())
    }

    @Test
    fun parsesAcceptedAndDuplicatesFromBatchResponses() {
        val created = parseOrdersBatchResponse(JSONObject("""{"accepted": 3, "duplicates": 0}"""))
        assertEquals(3, created.accepted)
        assertEquals(0, created.duplicates)
        val replay = parseOrdersBatchResponse(JSONObject("""{"accepted": 0, "duplicates": 3}"""))
        assertEquals(0, replay.accepted)
        assertEquals(3, replay.duplicates)
        // 计数字段缺失 → 拒绝（不猜 0）。
        assertFailsWith<org.json.JSONException> {
            parseOrdersBatchResponse(JSONObject("""{"accepted": 3}"""))
        }
    }
}
