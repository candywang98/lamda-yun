package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.features.xianyu.publish.PublishCompletionBoundary

/**
 * X11 — 编辑重发计划（任务卡第 3 条铁律）。
 *
 * 复用发布流程语义：完成边界沿用 P10 的 [PublishCompletionBoundary]
 * （publish 包对本任务只读引用），重发侧的填写/提交/成功判据与发布同一套。
 *
 * 旧对象的删除/下架**绝不是隐式步骤**：只要重发意味着旧对象要让位
 * （[OldObjectDisposition.DELIST_OLD] / [OldObjectDisposition.DELETE_OLD]），
 * 必须先在 [MaintenanceApprovalLedger] 里存在一条**显式独立**的
 * OLD_OBJECT_REMOVAL 批准（同目标、同动作）；缺批准/用途不对/动作不对/
 * 目标不符 = 一律 [RelistPlanError.IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN] 拒绝。
 * 不动旧对象（KEEP_LISTED，例如已下架商品的「重新上架」编辑）不需要处置批准。
 */
enum class OldObjectDisposition(val wire: String) {
    /** 不动旧对象（重发对象就是旧对象自身，如已下架品重新上架）。 */
    KEEP_LISTED("keep-listed"),

    /** 旧对象下架让位：需要显式独立批准（DELIST + OLD_OBJECT_REMOVAL）。 */
    DELIST_OLD("delist-old"),

    /** 旧对象删除让位：需要显式独立批准（DELETE 语义在本包= X10 delete 的领地，
     *  这里只校验批准存在与用途，删除执行走 X10 delete 通道）。 */
    DELETE_OLD("delete-old"),
}

/** 重发计划错误（原因码独立）。 */
enum class RelistPlanError(val wire: String) {
    IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN("IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN"),
    REMOVAL_APPROVAL_NOT_MATCHED("REMOVAL_APPROVAL_NOT_MATCHED"),
    UNNECESSARY_REMOVAL_APPROVAL("UNNECESSARY_REMOVAL_APPROVAL"),
    INVALID_REMOVAL_APPROVAL_STATE("INVALID_REMOVAL_APPROVAL_STATE"),
}

sealed interface RelistPlanValidation {
    data class Valid(val plan: RelistPlan) : RelistPlanValidation
    data class Invalid(val error: RelistPlanError, val reason: String) : RelistPlanValidation
}

/** 已冻结的重发计划（私有构造，唯一入口是 [RelistPlanValidator.validate]）。 */
class RelistPlan internal constructor(
    val oldTarget: MaintenanceTargetKey,
    val boundary: PublishCompletionBoundary,
    val disposition: OldObjectDisposition,
    val removalApprovalId: String?,
)

/** 重发计划校验器（纯决策；批准清单只读查询）。 */
object RelistPlanValidator {

    fun validate(
        oldTarget: MaintenanceTargetKey,
        boundary: PublishCompletionBoundary,
        disposition: OldObjectDisposition,
        removalApprovalId: String?,
        approvals: MaintenanceApprovalLedger,
    ): RelistPlanValidation {
        return when (disposition) {
            OldObjectDisposition.KEEP_LISTED -> {
                if (removalApprovalId != null) {
                    RelistPlanValidation.Invalid(
                        RelistPlanError.UNNECESSARY_REMOVAL_APPROVAL,
                        "disposition is KEEP_LISTED (the old object stays); a removal " +
                            "approval ($removalApprovalId) has no object here — reject the " +
                            "contradictory plan instead of silently keeping it",
                    )
                } else {
                    RelistPlanValidation.Valid(
                        RelistPlan(oldTarget, boundary, disposition, null),
                    )
                }
            }
            OldObjectDisposition.DELIST_OLD, OldObjectDisposition.DELETE_OLD -> {
                // 让位处置必须有显式独立批准：缺批准 = 隐式删除/下架，铁律拒绝。
                if (removalApprovalId == null) {
                    return RelistPlanValidation.Invalid(
                        RelistPlanError.IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN,
                        "relist disposition ${disposition.wire} would remove the old object " +
                            "without an explicit independent approval; implicit removal is " +
                            "never a hidden step of a republish",
                    )
                }
                val record = approvals.record(removalApprovalId)
                if (record == null) {
                    return RelistPlanValidation.Invalid(
                        RelistPlanError.IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN,
                        "removal approval $removalApprovalId does not exist; the old object " +
                            "cannot be removed implicitly",
                    )
                }
                if (record.purpose != ApprovalPurpose.OLD_OBJECT_REMOVAL) {
                    return RelistPlanValidation.Invalid(
                        RelistPlanError.REMOVAL_APPROVAL_NOT_MATCHED,
                        "approval $removalApprovalId purpose is ${record.purpose.wire}, " +
                            "not ${ApprovalPurpose.OLD_OBJECT_REMOVAL.wire}",
                    )
                }
                if (record.targetKey.identityKey != oldTarget.identityKey) {
                    return RelistPlanValidation.Invalid(
                        RelistPlanError.REMOVAL_APPROVAL_NOT_MATCHED,
                        "removal approval covers ${record.targetKey.identityKey}, not the " +
                            "relist target ${oldTarget.identityKey}",
                    )
                }
                // 动作匹配：DELIST_OLD 精确要求 DELIST 批准。DELETE_OLD 的执行属
                // X10 delete 通道（delete-delisted 单发确认），本包不复制其动作枚举，
                // 只要求「显式独立 removal 批准存在且未花」（用途+目标+状态三项硬校验）；
                // 真正的破坏性删除单击仍要走 X10 自己的批准清单。
                if (disposition == OldObjectDisposition.DELIST_OLD &&
                    record.action != MaintenanceActionKind.DELIST
                ) {
                    return RelistPlanValidation.Invalid(
                        RelistPlanError.REMOVAL_APPROVAL_NOT_MATCHED,
                        "disposition delist-old needs a DELIST removal approval, got " +
                            "${record.action.wire}",
                    )
                }
                if (record.state != BasicApprovalState.APPROVED) {
                    return RelistPlanValidation.Invalid(
                        RelistPlanError.INVALID_REMOVAL_APPROVAL_STATE,
                        "removal approval $removalApprovalId is ${record.state.wire}; it " +
                            "must be APPROVED (and unspent) when the relist plan is frozen",
                    )
                }
                RelistPlanValidation.Valid(
                    RelistPlan(oldTarget, boundary, disposition, removalApprovalId),
                )
            }
        }
    }
}
