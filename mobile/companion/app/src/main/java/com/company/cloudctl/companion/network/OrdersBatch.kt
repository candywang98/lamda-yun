package com.company.cloudctl.companion.network

import com.company.cloudctl.companion.automation.OrderRowSnapshot
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/**
 * order-sync/20260915.1 §3: request/response helpers for
 * POST /companion/v2/orders/batch. Pure functions so the payload shape and
 * response handling stay unit-testable without a pinned HTTPS stack
 * (same pattern as buildClaimedTaskPayload).
 */
internal data class OrdersBatchResult(val accepted: Int, val duplicates: Int)

/** Builds the §3 batch body; the batch must carry 1..20 rows (maxRows ≤ 10 keeps one batch sufficient). */
internal fun buildOrdersBatchPayload(rows: List<OrderRowSnapshot>, collectedAt: Instant): JSONObject {
    require(rows.size in 1..20) { "Orders batch must carry 1..20 rows" }
    val orders = JSONArray()
    rows.forEach { row ->
        val item = JSONObject()
            .put("direction", row.direction.name)
            .put("order_key", row.orderKey.trim().take(128))
        row.itemTitle?.trim()?.takeIf { it.isNotBlank() }?.let { item.put("item_title", it.take(512)) }
        row.buyerName?.trim()?.takeIf { it.isNotBlank() }?.let { item.put("buyer_name", it.take(128)) }
        row.amountCents?.takeIf { it > 0 }?.let { item.put("amount_cents", it) }
        row.statusText?.trim()?.takeIf { it.isNotBlank() }?.let { item.put("status_text", it.take(64)) }
        row.occurredAt?.takeIf { it.isNotBlank() }?.let { item.put("occurred_at", it) }
        if (row.rawLines.isNotEmpty()) item.put("raw", JSONObject().put("lines", JSONArray(row.rawLines)))
        orders.put(item)
    }
    return JSONObject()
        .put("orders", orders)
        .put("collected_at", collectedAt.toString())
}

/** Parses the 201/200 {"accepted", "duplicates"} body; both counters are required. */
internal fun parseOrdersBatchResponse(body: JSONObject): OrdersBatchResult =
    OrdersBatchResult(
        accepted = body.getInt("accepted"),
        duplicates = body.getInt("duplicates"),
    )
