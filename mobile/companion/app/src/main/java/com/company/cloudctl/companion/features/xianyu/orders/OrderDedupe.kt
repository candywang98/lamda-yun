package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderRowParser
import com.company.cloudctl.companion.automation.OrderRowSnapshot
import com.company.cloudctl.companion.automation.SkippedOrderRow

/**
 * O10 去重升级（fleet-first-20260916.1 任务卡 O10 §1）：按真实可见订单 ID 去重，
 * 缺 ID 降级标记（MISSING_ID），绝不拼凑假 ID；状态变化走 upsert。
 *
 * 勘测事实（recon-20260915-2，08/09 dump）：订单列表页不暴露平台订单号，slice1
 * 的复合自然键 `{direction}|{对手昵称}|{商品标题}|{amount_cents}` 仍是缺 ID 时的
 * 降级键——但必须带上 MISSING_ID 标记，让历史报表能区分「真实键」与「降级键」，
 * 而不是把复合键伪装成订单号。真实 ID 的来源是整段纯数字 15..24 位（订单详情
 * 页/未来列表改版）；[realOrderId] 找不到就返回 null，调用方降级，不猜测。
 *
 * 纯逻辑、无 Android 依赖：LocalAutomationExecutor 的接线（在 reportPendingOrders
 * 前调用 absorbPage）由主会话完成，本包只提供可单测的模型。
 */
object OrderDedupe {
    /** 键来自真实可见的平台订单号。 */
    const val MARKER_REAL_ID = "REAL_ID"

    /** 页面没有订单号，键是 slice1 复合自然键的降级形态。 */
    const val MARKER_MISSING_ID = "MISSING_ID"

    /** 平台订单号形状：整段纯数字 15..24 位（宁缺勿假：短数字串、含分隔符的一律不算）。 */
    private val REAL_ORDER_ID = Regex("^[0-9]{15,24}$")

    /**
     * 从一行订单的原始文本里提取真实可见订单号；没有则 null。
     * 输入先走 [OrderRowParser.cleanSegment]（去 \u200b + 首尾空白），
     * 与 slice1 的行清洗口径一致。
     */
    fun realOrderId(lines: List<String>): String? =
        lines.asSequence()
            .mapNotNull { OrderRowParser.cleanSegment(it).takeIf(String::isNotEmpty) }
            .firstOrNull { REAL_ORDER_ID.matches(it) }

    /** 一个已组装的 orderKey 是否本身就是真实订单号形状。 */
    fun markerFor(orderKey: String): String =
        if (REAL_ORDER_ID.matches(orderKey)) MARKER_REAL_ID else MARKER_MISSING_ID
}

/** 去重键：值 + 降级标记。同 marker 的键才可能相等；REAL_ID 与 MISSING_ID 永不合并。 */
data class OrderDedupeKey(val value: String, val marker: String)

/**
 * 一次吸收（absorb）一行的三种结果。
 *
 * @property Updated 状态变化 upsert：合并后的快照替换已见快照（新状态/补空字段），
 *   previousStatus 留证。
 */
sealed interface OrderAbsorbDecision {
    val key: OrderDedupeKey

    data class New(override val key: OrderDedupeKey) : OrderAbsorbDecision
    data class Duplicate(override val key: OrderDedupeKey) : OrderAbsorbDecision

    data class Updated(
        override val key: OrderDedupeKey,
        val previousStatus: String?,
    ) : OrderAbsorbDecision
}

/**
 * 已见集合：跨页/置顶/断网重传的重复键全部在此吸收，只有新键和状态变化键外报。
 * 键规则（O10 §1）：真实订单号可见 → 键值=订单号（REAL_ID）；否则键值=slice1 复合
 * 键（MISSING_ID）。同一订单的两种键形态不强行合并（列表页没有 ID 时无从知道对应
 * 关系），升级到详情页读取后自然统一到 REAL_ID。
 */
class OrderSeenRegistry {
    private val seen = LinkedHashMap<String, OrderRowSnapshot>()

    /** 已吸收的唯一键数。 */
    val size: Int get() = seen.size

    fun dedupeKeyOf(snapshot: OrderRowSnapshot): OrderDedupeKey {
        val real = OrderDedupe.realOrderId(snapshot.rawLines)
        return if (real != null) {
            OrderDedupeKey(real, OrderDedupe.MARKER_REAL_ID)
        } else {
            OrderDedupeKey(snapshot.orderKey, OrderDedupe.MARKER_MISSING_ID)
        }
    }

