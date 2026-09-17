package com.company.cloudctl.companion.features.xianyu.maintenance.delete

import com.company.cloudctl.companion.locators.ItemIdentityEvidence

/**
 * X10 — 删除编排（features 层纯决策；automation 层不改）。
 *
 * 路径按锚点契约（contracts/phase1/xianyu-anchors-20260915 §1/§2，
 * xianyu-maintenance-anchors-20260915）：标题定位进详情 → B13 身份核对 →
 * 管理菜单（语义锚点「管理按钮」→ 文本锚点「删除」）→ 唯一确认框
 * （「您确定要删除这个宝贝吗？」）→ **默认走取消闭环**（先证明能安全到达确认框
 * 并能撤出，再谈删除）→ 单发确认（destructiveGate 单发语义）→ 结果回读。
 *
 * 管理菜单冻结项（§2）：推广宝贝 / 超级擦亮为 **G3 付费项，编排永不触碰**；
 * 智能回复设置 / 编辑不用；本编排只用「删除」与「取消」两个文本锚点。菜单出现
 * 异常 → 点取消/BACK 零副作用退出（契约原文）。
 *
 * 本编排器是纯决策器（无 IO）：事件由 automation 接线层喂入（B13
 * ItemIdentityEvidence / TapAdmissionGate / PublishedCardLocator.verifyDetailTitle
 * 的输出翻译成 [DeleteEvent]），决策告诉接线层下一步；接缝留给主会话。
 */
sealed interface DeleteStepPrimitive {
    val id: String

    /** 列表页身份核对（B13 证据级：platformItemId 或 账号+复合可见属性+唯一命中）。 */
    data object VerifyListIdentity : DeleteStepPrimitive {
        override val id: String get() = "verify-list-identity"
    }

    /** 进详情后复核身份（标题一致 + 无旧窗口/epoch 漂移 + 无布局漂移拦截）。 */
    data object ReverifyDetailIdentity : DeleteStepPrimitive {
        override val id: String get() = "reverify-detail-identity"
    }

    /** 管理菜单验证（「删除」「取消」锚点在场；付费项永不触碰；异常=零副作用退出）。 */
    data object VerifyManageMenu : DeleteStepPrimitive {
        override val id: String get() = "verify-manage-menu"
    }

    /** 打开确认框（菜单文本锚点「删除」→ 居中确认弹窗）。 */
    data object OpenDeleteConfirmDialog : DeleteStepPrimitive {
        override val id: String get() = "open-delete-confirm-dialog"
    }

    /** 确认框唯一性验证（唯一弹窗 + 冻结文本 + 确定/取消齐全）。 */
    data object VerifyConfirmDialog : DeleteStepPrimitive {
        override val id: String get() = "verify-confirm-dialog"
    }

    /** 取消闭环（默认终点）：选「取消」→ 回详情 → 零副作用退出。 */
    data object CloseViaCancel : DeleteStepPrimitive {
        override val id: String get() = "close-via-cancel"
    }

    /** 申请唯一一次确认发放（批准清单 claimConfirmOnce；复合证据需先人工确认）。 */
    data object AwaitConfirmAuthorization : DeleteStepPrimitive {
        override val id: String get() = "await-confirm-authorization"
    }

    /** 执行单发确认（destructiveGate：一次授权+一次单击，UNKNOWN 不重试）。 */
    data object ConfirmDeleteOnce : DeleteStepPrimitive {
        override val id: String get() = "confirm-delete-once"
    }

    /** 结果回读（列表消失 + badge 变化；badge 门禁缺失 → 待核对）。 */
    data object ReadbackResult : DeleteStepPrimitive {
        override val id: String get() = "readback-result"
    }
}

/** 接线层喂入的执行事件（B13/W4 成果输出的翻译目标）。 */
sealed interface DeleteEvent {
    /** B13 身份证据评估结果；null = 连评估都无法进行（无目标 ID/无账号域）。 */
    data class TargetIdentityEvaluated(val evidence: ItemIdentityEvidence?) : DeleteEvent

