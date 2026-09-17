package com.company.cloudctl.companion.features.xianyu.maintenance.basic

/**
 * X11 — 维护动作与**各自独立**的结果类型（任务卡第 5 条铁律）。
 *
 * 每个动作的结果 wire 码独立（POLISHED/DELISTED/PRICE_REDUCED/RELISTED），
 * 禁止把任何结果统一映射成 success/delete：[MaintenanceActionResult.requireMatches]
 * 是类型层的硬门——DELIST 目标只能记 [MaintenanceActionResult.Delisted]，
 * 任何跨动作记账直接抛错（这是纪律，不是约定）。
 *
 * 与服务端镜像（services/control-api xianyu_maintenance.py）：服务端按
 * XIANYU_POLISH_DONE / XIANYU_DELIST_DONE / XIANYU_DELETE_DELISTED_DONE 分动作
 * 留痕、commandType 按动作分形；设备侧结果类型与之同构。
 */
enum class MaintenanceActionKind(val wire: String) {
    /** 擦亮（页顶一键擦亮，轻风险写，无账本单击）。 */
    POLISH("polish"),

    /** 下架（在卖 → 已下架，破坏性二次单击受控）。 */
    DELIST("delist"),

    /** 降价（动作按钮锚点 + 身份证明 + 字段回读三件套，见 [PriceReductionPlan]）。 */
    PRICE_REDUCE("price-reduce"),

    /** 编辑重发（复用发布流程语义；旧对象处置必须显式独立审批，见 [RelistPlan]）。 */
    RELIST("relist"),
}

/**
 * 逐动作结果类型：每个动作一个自己的结果，绝不共用一个「success」。
 * wire 码在 [MaintenanceActionResult] 全体中唯一（测试钉死）。
 */
sealed interface MaintenanceActionResult {
    /** 该结果所属的动作（类型对齐的门由它判定）。 */
    val kind: MaintenanceActionKind
    val wire: String

    /** POLISH 的唯一结果。 */
    data object Polished : MaintenanceActionResult {
        override val kind: MaintenanceActionKind get() = MaintenanceActionKind.POLISH
        override val wire: String get() = "POLISHED"
    }

    /** DELIST 的唯一结果。 */
    data object Delisted : MaintenanceActionResult {
        override val kind: MaintenanceActionKind get() = MaintenanceActionKind.DELIST
        override val wire: String get() = "DELISTED"
    }

    /** PRICE_REDUCE 的结果：携带降价前后金额（回读证据的一部分）。 */
    data class PriceReduced(
        val oldPriceCents: Long,
        val newPriceCents: Long,
    ) : MaintenanceActionResult {
        override val kind: MaintenanceActionKind get() = MaintenanceActionKind.PRICE_REDUCE
        override val wire: String get() = "PRICE_REDUCED"

        init {
            require(newPriceCents in 1 until oldPriceCents) {
                "a price reduction must stay positive and actually reduce: " +
                    "$oldPriceCents -> $newPriceCents"
            }
        }
    }

    /** RELIST 的结果：携带新对象的外部身份（发布成功时写回，可空=待回填）。 */
    data class Relisted(val newPlatformItemId: String?) : MaintenanceActionResult {
        override val kind: MaintenanceActionKind get() = MaintenanceActionKind.RELIST
        override val wire: String get() = "RELISTED"
    }

    companion object {
        /** 结果类型对齐门：动作与结果不符 = 编排 bug，直接抛（禁止静默换算）。 */
        fun requireMatches(action: MaintenanceActionKind, result: MaintenanceActionResult) {
            require(result.kind == action) {
                "result ${result.wire} does not belong to action ${action.wire}; " +
                    "unified success/delete mapping is forbidden (X11)"
            }
        }

        /** 全体结果 wire 码（测试用：钉死各动作结果码独立）。 */
        val allWires: Set<String> = setOf(
            Polished.wire,
            Delisted.wire,
            PriceReduced(200L, 100L).wire,
            Relisted(null).wire,
        )
    }
}

/**
 * 单目标单次执行的终局：只有 [Completed] 携带动作结果；
 * 回读不符/不可读 → [ReadbackHeld]，**不记成功**；已派发结果未知 → [Unknown]；
 * 其余零副作用失败 → [Failed]。四类绝不互换（分类语义与 X10 delete 同构）。
 */
sealed interface MaintenanceOutcome {
    data class Completed(val result: MaintenanceActionResult) : MaintenanceOutcome
    data class ReadbackHeld(val reasonCode: String, val reason: String) : MaintenanceOutcome
    data class Unknown(val reasonCode: String, val reason: String) : MaintenanceOutcome
    data class Failed(val reasonCode: String, val reason: String) : MaintenanceOutcome
}
