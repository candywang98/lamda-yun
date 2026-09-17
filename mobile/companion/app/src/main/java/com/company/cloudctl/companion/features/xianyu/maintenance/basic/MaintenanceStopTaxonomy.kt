package com.company.cloudctl.companion.features.xianyu.maintenance.basic

/**
 * X11 — 批量维护的显式停止条件（任务卡第 4 条铁律）。
 *
 * 四个停止条件各自携带**独立**原因码（wire 即原因码），停就是停：
 * [MaintenanceBatchRun] 一旦闩住 [MaintenanceHalt]，后续任何 nextDecision
 * 都返回同一 Halted，绝不自动续跑；解除的唯一路径是操作员介入后**新建运行**
 * （逐目标台账保证已完成动作不重复执行）。
 *
 * 身份证明失败是第五种停机形态（验收用例 2：目标被顶走/插队 → 不把下一项
 * 当原对象），与四个批量停止条件分开建模，但同样是闩死。
 */
enum class MaintenanceStopCondition(val wire: String) {
    /** 翻页超限：为找目标扫过的页深超过上限（防无限滚动扫库）。 */
    PAGINATION_LIMIT_EXCEEDED("PAGINATION_LIMIT_EXCEEDED"),

    /** 保护期：同目标存在未核销的旧尝试（UNKNOWN 未解除），明确拒绝，不排队。 */
    PROTECTION_PERIOD_ACTIVE("PROTECTION_PERIOD_ACTIVE"),

    /** 目标数超限：单次计划的目标数超过上限（镜像服务端 MAX_RUN_TASKS=50）。 */
    TARGET_COUNT_LIMIT_EXCEEDED("TARGET_COUNT_LIMIT_EXCEEDED"),

    /** 预算超限：计划内降价总金额超过预算（只在涉及 PRICE_REDUCE 时判定）。 */
    BUDGET_LIMIT_EXCEEDED("BUDGET_LIMIT_EXCEEDED"),
}

/** 停机记录：条件 + 可读原因 + 命中时的目标（可空=计划级守卫，未到任何目标）。 */
sealed interface MaintenanceHalt {
    val reasonCode: String
    val reason: String

    /**
     * 四个批量停止条件之一命中。reasonCode 恒等于 condition.wire
     * （独立性由枚举保证，测试钉死四个 wire 互不相同）。
     */
    data class StopConditionHit(
        val condition: MaintenanceStopCondition,
        override val reason: String,
        val targetKey: MaintenanceTargetKey? = null,
    ) : MaintenanceHalt {
        override val reasonCode: String get() = condition.wire

        init {
            require(reason.isNotBlank()) { "a stop condition needs a readable reason" }
        }
    }

    /**
     * 身份证明失败即停（B13 血缘）：复合证据歧义/不足/无目标 ID → 目标可能是
     * 被顶走/插队后的**另一件**，绝不把列表里的下一项当原对象继续。
     */
    data class IdentityProofFailed(
        val identityReason: String,
        val targetKey: MaintenanceTargetKey?,
    ) : MaintenanceHalt {
        override val reasonCode: String get() = IDENTITY_PROOF_FAILED
        override val reason: String
            get() = "target identity could not be proven ($identityReason); " +
                "the next list item must NEVER be treated as the original target — halt"

        companion object {
            const val IDENTITY_PROOF_FAILED = "IDENTITY_PROOF_FAILED"
        }
    }
}
