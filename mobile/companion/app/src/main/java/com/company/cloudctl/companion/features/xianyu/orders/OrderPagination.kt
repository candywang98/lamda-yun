package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection
import java.util.Base64

/**
 * O10 分页三件套（任务卡 §2）：游标 + 已见集合 + 页摘要，防无限滚动。
 *
 * - 游标 [OrderPageCursor]：记录 run 键、方向、已读屏数与最近一页的新键锚点，
 *   供断点续传/断网重传时恢复位置；编码自校验，解不开就 fail-closed 返回 null，
 *   绝不猜测位置。
 * - 已见集合：[OrderSeenRegistry]（OrderDedupe.kt）。
 * - 页摘要 [OrderPageSummary]：每屏一行的采集事实（新键/重叠/空页/部分可见），
 *   是历史窗口（OrderHistoryWindow.kt）与缺失页标注的原料。
 * - [OrderScrollPolicy]：三件套的裁决方——空页即停、连续无新键即停、超上限屏数
 *   即停，任何一条命中都不再发下一屏 swipe。
 */
data class OrderPageSummary(
    val screen: Int,
    val rowsSeen: Int,
    val newKeys: Int,
    val updatedKeys: Int,
    val overlap: Int,
    val skipped: Int,
    val partiallyVisible: Int,
    val empty: Boolean,
    val collectedAt: String,
)

fun OrderPageReading.toSummary(collectedAt: String): OrderPageSummary = OrderPageSummary(
    screen = screen,
    rowsSeen = newRows.size + updatedRows.size + overlapCount + skippedRows.size,
    newKeys = newRows.size,
    updatedKeys = updatedRows.size,
    overlap = overlapCount,
    skipped = skippedRows.size,
    partiallyVisible = partiallyVisibleRows,
    empty = empty,
    collectedAt = collectedAt,
)

/**
 * 滚动继续/停止裁决。reason 是稳定的机器码（日志/上报可直接使用）。
 */
sealed interface OrderScrollDecision {
    data object Continue : OrderScrollDecision

    data class Stop(val reason: String) : OrderScrollDecision

    companion object {
        /** 列表已到底（空页）。 */
        const val REASON_EMPTY_PAGE = "STOP_EMPTY_PAGE"

        /** 连续多屏没有任何新键——滚动没有前进，防无限滚动。 */
        const val REASON_STAGNANT = "STOP_STAGNANT"

        /** 超过最大屏数（对齐后端 ORDERS_MAX_SCREENS）。 */
        const val REASON_MAX_SCREENS = "STOP_MAX_SCREENS"
    }
}

object OrderScrollPolicy {
    /** 与后端 mobile_actions.ORDERS_MAX_SCREENS 冻结值一致（v2 最多 3 屏）。 */
    const val MAX_SCREENS = 3

    /** 连续「非空但零新键」的屏数上限：第 2 屏仍未前进即停（惯性重叠只容忍 1 屏）。 */
    const val MAX_STAGNANT_SCREENS = 2

    /**
     * 决定是否发起下一屏（nextScreen 是即将读取的 1-based 屏号）。
     * 裁决顺序：空页（到底了）→ 停滞（没前进）→ 屏数上限；先报已发生的事实。
     */
    fun decide(history: List<OrderPageSummary>, nextScreen: Int): OrderScrollDecision {
        val last = history.lastOrNull()
        if (last != null) {
            if (last.empty) return OrderScrollDecision.Stop(OrderScrollDecision.REASON_EMPTY_PAGE)
            val trailing = history.asReversed().takeWhile { !it.empty && it.newKeys == 0 && it.updatedKeys == 0 }
            if (trailing.size >= MAX_STAGNANT_SCREENS) {
                return OrderScrollDecision.Stop(OrderScrollDecision.REASON_STAGNANT)
            }
        }
        if (nextScreen > MAX_SCREENS) return OrderScrollDecision.Stop(OrderScrollDecision.REASON_MAX_SCREENS)
        return OrderScrollDecision.Continue
    }
}

/**
 * 分页游标：断点续传的位置事实。anchorKeys 只取最近一页的新键（最多
 * [MAX_ANCHORS] 个，超长截断），是「滚动确实在前进」的锚，不是全集。
 * 编码：Base64(url-safe, no padding) 包住 5 个字段（format/runKey/direction/
 * lastScreen/anchorsJoined）；字段分隔 \\u001F、锚点分隔 \\u001E——页文本经
 * slice1 清洗后不含这两个控制字符；字段内 US 与锚点内 RS 在拼接前各自防御性剥离。
 */
data class OrderPageCursor(
    val runKey: String,
    val direction: OrderDirection,
    val lastScreen: Int,
    val anchorKeys: List<String>,
) {
    fun encode(): String = encodeControlSeparated(
        FORMAT,
        runKey,
        direction.name,
        lastScreen.toString(),
        anchorKeys.map { it.replace(RS, "") }.joinToString(ANCHOR_SEPARATOR),
    )

    companion object {
        const val FORMAT = "o10cursor1"

        /** 锚点分隔符（record separator）。 */
        const val ANCHOR_SEPARATOR = RS

        const val MAX_ANCHORS = 3

        /** 从一页读取结果构造游标（锚点=本页新键，截断到 [MAX_ANCHORS]）。 */
        fun of(runKey: String, direction: OrderDirection, page: OrderPageReading): OrderPageCursor =
            OrderPageCursor(
                runKey = runKey,
                direction = direction,
                lastScreen = page.screen,
                anchorKeys = page.newRows.map { it.orderKey }.take(MAX_ANCHORS),
            )

        /** 解不开（格式/标记/方向/屏号非法）→ null，fail-closed 不猜位置。 */
        fun decode(raw: String): OrderPageCursor? {
            val parts = decodeControlSeparated(raw, expectedParts = 5) ?: return null
            if (parts[0] != FORMAT) return null
            val runKey = parts[1]
            if (runKey.isEmpty()) return null
            val direction = runCatching { OrderDirection.valueOf(parts[2]) }.getOrNull() ?: return null
            val screen = parts[3].toIntOrNull() ?: return null
            if (screen < 1 || screen > OrderScrollPolicy.MAX_SCREENS) return null
            val anchors = parts[4].split(ANCHOR_SEPARATOR).filter { it.isNotEmpty() }
            return OrderPageCursor(
                runKey = runKey,
                direction = direction,
                lastScreen = screen,
                anchorKeys = anchors,
            )
        }
    }
}

/** 字段分隔符（unit separator, U+001F）。 */
internal const val US = "\u001F"

/** 锚点分隔符（record separator, U+001E）。 */
internal const val RS = "\u001E"

/**
 * 控制字符分隔编码的统一实现：游标与断点共用。字段内的 US/RS 剥掉
 * （清洗后的页文本本就不含，这里是防御），外壳 Base64 url-safe 无填充。
 */
internal fun encodeControlSeparated(vararg parts: String): String {
    // 只防御字段分隔符 US；RS 是调用方（锚点）的合法分隔符，不能在这里剥掉。
    val cleaned = parts.map { part -> part.replace(US, "") }
    return Base64.getUrlEncoder().withoutPadding()
        .encodeToString(cleaned.joinToString(US).toByteArray(Charsets.UTF_8))
}

internal fun decodeControlSeparated(raw: String, expectedParts: Int): List<String>? {
    val decoded = runCatching {
        Base64.getUrlDecoder().decode(raw).toString(Charsets.UTF_8)
    }.getOrNull() ?: return null
    val parts = decoded.split(US)
    return if (parts.size == expectedParts) parts else null
}
