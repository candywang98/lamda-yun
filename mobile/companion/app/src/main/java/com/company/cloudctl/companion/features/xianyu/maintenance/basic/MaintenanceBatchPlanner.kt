package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.locators.ItemIdentityEvidence

/**
 * X11 — 批量维护：按身份逐件执行（任务卡第 1 条铁律）。
 *
 * 批量操作展开为「每目标独立子任务 + 审批证据」：不复刻旧 APK 的 firstMore
 * 式循环（拿第一张卡点更多→下一张→循环），而是每个目标各自携带
 * MaintenanceTargetKey（B13 身份）、各自的批准（approvalId）、各自的计划
 * （降价/重发），由 [MaintenanceBatchRun] 单件串行发放；已完成目标幂等跳过，
 * 四个停止条件 + 身份证明失败各自闩停，绝不自动续跑。
 *
 * 与已验证切片的血缘：擦亮/下架 v2（标题定位→详情→管理菜单→GATED 确认）
 * 是每个子任务执行时的设备侧形态，本层只做纯决策（事件进、决策出），
 * automation 接线留给主会话；X10 delete 的单发确认/保护期语义由
 * [MaintenanceApprovalLedger] 对齐实现。
 */

/** 运行限制（四个停止条件的阈值；默认值镜像服务端 MAX_RUN_TASKS=50）。 */
data class MaintenanceLimits(
    val maxTargetsPerRun: Int = DEFAULT_MAX_TARGETS_PER_RUN,
    val maxPaginationDepth: Int = DEFAULT_MAX_PAGINATION_DEPTH,
    /** 降价总预算（分）；null = 无预算守卫（只影响 PRICE_REDUCE）。 */
    val budgetCents: Long? = null,
) {
    init {
        require(maxTargetsPerRun >= 1) { "maxTargetsPerRun must be >= 1" }
        require(maxPaginationDepth >= 1) { "maxPaginationDepth must be >= 1" }
        require(budgetCents == null || budgetCents > 0) { "budgetCents must be positive" }
    }

    companion object {
        const val DEFAULT_MAX_TARGETS_PER_RUN = 50
        const val DEFAULT_MAX_PAGINATION_DEPTH = 20
    }
}

/** 批量计划里的一个目标条目（计划冻结前已通过各自校验器）。 */
data class MaintenanceBatchTarget(
    val targetId: String,
    val key: MaintenanceTargetKey,
    val action: MaintenanceActionKind,
    /** 该目标的直接动作批准（审批证据；PRICE_REDUCE/RELIST 的旧对象处置批准另算）。 */
    val approvalId: String,
    val pricePlan: PriceReductionPlan? = null,
    val relistPlan: RelistPlan? = null,
) {
    init {
        if (action == MaintenanceActionKind.PRICE_REDUCE) {
            require(pricePlan != null) { "a PRICE_REDUCE target needs a validated price plan" }
        }
        if (action == MaintenanceActionKind.RELIST) {
            require(relistPlan != null) { "a RELIST target needs a validated relist plan" }
        }
    }
}

/** 批量计划：目标清单 + 限制（计划级错误在构造期抛出，运行期只处理停止条件）。 */
class MaintenanceBatchPlan(
    val runId: String,
    val targets: List<MaintenanceBatchTarget>,
    val limits: MaintenanceLimits = MaintenanceLimits(),
) {
    init {
        require(runId.isNotBlank()) { "runId is required" }
        require(targets.isNotEmpty()) { "a batch plan needs at least one target" }
        val duplicateKeys = targets
            .groupingBy { "${it.key.identityKey}|${it.action.wire}" }
            .eachCount()
            .filterValues { it > 1 }
            .keys
        require(duplicateKeys.isEmpty()) {
            "duplicate (target, action) entries in the plan: $duplicateKeys"
        }
    }
}

/** 展开后的独立子任务（顺序号 = 计划内的执行序）。 */
data class PerTargetSubtask(
    val subtaskId: String,
    val targetId: String,
    val key: MaintenanceTargetKey,
    val action: MaintenanceActionKind,
    val sequence: Int,
    val approvalId: String,
    val pricePlan: PriceReductionPlan? = null,
    val relistPlan: RelistPlan? = null,
)

