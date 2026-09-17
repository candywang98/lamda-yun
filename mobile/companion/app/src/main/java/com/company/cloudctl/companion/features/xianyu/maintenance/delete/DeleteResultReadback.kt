package com.company.cloudctl.companion.features.xianyu.maintenance.delete

/**
 * X10 — 删除结果回读（权威可见结果 + 待核对语义）。
 *
 * 删除单击之后的核验输入只有三类**权威可见**观察（契约 xianyu-anchors-20260915 /
 * xianyu-maintenance-anchors-20260915，证据门不得擅改——改判定输入集 = 契约评审）：
 *
 * 1. 列表消失：回到「我发布的-已下架」后，同目标（标题定位）在列表中不可见；
 * 2. badge 变化：已下架 tab 数字角标 N-1（锚点契约：「删除成功⇒已下架 N-1」）；
 * 3. 确认框消失信号：删除确认弹窗关闭（弱信号，仅辅助）。
 *
 * 判定纪律（P09 第三次失败的原型）：
 * - 列表消失 + badge 佐证 → [DeleteReadbackVerdict.VerifiedDeleted]（机器可记成功）。
 * - 列表消失但 badge 门禁缺失/不可读（v2 详情路径 tabs 不在树内、已下架 tab 实测
 *   无数字角标）→ [DeleteReadbackVerdict.PendingVerification]「待核对」——**不伪造
 *   成功**，交操作员以 platformItemId + 截图核销。
 * - 目标仍可见 → [DeleteReadbackVerdict.StillPresent]：单击未生效或回读定位错误，
 *   一律不是成功；配合 UNKNOWN 台账等操作员。
 * - 观察互相矛盾（弹窗仍在却称列表消失等）→ [DeleteReadbackVerdict.Inconclusive]。
 *
 * 本对象是纯函数：无 IO、无时钟、无截图访问；证据引用由接线层采集后传入。
 */
object DeleteResultReadback {

    /** 回读观察快照（全部由接线层从真机采集）。 */
    data class Observation(
        /** 目标标题在已下架列表是否仍可见（true = 还在）。 */
        val targetStillVisible: Boolean,
        /**
         * 已下架 tab 数字角标读数；null = 角标缺失/不可读（badge 门禁缺失，
         * 不允许编造数值）。
         */
        val delistedBadgeCount: Int? = null,
        /** 删除前已下架角标基线（第一击前快照，MaintenanceBadgeSnapshots 语义）。 */
        val delistedBadgeBaseline: Int? = null,
        /** 删除确认弹窗是否已关闭（弱信号）。 */
        val confirmDialogDismissed: Boolean? = null,
    )

    /** 判定携带的证据引用（截图哈希等，接线层采集；判定器只透传）。 */
    data class Evidence(
        val listReadbackScreenshot: String? = null,
        val badgeReadbackScreenshot: String? = null,
        val strikeScreenshot: String? = null,
    )
}

/** 回读判定（有序：只有 VERIFIED_DELETED 是机器成功，其余一律不记成功）。 */
sealed interface DeleteReadbackVerdict {
    /** 权威可见结果齐备：列表消失 + badge N-1 佐证。 */
    data class VerifiedDeleted(
        val evidence: DeleteResultReadback.Evidence,
        val badgeBefore: Int,
        val badgeAfter: Int,
    ) : DeleteReadbackVerdict

    /**
     * 待核对：列表消失但 badge 门禁缺失/不可读。绝不折算成成功；操作员以
     * platformItemId/截图核销（A13 相位机 resolved 才算终局）。
     */
    data class PendingVerification(
        val reasonCode: String,
        val reason: String,
        val evidence: DeleteResultReadback.Evidence,
    ) : DeleteReadbackVerdict

    /** 目标仍可见：删除未生效（或回读定位到错卡），不是成功。 */
    data class StillPresent(
        val reason: String,
        val evidence: DeleteResultReadback.Evidence,
    ) : DeleteReadbackVerdict

    /** 观察矛盾：不结论，按 UNKNOWN 处置（等操作员）。 */
    data class Inconclusive(
        val reasonCode: String,
        val reason: String,
        val evidence: DeleteResultReadback.Evidence,
    ) : DeleteReadbackVerdict
}

/** 回读判定器（纯函数）。 */
object DeleteReadbackJudge {

    /**
     * 按判定纪律裁决一次回读。**成功路径必须双证齐备**（列表消失 + badge 佐证），
     * badge 门禁缺失一律降「待核对」——这正是 P09 删除终版验收的真机形态。
     */
    fun judge(observation: DeleteResultReadback.Observation): DeleteReadbackVerdict {
        // 矛盾检查先行：弹窗未关却声称列表已消失 → 不结论。
        if (observation.confirmDialogDismissed == false) {
            return DeleteReadbackVerdict.Inconclusive(
                reasonCode = DispatchedUnknownReason.READBACK_INCONCLUSIVE,
                reason = "the confirm dialog is still open while a list readback was claimed; " +
                    "observations contradict, refusing to conclude",
                evidence = DeleteResultReadback.Evidence(),
            )
        }
        if (observation.targetStillVisible) {
            return DeleteReadbackVerdict.StillPresent(
                reason = "target is still visible in the delisted list after the confirm strike; " +
                    "either the delete did not take effect or the readback located the wrong card",
                evidence = DeleteResultReadback.Evidence(),
            )
        }
        // 列表已消失。badge 双证：基线与读数都在且差 1 → 机器成功。
        val baseline = observation.delistedBadgeBaseline
        val after = observation.delistedBadgeCount
        return if (baseline != null && after != null) {
            if (after == baseline - 1) {
                DeleteReadbackVerdict.VerifiedDeleted(
                    evidence = DeleteResultReadback.Evidence(),
                    badgeBefore = baseline,
                    badgeAfter = after,
                )
            } else {
                DeleteReadbackVerdict.Inconclusive(
                    reasonCode = DispatchedUnknownReason.READBACK_INCONCLUSIVE,
                    reason = "target vanished but the delisted badge moved $baseline -> $after " +
                        "(expected ${baseline - 1}); refusing to fabricate success",
                    evidence = DeleteResultReadback.Evidence(),
                )
            }
        } else {
            // badge 门禁缺失（已下架 tab 无数字角标 / v2 详情路径 tabs 不在树内）：
            // 待核对，绝不伪造成功。证据门契约（判定输入集）不得为凑成功而擅改。
            DeleteReadbackVerdict.PendingVerification(
                reasonCode = DispatchedUnknownReason.BADGE_UNREADABLE,
                reason = "target vanished from the list but the badge gate is missing " +
                    "(baseline=${baseline ?: "unreadable"}, readback=${after ?: "unreadable"}); " +
                    "held for operator verification, success is NOT recorded",
                evidence = DeleteResultReadback.Evidence(),
            )
        }
    }
}
