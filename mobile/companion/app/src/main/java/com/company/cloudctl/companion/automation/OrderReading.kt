package com.company.cloudctl.companion.automation

/**
 * Order-sync slice 1 (contract order-sync/20260915.1 §5/§7 + parsing addendum
 * order-sync/20260915.2, calibrated against the controller's on-device dumps
 * /tmp/recon-ref/08-sold-orders-ui.xml and 09-bought-orders-ui.xml, OnePlus 9R).
 *
 * One collected order row: the parsed snapshot the batch endpoint carries
 * (§3) plus the raw line material it came from. All fields except [orderKey]
 * are best-effort snapshots — the backend keeps them nullable.
 */
data class OrderRowSnapshot(
    val direction: OrderDirection,
    val orderKey: String,
    val itemTitle: String? = null,
    val buyerName: String? = null,
    val amountCents: Long? = null,
    val statusText: String? = null,
    val occurredAt: String? = null,
    val rawLines: List<String> = emptyList(),
)

/** A row the collector read but refused to turn into an order (never a task failure). */
data class SkippedOrderRow(val rowIndex: Int, val reason: String)

/** Outcome of parsing one raw row: either a keyed snapshot candidate or a skip reason. */
sealed interface OrderRowParseOutcome {
    data class Parsed(
        val orderKey: String,
        val itemTitle: String?,
        val buyerName: String?,
        val amountCents: Long?,
        val statusText: String?,
        val occurredAt: String?,
    ) : OrderRowParseOutcome

    data class Skipped(val reason: String) : OrderRowParseOutcome
}

/**
 * Parses one order row from its ordered text/content-desc lines.
 *
 * Surveyed facts encoded here (dumps 08/09, recon-20260915-2):
 * - the list page exposes NO platform order number (no long digit strings, no
 *   resource-ids), so order_key is the controller-ruled composite natural key
 *   `{direction}|{对手昵称}|{商品标题}|{amount_cents}` — every segment strips
 *   \u200b and outer whitespace first, the title segment caps at 64 chars and
 *   the whole key caps at 128;
 * - a row node's own content-desc starts with 「订单信息」 and carries service
 *   tags (退货运费险|好评|…|10分钟发货|描述不符全额退) — structural, never data;
 * - value nodes duplicate their payload as 「X, X」 inside content-desc
 *   (RUSHANG, RUSHANG / 交易成功, 交易成功) — mirrored halves collapse to X;
 * - first block = counterparty nickname (buyer on SOLD, seller on BOUGHT),
 *   status original on its right (交易成功 / 交易关闭，有退款 / 等待见面交易);
 *   second block = item title;
 * - the price sits at the right as several clickable Buttons chopped by
 *   U+200B: '¥\u200b' + '1\u200b0\u200b' + '.\u200b8\u200b0\u200b' — fragments
 *   concatenate after removing all \u200b/whitespace, the ¥ prefix drops and
 *   the decimal string converts to cents ("10.80" → 1080);
 * - rows also carry action buttons (「…，按钮」) and questionnaire prompts
 *   (满意度/满意吗/值不值/表态/评价让…) that are never field data;
 * - the SOLD page's 「横幅通知」 banner is outside the row container and the
 *   parser must not depend on its presence or absence;
 * - a row reaches NO_KEY (skipped, not a failure) only when nickname, title
 *   AND amount are all missing; partially missing rows keep empty segments.
 *
 * Known limitation (ruled acceptable for slice 1): same counterparty + same
 * title + same price collapses into one deduped order; slice 2 upgrades to
 * the real order number from the order-detail page.
 */
object OrderRowParser {
    const val REASON_NO_KEY = "NO_KEY"

    /** 20260915.2: a list row is a direct child whose content-desc starts with this marker. */
    const val ROW_MARKER_PREFIX = "订单信息"

    // Surveyed row-desc service tags (recon-20260915-2); never field data.
    private val STRUCTURAL_TAGS = setOf("退货运费险", "好评", "中评", "差评", "10分钟发货", "描述不符全额退")

    // A price fragment after cleaning: optional ¥, digits with optional
    // decimal part, a leading-dot cents fragment ('.\u200b8\u200b0\u200b' → '.80')
    // or a bare currency sign ('¥\u200b' → '¥').
    private val PRICE_FRAGMENT = Regex("^[¥￥]?(?:[0-9][0-9,]*(?:\\.[0-9]{0,2})?|\\.[0-9]{1,2})?$")
    private val PRICE_JOINED = Regex("^[0-9]{1,10}(?:\\.[0-9]{1,2})?$")

    // Status originals from the dumps (交易成功 / 交易关闭，有退款 / 等待见面交易)
    // plus the status tabs (待付款/待发货/待收货/待评价/退款中) and common siblings.
    private val STATUS_VOCABULARY = setOf(
        "交易成功", "交易关闭", "交易关闭，有退款", "有退款", "等待见面交易", "退款中", "售后中",
        "待付款", "待发货", "待收货", "待评价", "已发货", "已收货", "已完成", "已关闭", "已取消",
    )

    private val DATE_TIME = Regex("^(20[0-9]{2}-[0-9]{2}-[0-9]{2})(?:\\s([0-9]{2}:[0-9]{2})(?::[0-9]{2})?)?$")

    // Questionnaire prompts embedded in rows (surveyed on both dumps).
    private val QUESTIONNAIRE_HINTS = listOf("满意度", "满意吗", "值不值", "表态", "评价让")

    /** Strips \u200b everywhere plus outer whitespace (segment cleaning, 20260915.2). */
    fun cleanSegment(value: String): String = value.replace("​", "").trim()

