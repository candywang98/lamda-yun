package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * O10 gold assertions (fleet-first-20260916.1): the screens push body is
 * FROZEN against the backend request model
 * services/control-api/src/cloudctl_api/fleet_orders.py::FleetOrderScreenIn
 * (model_config extra="forbid" — any extra field is a 422):
 *
 *   runKey        str 1..128   (alias run_key)
 *   accountKey    str 1..128   (alias account_key)
 *   schemaVersion int 1..99    (alias schema_version)
 *   screen        int 1..50
 *   direction     "SOLD"|"BOUGHT"
 *   rows          list[OrderIn] <= MAX_BATCH(20), empty allowed (empty page)
 *   partialRows   list[int] <= 50 (alias partial_rows)
 *   collectedAt   str|None <= 64 (alias collected_at)
 *
 * Row items reuse the slice1 /orders/batch OrderIn shape: direction,
 * order_key, item_title?, buyer_name?, amount_cents?, status_text?,
 * occurred_at?, raw? — snake_case exactly as the batch endpoint accepts.
 */
class OrdersScreenPayloadTest {
    @Test
    fun payloadCarriesExactlyTheBackendRequestModelFields() {
        val payload = buildOrdersScreenPayload(
            runKey = "task-xianyu-orders-v2-001",
            accountKey = "account-1",
            schemaVersion = ORDER_SCREENS_SCHEMA_VERSION,
            direction = OrderDirection.SOLD,
            screen = 2,
            rows = listOf(fullRow(), minimalRow()),
            partialRowIndices = listOf(1),
            collectedAt = "2026-09-15T08:00:00Z",
        )

        // Top-level key set frozen against FleetOrderScreenIn (extra=forbid).
        assertEquals(
            setOf("runKey", "accountKey", "schemaVersion", "screen", "direction", "rows", "partialRows", "collectedAt"),
            payload.keys().asSequence().toSet(),
        )
        assertEquals("task-xianyu-orders-v2-001", payload.getString("runKey"))
        assertEquals("account-1", payload.getString("accountKey"))
        assertEquals(1, payload.getInt("schemaVersion"))
        assertEquals(2, payload.getInt("screen"))
        assertEquals("SOLD", payload.getString("direction"))
        assertEquals(1, payload.getJSONArray("partialRows").length())
        assertEquals(1, payload.getJSONArray("partialRows").getInt(0))
        assertEquals("2026-09-15T08:00:00Z", payload.getString("collectedAt"))

        val rows = payload.getJSONArray("rows")
        assertEquals(2, rows.length())

        // Full row: every optional field present, snake_case like the batch.
        val full = rows.getJSONObject(0)
        assertEquals(
            setOf("direction", "order_key", "item_title", "buyer_name", "amount_cents", "status_text", "occurred_at", "raw"),
            full.keys().asSequence().toSet(),
        )
        assertEquals("SOLD", full.getString("direction"))
        assertEquals("SOLD|RUSHANG|书|1080", full.getString("order_key"))
        assertEquals("书", full.getString("item_title"))
        assertEquals("RUSHANG", full.getString("buyer_name"))
        assertEquals(1080L, full.getLong("amount_cents"))
        assertEquals("交易成功", full.getString("status_text"))
        assertEquals("2026-09-01T10:00:00+08:00", full.getString("occurred_at"))
        assertEquals(listOf("行1", "行2"), full.getJSONObject("raw").getJSONArray("lines").let { lines ->
            List(lines.length()) { lines.getString(it) }
        })

        // Minimal row: only the required pair — absent optionals, never nulls.
        val minimal = rows.getJSONObject(1)
        assertEquals(setOf("direction", "order_key"), minimal.keys().asSequence().toSet())
        assertEquals("BOUGHT", minimal.getString("direction"))
        assertEquals("BOUGHT|||250", minimal.getString("order_key"))
    }

    @Test
    fun emptyRowsListStaysLegalForAnEmptyPagePush() {
        // The screens endpoint records empty pages (empty_page flag); unlike
        // the 1..20 batch, zero rows must build and push.
        val payload = buildOrdersScreenPayload(
            runKey = "run-1",
            accountKey = "account-1",
            schemaVersion = 1,
            direction = OrderDirection.BOUGHT,
            screen = 3,
            rows = emptyList(),
            partialRowIndices = emptyList(),
            collectedAt = "2026-09-15T08:00:00Z",
        )
        assertEquals(0, payload.getJSONArray("rows").length())
        assertEquals(0, payload.getJSONArray("partialRows").length())
    }

    @Test
    fun blankOrNullOptionalsAreOmittedRatherThanSentEmpty() {
        val payload = buildOrdersScreenPayload(
            runKey = "run-1",
            accountKey = "account-1",
            schemaVersion = 1,
            direction = OrderDirection.SOLD,
            screen = 1,
            rows = listOf(
                OrderRowSnapshot(
                    direction = OrderDirection.SOLD,
                    orderKey = "  SOLD|x|y|100  ",
                    itemTitle = "   ",
                    buyerName = null,
                    amountCents = 0L, // non-positive amounts are dropped like the batch
                    statusText = null,
                    occurredAt = "",
                    rawLines = emptyList(),
                ),
            ),
            partialRowIndices = emptyList(),
            collectedAt = "2026-09-15T08:00:00Z",
        )
        val row = payload.getJSONArray("rows").getJSONObject(0)
        assertEquals(setOf("direction", "order_key"), row.keys().asSequence().toSet())
        // The order key is trimmed and capped like the batch rows.
        assertEquals("SOLD|x|y|100", row.getString("order_key"))
        assertFalse(row.has("raw"))
    }

    @Test
    fun rejectsBlankIdentityAndOutOfRangeValuesBeforeAnyPush() {
        val args = { runKey: String, accountKey: String, schemaVersion: Int, screen: Int ->
            buildOrdersScreenPayload(
                runKey = runKey,
                accountKey = accountKey,
                schemaVersion = schemaVersion,
                direction = OrderDirection.SOLD,
                screen = screen,
                rows = emptyList(),
                partialRowIndices = emptyList(),
                collectedAt = "2026-09-15T08:00:00Z",
            )
        }
        assertFailsWith<IllegalArgumentException> { args("", "account-1", 1, 1) }
        assertFailsWith<IllegalArgumentException> { args("run-1", "", 1, 1) }
        assertFailsWith<IllegalArgumentException> { args("run-1", "account-1", 0, 1) }
        assertFailsWith<IllegalArgumentException> { args("run-1", "account-1", 100, 1) }
        assertFailsWith<IllegalArgumentException> { args("run-1", "account-1", 1, 0) }
        assertFailsWith<IllegalArgumentException> { args("run-1", "account-1", 1, 51) }
    }

    private fun fullRow() = OrderRowSnapshot(
        direction = OrderDirection.SOLD,
        orderKey = "SOLD|RUSHANG|书|1080",
        itemTitle = "书",
        buyerName = "RUSHANG",
        amountCents = 1080L,
        statusText = "交易成功",
        occurredAt = "2026-09-01T10:00:00+08:00",
        rawLines = listOf("行1", "行2"),
    )

    private fun minimalRow() = OrderRowSnapshot(
        direction = OrderDirection.BOUGHT,
        orderKey = "BOUGHT|||250",
    )
}
