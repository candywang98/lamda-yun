package com.company.cloudctl.companion.automation

/**
 * Listing collection parser (P43/P44, xy-tasks-24; contract
 * listing-collect/20260920.2, calibrated 2026-09-20 against a REAL
 * 「我发布的」 card dump — OnePlus 9R, 186 在卖).
 *
 * Each card surfaces as ONE container content-desc with newline-joined
 * lines (Flutter semantics). Verified real structure:
 *
 * ```
 * 恭喜可托管无忧卖, 托管后预估将在1~3天内卖出   ← 营销前缀（可无）
 * 托管 / 降价 / 编辑 / 诊断                      ← 卡片按钮行
 * 《十万个为什么》个人闲置                       ← 标题
 * 曝光13
 * 浏览2
 * 想要0
 * ¥ / 8 / .88                                    ← 价格拆碎段
 * ```
 *
 * The user-ruled fields 标题/曝光/浏览/想要(+价格) all live on the card —
 * no detail-page entry is ever needed. The card carries NO platform item
 * id, so identity stays the composite natural key `{title}|{price_cents}`
 * (order-sync slice1 cleaning rules; a real 15..24-digit id, if a future
 * card exposes one, keys by itself and is marked REAL_ID server-side).
 *
 * Competitor-calibrated rulings (yuyou decompiled analysis 2026-09-20):
 * - 曝光 counts use the CARD field (never the store-level 今日曝光);
 * - a 「万」 suffix multiplies by 10_000 (曝光1.2万 → 12000);
 * - the accessibility tree occasionally surfaces a CDN image filename as
 *   the title (e.g. `TB1xxx.png_110x10000.jpg_`) — such lines are noise,
 *   never titles (title anti-pollution);
 * - missing stat lines default to 0 (edit_count semantics), and covers are
 *   OUT of scope for the statistics line (no share-link parsing here).
 */
data class ListingRowSnapshot(
    val itemKey: String,
    val title: String? = null,
    val priceCents: Long? = null,
    val priceText: String? = null,
    val statusText: String? = null,
    val exposureCount: Int? = null,
    val viewsCount: Int? = null,
    val wantsCount: Int? = null,
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
        val exposureCount: Int?,
        val viewsCount: Int?,
        val wantsCount: Int?,
    ) : ListingRowParseOutcome

    data class Skipped(val reason: String) : ListingRowParseOutcome
}

object ListingReading {
    /** Whole lines that are card action buttons, never data. */
    private val BUTTON_LINES = setOf("托管", "降价", "编辑", "诊断", "擦亮", "下架", "删除", "留言")

    /** CDN image artifacts the tree may surface in the title slot (anti-pollution). */
    private val IMAGE_ARTIFACT_HINTS = listOf(".png", ".jpg", ".jpeg", ".webp", "http", "O1CN", "TB1")

    private fun looksLikeImageArtifact(line: String): Boolean =
        IMAGE_ARTIFACT_HINTS.any { line.contains(it, ignoreCase = true) }

    /** Marketing prefix lines the card may prepend. */
    private const val MARKETING_PREFIX = "恭喜可托管无忧卖"

    fun cleanSegment(value: String): String = value.replace("​", "").trim()

    fun compositeItemKey(title: String, priceCents: Long?): String {
        val cleanTitle = cleanSegment(title).take(64)
        return "$cleanTitle|${priceCents ?: "?"}".take(128)
    }

    /**
     * Parses one card from its container content-desc (newline-joined) or an
     * ordered line list. Stats are matched by their Chinese label prefix
     * (曝光N/浏览N/想要N), price by ¥-prefixed fragments which concatenate
     * across segments; everything unkeyable is Skipped, never fabricated.
     */
    fun parseCard(contentDesc: String): ListingRowParseOutcome =
        parse(contentDesc.split("\n"))

    fun parse(lines: List<String>): ListingRowParseOutcome {
        val cleaned = lines.map(::cleanSegment).filter { it.isNotEmpty() }
        if (cleaned.isEmpty()) return ListingRowParseOutcome.Skipped("EMPTY_CARD")

        var title: String? = null
        var priceCents: Long? = null
        var priceText: String? = null
        var exposure: Int? = null
        var views: Int? = null
        var wants: Int? = null
        val priceFragments = StringBuilder()

        for (line in cleaned) {
            when {
                line.startsWith(MARKETING_PREFIX) || line in BUTTON_LINES -> Unit
                line.startsWith("曝光") -> exposure = countAfter(line, "曝光")
                line.startsWith("浏览") -> views = countAfter(line, "浏览")
                line.startsWith("想要") -> wants = countAfter(line, "想要")
                line.startsWith("¥") -> priceFragments.append(line.drop(1))
                line.all { it.isDigit() || it == '.' } && line.any { it.isDigit() } &&
                    title != null ->
                    // price continuation segments (18 / .88) after ¥
                    priceFragments.append(line)
                title == null && !looksLikeImageArtifact(line) -> title = line
                // extra title-like lines (subtitle) are ignored, first line wins
            }
        }
        val priceJoined = priceFragments.toString()
        if (priceJoined.isNotEmpty()) {
            priceCents = priceToCents(priceJoined)
            priceText = "¥$priceJoined"
        }

        val finalTitle = title
        if (finalTitle == null) return ListingRowParseOutcome.Skipped("NO_TITLE")
        if (priceCents == null) return ListingRowParseOutcome.Skipped("NO_PRICE")

        return ListingRowParseOutcome.Parsed(
            itemKey = compositeItemKey(finalTitle, priceCents),
            title = finalTitle.take(64),
            priceCents = priceCents,
            priceText = priceText,
            statusText = "在卖",
            // Missing stat lines default to 0 (edit_count semantics).
            exposureCount = exposure ?: 0,
            viewsCount = views ?: 0,
            wantsCount = wants ?: 0,
        )
    }

    private fun countAfter(line: String, label: String): Int? {
        val raw = line.removePrefix(label).trim()
        if (raw.isEmpty()) return null
        // 「万」 suffix multiplies by 10_000 (曝光1.2万 → 12000).
        if (raw.endsWith("万")) {
            return raw.dropLast(1).toDoubleOrNull()?.let { Math.round(it * 10_000).toInt() }
        }
        return raw.take(8).toIntOrNull()
    }

    fun priceToCents(text: String): Long? {
        val digits = text.filter { it.isDigit() || it == '.' }
        if (digits.isEmpty() || digits == ".") return null
        return try {
            val yuan = digits.toDouble()
            if (yuan < 0) null else Math.round(yuan * 100)
        } catch (error: NumberFormatException) {
            null
        }
    }
}
