package com.company.cloudctl.companion.automation

/**
 * Listing collection parser (P43/P44, xy-tasks-24; contract
 * listing-collect/20260920.1).
 *
 * The 「我发布的」 page is a Flutter list with three tabs (在卖 / n草稿 /
 * 已下架 — verified on device 2026-09-20, Huawei P30 Pro dump 06). Like the
 * order list, it exposes NO platform item id at card level, so the listing
 * identity is the controller-ruled composite natural key
 * `{title}|{price_cents}` with the same cleaning rules as order-sync
 * slice 1: strip U+200B and outer whitespace, title caps at 64 chars and
 * the whole key at 128.
 *
 * CALIBRATION WINDOW: card-level line material (title/price fragments,
 * mirrored content-desc halves, status badges) still needs a real dump of
 * a NON-empty 在卖 tab — the only device with live listings (OnePlus 9R)
 * had its Xianyu session expired on 2026-09-20. The row splitter below
 * therefore stays conservative: it consumes the per-card ordered lines the
 * accessibility reader supplies and refuses (as Skipped, never a task
 * failure) anything it cannot key unambiguously.
 */
data class ListingRowSnapshot(
    val itemKey: String,
    val title: String? = null,
    val priceCents: Long? = null,
    val priceText: String? = null,
    val statusText: String? = null,
    val rawLines: List<String> = emptyList(),
)

data class SkippedListingRow(val rowIndex: Int, val reason: String)

sealed interface ListingRowParseOutcome {
    data class Parsed(
        val itemKey: String,
        val title: String?,
        val priceCents: Long?,
        val priceText: String?,
        val statusText: String?,
    ) : ListingRowParseOutcome

    data class Skipped(val reason: String) : ListingRowParseOutcome
}

object ListingReading {
    private val STATUS_HINTS = listOf("在卖", "已下架", "草稿")

    fun cleanSegment(value: String): String = value.replace("​", "").trim()

    fun compositeItemKey(title: String, priceCents: Long?): String {
        val cleanTitle = cleanSegment(title).take(64)
        val key = "$cleanTitle|${priceCents ?: "?"}"
        return key.take(128)
    }

    /**
     * Parses one card from its ordered text/content-desc lines. Recognized
     * shapes (pending full calibration):
     * - price: a ¥-prefixed fragment, possibly chopped by U+200B;
     * - status: one of the known tab/badge words;
     * - title: the longest remaining line that is not price/status noise.
     */
    fun parse(lines: List<String>): ListingRowParseOutcome {
        val cleaned = lines.map(::cleanSegment).filter { it.isNotEmpty() }
        if (cleaned.isEmpty()) return ListingRowParseOutcome.Skipped("EMPTY_CARD")

        val priceText = cleaned.firstOrNull { it.startsWith("¥") }
        val priceCents = priceText?.let(::priceToCents)
        val status = cleaned.firstOrNull { line -> STATUS_HINTS.any { line == it } }
        val title = cleaned
            .filterNot { it == priceText || it == status }
            .filterNot { line -> STATUS_HINTS.any { line == it } }
            .maxByOrNull { it.length }

        if (title.isNullOrEmpty()) return ListingRowParseOutcome.Skipped("NO_TITLE")
        if (priceCents == null) {
            // A price-less card cannot be keyed stably: refuse rather than
            // fabricate a volatile identity.
            return ListingRowParseOutcome.Skipped("NO_PRICE")
        }
        return ListingRowParseOutcome.Parsed(
            itemKey = compositeItemKey(title, priceCents),
            title = title.take(64),
            priceCents = priceCents,
            priceText = priceText,
            statusText = status,
        )
    }

    fun priceToCents(text: String): Long? {
        val digits = text.filter { it.isDigit() || it == '.' }.replace("​", "")
        if (digits.isEmpty() || digits == ".") return null
        return try {
            val yuan = digits.toDouble()
            if (yuan < 0) null else Math.round(yuan * 100)
        } catch (error: NumberFormatException) {
            null
        }
    }
}