    fun absorb(snapshot: OrderRowSnapshot): OrderAbsorbDecision {
        val key = dedupeKeyOf(snapshot)
        val existing = seen[key.value]
            ?: run {
                seen[key.value] = snapshot
                return OrderAbsorbDecision.New(key)
            }
        if (!upsertWorth(existing, snapshot)) return OrderAbsorbDecision.Duplicate(key)
        seen[key.value] = mergeSnapshot(existing, snapshot)
        return OrderAbsorbDecision.Updated(key, existing.statusText)
    }

    /** upsert 触发条件：状态文本变化，或新快照补上了旧快照缺失的字段。 */
    private fun upsertWorth(existing: OrderRowSnapshot, incoming: OrderRowSnapshot): Boolean =
        existing.statusText != incoming.statusText ||
            (existing.itemTitle == null && incoming.itemTitle != null) ||
            (existing.buyerName == null && incoming.buyerName != null) ||
            (existing.amountCents == null && incoming.amountCents != null) ||
            (existing.occurredAt == null && incoming.occurredAt != null)

    /**
     * 合并规则：状态/新非空字段取新值，旧非空字段保留（先见事实不丢）；
     * rawLines 保留首见证据（页面原文是勘测材料，不随后续滚动改写）。
     */
    private fun mergeSnapshot(existing: OrderRowSnapshot, incoming: OrderRowSnapshot) =
        OrderRowSnapshot(
            direction = existing.direction,
            orderKey = existing.orderKey,
            itemTitle = existing.itemTitle ?: incoming.itemTitle,
            buyerName = existing.buyerName ?: incoming.buyerName,
            amountCents = existing.amountCents ?: incoming.amountCents,
            statusText = incoming.statusText ?: existing.statusText,
            occurredAt = existing.occurredAt ?: incoming.occurredAt,
            rawLines = existing.rawLines,
        )

    /** 当前已见快照（键序稳定，供断点持久化/调试）。 */
    fun snapshots(): List<OrderRowSnapshot> = seen.values.toList()
}

/** 一页读取的完整结果：新键、状态变化键、重叠数、跳过行、部分可见行计数。 */
data class OrderPageReading(
    val screen: Int,
    val newRows: List<OrderRowSnapshot>,
    val updatedRows: List<OrderRowSnapshot>,
    val overlapCount: Int,
    val skippedRows: List<SkippedOrderRow>,
    val partiallyVisibleRows: Int,
    val empty: Boolean,
) {
    /** 本页出现的去重键（含重复），供游标锚点与页摘要使用。 */
    val newKeyCount: Int get() = newRows.size

    companion object {
        val EMPTY_SCREEN_1: OrderPageReading = OrderPageReading(
            screen = 1,
            newRows = emptyList(),
            updatedRows = emptyList(),
            overlapCount = 0,
            skippedRows = emptyList(),
            partiallyVisibleRows = 0,
            empty = true,
        )
    }
}

/**
 * 部分可见行判定：行解析出了键（有金额或段信息）但昵称与标题都缺——
 * 滚动停在一行中间时的典型形态。行是已观测事实，照常去重上报，
 * 但页摘要计数 partialRows，历史报表据此标注。
 */
fun OrderRowSnapshot.isPartiallyVisible(): Boolean = buyerName == null && itemTitle == null

/**
 * 页级吸收入口：一屏的行快照逐个过已见集合，返回该页的 [OrderPageReading]。
 * 置顶订单每页重现、跨页重叠、断网重传的同页重放，都落在 overlapCount，不重复计数。
 */
fun OrderSeenRegistry.absorbPage(
    screen: Int,
    snapshots: List<OrderRowSnapshot>,
    skipped: List<SkippedOrderRow> = emptyList(),
): OrderPageReading {
    val newRows = mutableListOf<OrderRowSnapshot>()
    val updatedRows = mutableListOf<OrderRowSnapshot>()
    var overlap = 0
    snapshots.forEach { snapshot ->
        when (absorb(snapshot)) {
            is OrderAbsorbDecision.New -> newRows += snapshot
            is OrderAbsorbDecision.Updated -> updatedRows += snapshot
            is OrderAbsorbDecision.Duplicate -> overlap += 1
        }
    }
    return OrderPageReading(
        screen = screen,
        newRows = newRows,
        updatedRows = updatedRows,
        overlapCount = overlap,
        skippedRows = skipped,
        partiallyVisibleRows = snapshots.count { it.isPartiallyVisible() },
        empty = snapshots.isEmpty() && skipped.isEmpty(),
    )
}