/** 计划展开结果：子任务列表，或计划级停止（目标数/预算，未触任何目标即停）。 */
sealed interface BatchExpansion {
    data class Subtasks(val subtasks: List<PerTargetSubtask>) : BatchExpansion
    data class Halted(val halt: MaintenanceHalt) : BatchExpansion
}

/** 计划展开器（纯函数；两个计划级守卫在发放任何目标之前判定）。 */
object MaintenanceBatchPlanner {

    fun expand(plan: MaintenanceBatchPlan): BatchExpansion {
        // 守卫 1：目标数超限——整计划拒绝，一个都不发。
        if (plan.targets.size > plan.limits.maxTargetsPerRun) {
            return BatchExpansion.Halted(
                MaintenanceHalt.StopConditionHit(
                    condition = MaintenanceStopCondition.TARGET_COUNT_LIMIT_EXCEEDED,
                    reason = "plan carries ${plan.targets.size} targets, limit is " +
                        "${plan.limits.maxTargetsPerRun}; stop before any dispatch (no partial sweep)",
                ),
            )
        }
        // 守卫 2：预算超限——计划内降价总金额超预算，整计划拒绝。
        val budget = plan.limits.budgetCents
        if (budget != null) {
            val plannedDelta = plan.targets
                .filter { it.action == MaintenanceActionKind.PRICE_REDUCE }
                .sumOf { it.pricePlan?.plannedDeltaCents ?: 0L }
            if (plannedDelta > budget) {
                return BatchExpansion.Halted(
                    MaintenanceHalt.StopConditionHit(
                        condition = MaintenanceStopCondition.BUDGET_LIMIT_EXCEEDED,
                        reason = "planned price reductions total $plannedDelta cents over " +
                            "budget $budget; stop before any dispatch",
                    ),
                )
            }
        }
        return BatchExpansion.Subtasks(
            plan.targets.mapIndexed { index, target ->
                PerTargetSubtask(
                    subtaskId = "${plan.runId}-s${index + 1}",
                    targetId = target.targetId,
                    key = target.key,
                    action = target.action,
                    sequence = index + 1,
                    approvalId = target.approvalId,
                    pricePlan = target.pricePlan,
                    relistPlan = target.relistPlan,
                )
            },
        )
    }
}

/** 单件发放决策。 */
sealed interface NextDecision {
    /** 发放该子任务（含批准准入裁决；接线层据此驱动已验证的 v2 切片）。 */
    data class Issue(
        val subtask: PerTargetSubtask,
        val approvalAdmission: BasicApprovalDecision,
    ) : NextDecision

    /** 有目标在飞（单件串行）：先报它的结果，再谈下一件。 */
    data object AwaitingResult : NextDecision

    /** 停机闩已置位：同一停机记录反复返回，绝不自动续跑。 */
    data class Halted(val halt: MaintenanceHalt) : NextDecision

    /** 全部目标终局（完成/跳过），无下一件。 */
    data object Finished : NextDecision
}

/** 身份证明裁决。 */
sealed interface IdentityDecision {
    data object Admitted : IdentityDecision
    data object NeedHumanConfirm : IdentityDecision
    data class Halted(val halt: MaintenanceHalt) : IdentityDecision
    data object NotCurrentSubtask : IdentityDecision
}

/** 结果上报裁决。 */
sealed interface ReportDecision {
    data class Recorded(val record: MaintenanceTargetRecord) : ReportDecision
    data object NotCurrentSubtask : ReportDecision
}

/**
 * 批量运行（纯决策状态机；台账与批准清单由调用方持有、跨运行复用）。
 *
 * 停止纪律：halted 一旦置位即闩死（nextDecision 永远返回同一停机）；
 * 「续跑」只能是操作员显式新建一个运行——逐目标台账保证已完成动作不重复。
 */