    /**
     * 详情页身份复核：标题是否匹配、采获窗口/epoch 是否漂移、布局守卫是否拦截
     * （旧窗口与漂移都是「误卡」类的直接形态，fail-closed）。
     */
    data class DetailIdentityChecked(
        val titleMatched: Boolean,
        val windowChanged: Boolean = false,
        val sessionEpochChanged: Boolean = false,
        val layoutDriftBlocked: Boolean = false,
    ) : DeleteEvent

    /** 管理菜单观察：删除/取消锚点在场性 + 异常标记（付费项永不触碰，只观察）。 */
    data class ManageMenuObserved(
        val deleteAnchorPresent: Boolean,
        val cancelAnchorPresent: Boolean,
        val anomaly: Boolean = false,
    ) : DeleteEvent

    /** 确认框观察：唯一性 + 冻结文本匹配。 */
    data class ConfirmDialogObserved(
        val unique: Boolean,
        val textMatches: Boolean,
    ) : DeleteEvent

    /** 取消闭环退出结果（sideEffects 必须为 0 才算闭环干净）。 */
    data class CancelLoopExited(val sideEffects: Int, val backOnDetailOrList: Boolean) : DeleteEvent

    /** 人工身份确认（B13 CompositeConfirmed.humanConfirmationRequired 的回执）。 */
    data object HumanIdentityConfirmed : DeleteEvent

    /** 批准清单的发放裁决（claimConfirmOnce 结果）。 */
    data class AuthorizationDecided(val decision: DeleteApprovalDecision) : DeleteEvent

    /** 单发确认已派发（destructiveGate effect 已执行一次）。 */
    data class StrikeDispatched(val actionKey: String) : DeleteEvent

    /** 服务端台账结果上报回执（A13：APPLIED / UNKNOWN）。 */
    data class StrikeOutcomeReported(
        val status: String,
        val reasonCode: String? = null,
    ) : DeleteEvent

    /** 回读观察（喂 [DeleteReadbackJudge]）。 */
    data class ReadbackObserved(
        val observation: DeleteResultReadback.Observation,
        val evidence: DeleteResultReadback.Evidence = DeleteResultReadback.Evidence(),
    ) : DeleteEvent
}

/** 编排决策。 */
sealed interface DeleteDecision {
    /** 原语通过，推进（finished=true 表示计划走完）。 */
    data class Advance(val next: DeleteStepPrimitive, val finished: Boolean) : DeleteDecision

    /** 复合证据需要人工身份确认（不可逆动作前的 B13 强制门）。 */
    data object WaitHumanIdentityConfirm : DeleteDecision

    /**
     * 零副作用安全退出（菜单/确认框异常：按锚点契约点取消/BACK）。
     * 分类 [DeleteFailureClass.NOT_DISPATCHED]——单击从未发生。
     */
    data class AbortSafely(val record: DeleteFailureRecord) : DeleteDecision

    /**
     * 取消闭环完成：零副作用到达过确认框并撤出。接线层应把批准记
     * ABORTED_BY_OPERATOR（[DeleteApprovalLedger.recordAbort]）。
     */
    data class CancelLoopClosed(val approvalId: String, val sideEffects: Int) : DeleteDecision

    /** 放行唯一一次确认（接线层拿 issuance 去 destructiveGate，绝不自行补发）。 */
    data class AuthorizeStrike(val issuance: DeleteConfirmIssuance) : DeleteDecision

    /** 已派发结果未知：终态挂起（绝不二次派发），回读置待核对，等操作员核销。 */
    data class ReportedUnknown(val record: DeleteFailureRecord) : DeleteDecision

    /** 回读完成（带判定；只有 VERIFIED_DELETED 才允许记机器成功）。 */
    data class Completed(val verdict: DeleteReadbackVerdict) : DeleteDecision

    /** 分类学阻断（误卡/未派发/保护期；含原因码，fail-closed，绝不触击）。 */
    data class Blocked(val record: DeleteFailureRecord) : DeleteDecision
}

/**
 * 删除编排器：默认取消闭环计划 / 删除计划。事件驱动、纯决策。
 *
 * 重放防护：确认单击派发后（dispatched 闩）或 UNKNOWN 上报后，任何要求重新派发
 * 的事件一律 [DeleteDecision.Blocked]（PROTECTION_PERIOD / UNRESOLVED_PRIOR_ATTEMPT）
 * ——「未知任务不自动重新删除」在编排器侧的硬闩。
 */