    /** Collapses the surveyed mirrored node form 「X, X」 back to X. */
    fun collapseMirrored(line: String): String {
        val separator = line.indexOf(", ")
        if (separator <= 0) return line
        val left = line.substring(0, separator)
        val right = line.substring(separator + 2)
        return if (left == right) left else line
    }

    private fun cleanFragment(value: String): String = value.filterNot { it.isWhitespace() || it == '​' }

    /**
     * Builds the composite natural key:
     * `{direction}|{对手昵称}|{商品标题}|{amount_cents}` — title segment caps
     * at 64, the assembled key caps at 128.
     */
    fun compositeOrderKey(
        direction: OrderDirection,
        nickname: String?,
        itemTitle: String?,
        amountCents: Long?,
    ): String {
        val nick = cleanSegment(nickname.orEmpty())
        val title = cleanSegment(itemTitle.orEmpty()).take(64)
        val amount = amountCents?.toString().orEmpty()
        return "$direction|$nick|$title|$amount".take(128)
    }

    fun parse(direction: OrderDirection, lines: List<String>): OrderRowParseOutcome {
        val cleaned = lines.mapNotNull { raw -> collapseMirrored(cleanSegment(raw)) }
            .filter { cleanFragment(it).isNotEmpty() }
        if (cleaned.isEmpty()) return OrderRowParseOutcome.Skipped(REASON_NO_KEY)

        var statusText: String? = null
        var occurredAt: String? = null
        val priceFragments = mutableListOf<String>()
        val candidates = mutableListOf<String>()
        cleaned.forEach { line ->
            val fragment = cleanFragment(line)
            when {
                line.startsWith(ROW_MARKER_PREFIX) || line in STRUCTURAL_TAGS -> Unit
                line.contains("，按钮") -> Unit
                QUESTIONNAIRE_HINTS.any { line.contains(it) } -> Unit
                statusText == null && line in STATUS_VOCABULARY -> statusText = line
                occurredAt == null && DATE_TIME.matches(line) ->
                    occurredAt = toIsoInstant(DATE_TIME.matchEntire(line)!!)
                PRICE_FRAGMENT.matches(fragment) -> priceFragments += fragment
                else -> candidates += line
            }
        }

        val amountCents = assembleAmountCents(priceFragments)
        // Surveyed layout order: the counterparty nickname block comes before
        // the title block, so the first remaining candidate is the nickname and
        // the longest of the rest is the title.
        val nickname: String?
        val title: String?
        when {
            candidates.isEmpty() -> {
                nickname = null
                title = null
            }
            candidates.size == 1 -> {
                nickname = null
                title = candidates.first()
            }
            else -> {
                nickname = candidates.first()
                title = candidates.drop(1).maxByOrNull { it.length }
            }
        }

        if (nickname.isNullOrEmpty() && title.isNullOrEmpty() && amountCents == null) {
            return OrderRowParseOutcome.Skipped(REASON_NO_KEY)
        }

        return OrderRowParseOutcome.Parsed(
            orderKey = compositeOrderKey(direction, nickname, title, amountCents),
            itemTitle = title?.takeIf { it.isNotBlank() }?.take(512),
            buyerName = nickname?.takeIf { it.isNotBlank() }?.take(128),
            amountCents = amountCents,
            statusText = statusText?.take(64),
            occurredAt = occurredAt,
        )
    }

    /**
     * Concatenates the U+200B-chopped price fragments in line order, drops the
     * ¥ prefix and converts the decimal string to cents ('¥'+'10'+'.80' →
     * "10.80" → 1080). A concatenation that is not a plain decimal price
     * leaves amount null (never a guessed value).
     */
    private fun assembleAmountCents(fragments: List<String>): Long? {
        if (fragments.isEmpty()) return null
        val joined = fragments.joinToString("")
            .dropWhile { it == '¥' || it == '￥' }
            .replace(",", "")
        if (!PRICE_JOINED.matches(joined)) return null
        val cents = runCatching { java.math.BigDecimal(joined).movePointRight(2) }.getOrNull() ?: return null
        return cents.takeIf { it > java.math.BigDecimal.ZERO }
            ?.let { it.longValueExact().takeIf { value -> value in 1..999_999_999L } }
    }

    /** Page dates are device-local (CST); the time part defaults to midnight when absent. */
    private fun toIsoInstant(match: MatchResult): String {
        val date = match.groupValues[1]
        val time = match.groupValues[2].takeIf { it.isNotBlank() } ?: "00:00"
        return "${date}T$time:00+08:00"
    }
}

/**
 * Receives the readOrders collection the moment its step succeeds (§5): the
 * companion calls the §3 batch endpoint immediately after SUCCEEDED; failure
 * codes like LOCATOR_UNVERIFIED never reach this port.
 */
fun interface OrderReporter {
    suspend fun reportOrders(
        taskId: String,
        direction: OrderDirection,
        collected: List<OrderRowSnapshot>,
        skipped: List<SkippedOrderRow>,
    )
}

/** Binds a parser outcome to its direction and raw line material. */
internal fun OrderRowParseOutcome.Parsed.toSnapshot(
    direction: OrderDirection,
    rawLines: List<String>,
): OrderRowSnapshot = OrderRowSnapshot(
    direction = direction,
    orderKey = orderKey,
    itemTitle = itemTitle,
    buyerName = buyerName,
    amountCents = amountCents,
    statusText = statusText,
    occurredAt = occurredAt,
    rawLines = rawLines,
)