class MaintenanceBatchRun(
    val runId: String,
    private val subtasks: List<PerTargetSubtask>,
    private val targetLedger: MaintenanceTargetLedger,
    private val approvalLedger: MaintenanceApprovalLedger,
    private val limits: MaintenanceLimits,
) {
    init {
        require(subtasks.isNotEmpty()) { "a batch run needs at least one subtask" }
        val unenrolled = subtasks.filter { targetLedger.record(it.targetId) == null }
        require(unenrolled.isEmpty()) {
            "every subtask target must be enrolled in the ledger first: " +
                unenrolled.joinToString { it.targetId }
        }
    }

    private var halted: MaintenanceHalt? = null
    private var currentSubtaskId: String? = null
    private val humanConfirmed = mutableSetOf<String>()

    val isHalted: Boolean get() = halted != null

    /** 当前停机记录（未停机为 null；测试与接线层观察用）。 */
    fun haltRecord(): MaintenanceHalt? = halted

    /**
     * 单件串行发放：跳过终局目标（幂等），UNKNOWN/保护期闩停，批准准入
     * 拒绝按性质分流（保护类→停机；注册类→该目标 FAILED 后看下一件）。
     * 每次调用幂等：在飞未结前返回 AwaitingResult。
     */
    fun nextDecision(): NextDecision {
        halted?.let { return NextDecision.Halted(it) }
        currentSubtaskId?.let { return NextDecision.AwaitingResult }
        for (subtask in subtasks) {
            val record = targetLedger.record(subtask.targetId) ?: continue
            when (record.state) {
                // 幂等核心：已完成/回读待核/已失败的目标直接跳过，不重复执行。
                MaintenanceTargetState.COMPLETED,
                MaintenanceTargetState.READBACK_HELD,
                MaintenanceTargetState.FAILED,
                -> continue
                // UNKNOWN 目标：保护期闩停（同 X10「未知任务不自动重新执行」）。
                MaintenanceTargetState.UNKNOWN -> {
                    return NextDecision.Halted(
                        latch(
                            MaintenanceHalt.StopConditionHit(
                                condition = MaintenanceStopCondition.PROTECTION_PERIOD_ACTIVE,
                                reason = "target ${subtask.key.identityKey} holds an UNKNOWN " +
                                    "prior attempt (${record.reasonCode}); the operator must " +
                                    "resolve it before this run may continue (no auto resume)",
                                targetKey = subtask.key,
                            ),
                        ),
                    )
                }
                MaintenanceTargetState.IN_FLIGHT, MaintenanceTargetState.PENDING -> {
                    // 台账说可动，但批准先说话：准入拒绝时保护类停机、注册类记失败。
                    val admission = approvalLedger.admit(subtask.approvalId)
                    when (admission) {
                        is BasicApprovalDecision.Rejected -> {
                            if (admission.protectionHalt) {
                                return NextDecision.Halted(
                                    latch(
                                        MaintenanceHalt.StopConditionHit(
                                            condition = MaintenanceStopCondition.PROTECTION_PERIOD_ACTIVE,
                                            reason = admission.reason,
                                            targetKey = subtask.key,
                                        ),
                                    ),
                                )
                            }
                            // 注册类拒绝（过期/已消费/已撤销）：该目标零副作用失败，
                            // 其余目标各有各的批准，继续看下一件。
                            if (record.state == MaintenanceTargetState.PENDING) {
                                targetLedger.markInFlight(subtask.targetId, subtask.subtaskId)
                            }
                            targetLedger.markFailed(subtask.targetId, admission.reasonCode)
                            continue
                        }
                        is BasicApprovalDecision.Admitted, is BasicApprovalDecision.Issued -> Unit
                    }
                    if (record.state == MaintenanceTargetState.PENDING) {
                        targetLedger.markInFlight(subtask.targetId, subtask.subtaskId)
                    }
                    currentSubtaskId = subtask.subtaskId
                    return NextDecision.Issue(subtask, admission)
                }
            }
        }
        return NextDecision.Finished
    }

    /**
     * 身份证明门（验收用例 2）：B13 证据不足/歧义 → 闩 IdentityProofFailed，
     * 绝不把列表里的下一项当原对象；复合证据必须先过人工确认。
     */
    fun submitIdentity(
        subtaskId: String,
        evidence: ItemIdentityEvidence?,
    ): IdentityDecision {
        halted?.let { return IdentityDecision.Halted(it) }
        if (subtaskId != currentSubtaskId) return IdentityDecision.NotCurrentSubtask
        return when (evidence) {
            null -> identityHalt("no target id and no account-scoped composite")
            is ItemIdentityEvidence.PlatformItemId -> IdentityDecision.Admitted
            is ItemIdentityEvidence.CompositeConfirmed ->
                if (subtaskId in humanConfirmed) {
                    IdentityDecision.Admitted
                } else {
                    IdentityDecision.NeedHumanConfirm
                }
            is ItemIdentityEvidence.Insufficient -> identityHalt(evidence.reason)
        }
    }

    /** 人工身份确认回执（复合证据的强制门）。 */
    fun confirmHumanIdentity(subtaskId: String): IdentityDecision {
        halted?.let { return IdentityDecision.Halted(it) }
        if (subtaskId != currentSubtaskId) return IdentityDecision.NotCurrentSubtask
        humanConfirmed += subtaskId
        return IdentityDecision.Admitted
    }

    /** 单发确认申请（批准清单 claim-once；接线层拿 issuance 驱动受控单击）。 */
    fun claimConfirmOnce(subtaskId: String): BasicApprovalDecision {
        require(subtaskId == currentSubtaskId) { "only the current subtask may claim a confirm" }
        return approvalLedger.claimActionOnce(
            approvalId = subtasks.first { it.subtaskId == subtaskId }.approvalId,
            subtaskId = subtaskId,
        )
    }

    /**
     * 结果上报：按 [MaintenanceOutcome] 分类落账。UNKNOWN 只落账不停机——
     * 下一次 nextDecision 到达该目标时闩 PROTECTION（保护期原因码独立）。
     */
    fun reportOutcome(subtaskId: String, outcome: MaintenanceOutcome): ReportDecision {
        halted?.let { return ReportDecision.NotCurrentSubtask }
        if (subtaskId != currentSubtaskId) return ReportDecision.NotCurrentSubtask
        val subtask = subtasks.first { it.subtaskId == subtaskId }
        val record = when (outcome) {
            is MaintenanceOutcome.Completed ->
                targetLedger.complete(targetIdOf(subtask), outcome.result)
            is MaintenanceOutcome.ReadbackHeld ->
                targetLedger.holdReadback(targetIdOf(subtask), outcome.reasonCode)
            is MaintenanceOutcome.Unknown ->
                targetLedger.markUnknown(targetIdOf(subtask), outcome.reasonCode)
            is MaintenanceOutcome.Failed ->
                targetLedger.markFailed(targetIdOf(subtask), outcome.reasonCode)
        }
        currentSubtaskId = null
        return ReportDecision.Recorded(record)
    }

    /** 操作员主动结束在飞目标（零副作用撤出：批准记 ABORTED，目标记 FAILED）。 */
    fun abortCurrentSubtask(reasonCode: String): ReportDecision {
        val current = currentSubtaskId ?: return ReportDecision.NotCurrentSubtask
        val subtask = subtasks.first { it.subtaskId == current }
        approvalLedger.recordAbort(subtask.approvalId)
        val record = targetLedger.markFailed(subtask.targetId, reasonCode)
        currentSubtaskId = null
        return ReportDecision.Recorded(record)
    }

    /**
     * 翻页深度上报（验收用例 4 之一）：接线层扫页找目标时喂入当前页深；
     * 超限立即闩停 PAGINATION_LIMIT_EXCEEDED（停就是停）。
     */
    fun reportPageDepth(depth: Int): Boolean {
        if (halted != null) return true
        if (depth > limits.maxPaginationDepth) {
            latch(
                MaintenanceHalt.StopConditionHit(
                    condition = MaintenanceStopCondition.PAGINATION_LIMIT_EXCEEDED,
                    reason = "the sweep advanced to page depth $depth over the limit " +
                        "${limits.maxPaginationDepth}; halt instead of paging forever",
                ),
            )
            return true
        }
        return false
    }

    // --- 内部 ---

    private fun identityHalt(detail: String): IdentityDecision {
        val subtask = subtasks.firstOrNull { it.subtaskId == currentSubtaskId }
        val halt = MaintenanceHalt.IdentityProofFailed(
            identityReason = detail,
            targetKey = subtask?.key,
        )
        // 身份证明失败的目标记零副作用失败（未触击），运行闩死。
        subtask?.let { targetLedger.markFailed(it.targetId, halt.reasonCode) }
        return IdentityDecision.Halted(latch(halt))
    }

    private fun latch(halt: MaintenanceHalt): MaintenanceHalt {
        halted = halt
        return halt
    }

    private fun targetIdOf(subtask: PerTargetSubtask): String = subtask.targetId
}