class DeleteOrchestrator(
    private val plan: List<DeleteStepPrimitive>,
    private val approvalId: String,
    private val taskId: String? = null,
) {
    init {
        require(plan.isNotEmpty()) { "delete plan must not be empty" }
    }

    private var index: Int = 0
    private var waitingHuman: Boolean = false
    private var dispatched: Boolean = false
    private var unknownReported: Boolean = false
    private var terminal: Boolean = false

    val current: DeleteStepPrimitive get() = plan[index]

    /** 组合计划：取消闭环（默认排练）。 */
    companion object {
        val CANCEL_LOOP_PLAN: List<DeleteStepPrimitive> = listOf(
            DeleteStepPrimitive.VerifyListIdentity,
            DeleteStepPrimitive.ReverifyDetailIdentity,
            DeleteStepPrimitive.VerifyManageMenu,
            DeleteStepPrimitive.OpenDeleteConfirmDialog,
            DeleteStepPrimitive.VerifyConfirmDialog,
            DeleteStepPrimitive.CloseViaCancel,
        )

        /** 删除计划：取消闭环前缀 + 单发确认 + 回读。 */
        val DELETE_PLAN: List<DeleteStepPrimitive> = CANCEL_LOOP_PLAN.dropLast(1) + listOf(
            DeleteStepPrimitive.AwaitConfirmAuthorization,
            DeleteStepPrimitive.ConfirmDeleteOnce,
            DeleteStepPrimitive.ReadbackResult,
        )
    }

    fun submit(event: DeleteEvent): DeleteDecision {
        check(!terminal) { "orchestrator is terminal; build a new run with a fresh approval" }
        // 重放防护：已派发/已 UNKNOWN 后，除结果上报与回读外的一切事件都不得再推进。
        if (unknownReported) {
            return DeleteDecision.Blocked(
                DeleteFailureRecord(
                    failureClass = DeleteFailureClass.PROTECTION_PERIOD,
                    reasonCode = ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
                    reason = "strike outcome is UNKNOWN and unresolver-reported; no further " +
                        "steps run until the operator resolves it (no auto re-delete)",
                    taskId = taskId,
                ),
            )
        }
        if (waitingHuman && event !is DeleteEvent.HumanIdentityConfirmed) {
            return DeleteDecision.WaitHumanIdentityConfirm
        }
        val step = plan[index]
        return when (event) {
            is DeleteEvent.TargetIdentityEvaluated ->
                if (step == DeleteStepPrimitive.VerifyListIdentity) onIdentity(event.evidence)
                else unexpected(step)
            is DeleteEvent.DetailIdentityChecked ->
                if (step == DeleteStepPrimitive.ReverifyDetailIdentity) onDetail(event)
                else unexpected(step)
            is DeleteEvent.ManageMenuObserved ->
                if (step == DeleteStepPrimitive.VerifyManageMenu) onMenu(event)
                else unexpected(step)
            is DeleteEvent.ConfirmDialogObserved ->
                // 两次观察：第一次=弹窗已打开（presence），第二次=唯一性+冻结文本验证。
                // 任一次异常都零副作用退出。
                if (step == DeleteStepPrimitive.OpenDeleteConfirmDialog ||
                    step == DeleteStepPrimitive.VerifyConfirmDialog
                ) {
                    onDialog(event)
                } else {
                    unexpected(step)
                }
            is DeleteEvent.CancelLoopExited ->
                if (step == DeleteStepPrimitive.CloseViaCancel) onCancelLoop(event)
                else unexpected(step)
            is DeleteEvent.HumanIdentityConfirmed ->
                if (waitingHuman) {
                    waitingHuman = false
                    advance()
                } else {
                    unexpected(step)
                }
            is DeleteEvent.AuthorizationDecided ->
                if (step == DeleteStepPrimitive.AwaitConfirmAuthorization) onAuthorization(event)
                else unexpected(step)
            is DeleteEvent.StrikeDispatched ->
                if (step == DeleteStepPrimitive.ConfirmDeleteOnce && !dispatched) {
                    dispatched = true
                    // 派发即闩：等待结果上报事件（不推进原语）。
                    DeleteDecision.Advance(step, finished = false)
                } else if (dispatched) {
                    DeleteDecision.Blocked(
                        DeleteFailureRecord(
                            failureClass = DeleteFailureClass.PROTECTION_PERIOD,
                            reasonCode = ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
                            reason = "a second strike dispatch was offered after the single " +
                                "confirm already ran; single-strike semantics forbid it",
                            taskId = taskId,
                        ),
                    )
                } else {
                    unexpected(step)
                }
            is DeleteEvent.StrikeOutcomeReported ->
                if (step == DeleteStepPrimitive.ConfirmDeleteOnce && dispatched) onOutcome(event)
                else if (!dispatched) {
                    DeleteDecision.Blocked(
                        DeleteFailureRecord(
                            failureClass = DeleteFailureClass.NOT_DISPATCHED,
                            reasonCode = NotDispatchedReason.INTENT_REJECTED,
                            reason = "an outcome arrived without any dispatched strike; " +
                                "nothing may be concluded from it",
                            taskId = taskId,
                        ),
                    )
                } else {
                    unexpected(step)
                }
            is DeleteEvent.ReadbackObserved ->
                if (step == DeleteStepPrimitive.ReadbackResult) {
                    val verdict = DeleteReadbackJudge.judge(event.observation)
                    terminal = true
                    DeleteDecision.Completed(verdict)
                } else {
                    unexpected(step)
                }
        }
    }

    // --- 步骤裁决 ---

    private fun onIdentity(evidence: ItemIdentityEvidence?): DeleteDecision = when (evidence) {
        null -> blockedWrongTarget(
            WrongTargetReason.NO_TARGET_ID,
            "identity evaluation could not even run: no target id and no account-scoped " +
                "composite (a faceless target is never deletable)",
        )
        is ItemIdentityEvidence.PlatformItemId -> advance()
        is ItemIdentityEvidence.CompositeConfirmed -> {
            // B13：复合证据弱于平台 ID，人工确认是强制门。
            waitingHuman = true
            DeleteDecision.WaitHumanIdentityConfirm
        }
        is ItemIdentityEvidence.Insufficient -> {
            val reasonText = evidence.reason
            val code = when {
                reasonText.contains("distinct cards") && !reasonText.contains("ZERO") ->
                    WrongTargetReason.SAME_TITLE_AMBIGUITY
                reasonText.contains("account scope") -> WrongTargetReason.NO_TARGET_ID
                else -> WrongTargetReason.INSUFFICIENT_EVIDENCE
            }
            blockedWrongTarget(code, reasonText)
        }
    }

    private fun onDetail(event: DeleteEvent.DetailIdentityChecked): DeleteDecision = when {
        event.windowChanged || event.sessionEpochChanged -> blockedWrongTarget(
            WrongTargetReason.STALE_WINDOW,
            "the detail-page capture belongs to another accessibility window/session epoch; " +
                "its coordinates are void (B13 TapAdmissionGate lineage)",
        )
        event.layoutDriftBlocked -> blockedWrongTarget(
            WrongTargetReason.LAYOUT_DRIFT_BLOCKED,
            "the list layout drifted past the guard budget; old coordinates would hit the " +
                "wrong card (P09 second failure prototype)",
        )
        !event.titleMatched -> blockedWrongTarget(
            WrongTargetReason.DETAIL_TITLE_MISMATCH,
            "the opened detail page title does not match the target located on the list " +
                "(wrong card entered)",
        )
        else -> advance()
    }

    private fun onMenu(event: DeleteEvent.ManageMenuObserved): DeleteDecision =
        if (event.anomaly || !event.deleteAnchorPresent || !event.cancelAnchorPresent) {
            // 锚点契约：菜单异常 → 取消/BACK 零副作用退出（付费项从不触碰）。
            DeleteDecision.AbortSafely(
                DeleteFailureRecord(
                    failureClass = DeleteFailureClass.NOT_DISPATCHED,
                    reasonCode = NotDispatchedReason.MENU_NOT_VERIFIED,
                    reason = "manage menu did not verify (anomaly=${event.anomaly}, " +
                        "delete=${event.deleteAnchorPresent}, cancel=${event.cancelAnchorPresent}); " +
                        "exit via cancel/BACK with zero side effects",
                    taskId = taskId,
                ),
            )
        } else {
            advance()
        }

    private fun onDialog(event: DeleteEvent.ConfirmDialogObserved): DeleteDecision =
        if (!event.unique || !event.textMatches) {
            DeleteDecision.AbortSafely(
                DeleteFailureRecord(
                    failureClass = DeleteFailureClass.NOT_DISPATCHED,
                    reasonCode = NotDispatchedReason.CONFIRM_DIALOG_NOT_UNIQUE,
                    reason = "the delete confirm dialog was not the single frozen " +
                        "「您确定要删除这个宝贝吗？」 dialog (unique=${event.unique}, " +
                        "text=${event.textMatches}); exit via cancel with zero side effects",
                    taskId = taskId,
                ),
            )
        } else {
            advance()
        }

    private fun onCancelLoop(event: DeleteEvent.CancelLoopExited): DeleteDecision =
        if (event.sideEffects == 0 && event.backOnDetailOrList) {
            terminal = true
            DeleteDecision.CancelLoopClosed(approvalId = approvalId, sideEffects = 0)
        } else {
            DeleteDecision.Blocked(
                DeleteFailureRecord(
                    failureClass = DeleteFailureClass.NOT_DISPATCHED,
                    reasonCode = NotDispatchedReason.CANCEL_LOOP_NOT_CLEAN,
                    reason = "cancel loop exited with sideEffects=${event.sideEffects}, " +
                        "backOnDetailOrList=${event.backOnDetailOrList}; not a clean retreat",
                    taskId = taskId,
                ),
            )
        }

    private fun onAuthorization(event: DeleteEvent.AuthorizationDecided): DeleteDecision =
        when (val decision = event.decision) {
            is DeleteApprovalDecision.Issued -> {
                advance()
                DeleteDecision.AuthorizeStrike(decision.issuance)
            }
            is DeleteApprovalDecision.Rejected -> DeleteDecision.Blocked(
                DeleteFailureRecord(
                    failureClass = decision.failureClass,
                    reasonCode = decision.reasonCode,
                    reason = decision.reason,
                    taskId = taskId,
                ),
            )
            is DeleteApprovalDecision.Admitted -> unexpected(plan[index])
        }

    private fun onOutcome(event: DeleteEvent.StrikeOutcomeReported): DeleteDecision =
        when (event.status) {
            "APPLIED" -> advance()
            "UNKNOWN" -> {
                unknownReported = true
                DeleteDecision.ReportedUnknown(
                    DeleteFailureRecord(
                        failureClass = DeleteFailureClass.DISPATCHED_UNKNOWN,
                        reasonCode = event.reasonCode
                            ?: DispatchedUnknownReason.DIALOG_DISMISSAL_UNCAPTURED,
                        reason = "the single confirm was dispatched but its result evidence is " +
                            "not authoritative; UNKNOWN is terminal for this run, the readback " +
                            "holds PENDING_VERIFICATION and the operator reconciles",
                        taskId = taskId,
                    ),
                )
            }
            else -> DeleteDecision.Blocked(
                DeleteFailureRecord(
                    failureClass = DeleteFailureClass.DISPATCHED_UNKNOWN,
                    reasonCode = DispatchedUnknownReason.READBACK_INCONCLUSIVE,
                    reason = "unexpected strike outcome status '${event.status}'",
                    taskId = taskId,
                ),
            )
        }

    // --- 工具 ---

    private fun blockedWrongTarget(code: String, reason: String): DeleteDecision.Blocked {
        terminal = true
        return DeleteDecision.Blocked(
            DeleteFailureRecord(
                failureClass = DeleteFailureClass.WRONG_TARGET,
                reasonCode = code,
                reason = reason,
                taskId = taskId,
            ),
        )
    }

    private fun advance(): DeleteDecision {
        val next = plan.getOrNull(index + 1)
        if (next == null) {
            terminal = true
            return DeleteDecision.Advance(plan.last(), finished = true)
        }
        index += 1
        return DeleteDecision.Advance(next, finished = false)
    }

    private fun unexpected(step: DeleteStepPrimitive): DeleteDecision.Blocked {
        terminal = true
        return DeleteDecision.Blocked(
            DeleteFailureRecord(
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
                reasonCode = NotDispatchedReason.UNEXPECTED_EVENT,
                reason = "event does not belong to step ${step.id}",
                taskId = taskId,
            ),
        )
    }
}
