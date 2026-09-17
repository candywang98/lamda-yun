package com.company.cloudctl.companion.features.xianyu.orders

import com.company.cloudctl.companion.automation.OrderDirection

/**
 * O10 历史切片（任务卡 §3）：把一个 run 的页摘要折叠成历史窗口，注明采集窗口
 * （起止时间）与缺失页（屏号断档）——报表侧据此如实说明「这份订单数据只覆盖了
 * 哪些屏、缺了哪些屏」，而不是默默当全集展示。
 *
 * 断网重传合并：同屏号的重复摘要只保留一份（后到的覆盖先到的——重传成功说明
 * 后到的是完整版），绝不重复计数。
 */
object OrderHistoryWindow {
    data class Window(
        val runKey: String,
        val direction: OrderDirection,
        /** 采集窗口起点：所有已采屏里最早的 collectedAt；全部未知时为 null（如实缺失）。 */
        val startedAt: String?,
        /** 采集窗口终点：最晚的 collectedAt。 */
        val endedAt: String?,
        /** 已采屏号（升序去重）。 */
        val screensPresent: List<Int>,
        /** 缺失屏号：1..最大已采屏 里的断档（没采到的页，报表必须标注）。 */
        val missingScreens: List<Int>,
        /** 空页屏号：采到了但列表为空（正常到底）。 */
        val emptyScreens: List<Int>,
        /** 部分可见屏号：该屏存在部分可见行（滚动停在行中间）。 */
        val partialScreens: List<Int>,
        /** 本 run 累计新键数（重传不重复计）。 */
        val totalNewKeys: Int,
        /** 本 run 累计状态变化键数。 */
        val totalUpdatedKeys: Int,
    )

    /** 把一个 run 的页摘要折叠成窗口；重传同屏覆盖，屏号断档算缺失。 */
    fun of(
        runKey: String,
        direction: OrderDirection,
        summaries: List<OrderPageSummary>,
    ): Window {
        val merged = LinkedHashMap<Int, OrderPageSummary>()
        summaries.forEach { summary ->
            require(summary.screen >= 1) { "screen is 1-based" }
            merged[summary.screen] = summary
        }
        val screens = merged.keys.sorted()
        val maxScreen = screens.lastOrNull() ?: 0
        val timestamps = merged.values.map { it.collectedAt }.filter { it.isNotEmpty() }
        return Window(
            runKey = runKey,
            direction = direction,
            startedAt = timestamps.minOrNull(),
            endedAt = timestamps.maxOrNull(),
            screensPresent = screens,
            missingScreens = if (maxScreen == 0) emptyList() else (1..maxScreen).filter { it !in merged },
            emptyScreens = merged.values.filter { it.empty }.map { it.screen },
            partialScreens = merged.values.filter { it.partiallyVisible > 0 }.map { it.screen },
            totalNewKeys = merged.values.sumOf { it.newKeys },
            totalUpdatedKeys = merged.values.sumOf { it.updatedKeys },
        )
    }

    /**
     * 人读标注（报表/前端直接展示）。缺什么说什么；全齐时说全齐。
     * collectedAt 是 ISO-8601 文本（+08:00 或 Z），同格式下字典序即时间序。
     */
    fun annotate(window: Window): String {
        val parts = mutableListOf<String>()
        parts += if (window.screensPresent.isEmpty()) {
            "已采 0 屏"
        } else {
            "已采第 ${window.screensPresent.joinToString("、")} 屏"
        }
        if (window.missingScreens.isNotEmpty()) {
            parts += "缺失第 ${window.missingScreens.joinToString("、")} 屏"
        }
        if (window.emptyScreens.isNotEmpty()) {
            parts += "第 ${window.emptyScreens.joinToString("、")} 屏为空页"
        }
        if (window.partialScreens.isNotEmpty()) {
            parts += "第 ${window.partialScreens.joinToString("、")} 屏有部分可见行"
        }
        parts += "新增 ${window.totalNewKeys} 键"
        if (window.totalUpdatedKeys > 0) {
            parts += "状态变化 ${window.totalUpdatedKeys} 键"
        }
        if (window.startedAt != null && window.endedAt != null) {
            parts += "窗口 ${window.startedAt} ~ ${window.endedAt}"
        } else {
            parts += "窗口时间缺失"
        }
        return parts.joinToString(" · ")
    }
}
