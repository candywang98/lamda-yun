package com.company.cloudctl.companion.features.xianyu.maintenance.delete

/**
 * X10 — 删除批准清单（设备侧纯决策；落库/对账接线留给主会话）。
 *
 * 逐目标一条批准，含四要素：账号（accountScope）/证据（identityEvidence，B13
 * 级别）/动作（action，冻结为 delete-delisted）/有效期（validFromMs..validUntilMs）。
 *
 * 三条铁律：
 * 1. **一次只发一次确认**：[claimConfirmOnce] 把批准从 APPROVED 推进到 CONSUMED 并
 *    铸造唯一 issuance（绑定 taskId）。第二次请求一律 ALREADY_ISSUED 拒绝——与服务端
 *    destructiveGate 单发语义（intent 只 AUTHORIZED 一次、hasRecordedAction 只会
 *    RECONCILE）互为镜像；本地永不补发。
 * 2. **保护期是明确拒绝**：[admit] 在保护窗口内返回 PROTECTION_PERIOD 拒绝（一个
 *    状态，不是一个倒计时）。没有队列、没有「到期自动重试」；解除的唯一路径是
 *    操作员核销旧尝试（[recordResolved]）。UNKNOWN 的旧批准把目标锁进保护期。
 * 3. **取消闭环记账**：[recordAbort] 把 APPROVED 批准记为 ABORTED_BY_OPERATOR
 *    （到达确认框后选择取消、零副作用退出的排练闭环）。
 */
enum class DeleteApprovalState(val wire: String) {
    /** 已批准，未发放确认。 */
    APPROVED("APPROVED"),

    /** 唯一一次确认已发放（终态：不再补发）。 */
    CONSUMED("CONSUMED"),

    /** 取消闭环完成，操作员撤出（终态，零副作用）。 */
    ABORTED_BY_OPERATOR("ABORTED_BY_OPERATOR"),

    /** 保护期明确拒绝（终态：本条拒绝本身留痕，但不会转正）。 */
    PROTECTION_PERIOD("PROTECTION_PERIOD"),

    /** 有效期已过（终态）。 */
    EXPIRED("EXPIRED"),

    /** 结果已核销（终态：成功或操作员确认的终局）。 */
    RESOLVED("RESOLVED"),
}

/** 批准目标键：platformItemId 强身份，或账号域 + 复合可见属性（B13 语义）。 */
data class DeleteTargetKey(
    val accountScope: String,
    val platformItemId: String? = null,
    val titleContains: String? = null,
    val price: String? = null,
    val listingState: String? = null,
) {
    /** 同一目标的判定键：platformItemId 优先；否则账号 + 标题 + 价格 + 状态。 */
    val identityKey: String
        get() {
            val realId = platformItemId?.takeIf { it.isNotBlank() }
            return if (realId != null) {
                "id:$realId"
            } else {
                "composite:${accountScope}|${titleContains ?: ""}|${price ?: ""}|${listingState ?: ""}"
            }
        }

    init {
        require(accountScope.isNotBlank()) { "account scope is required: identity is account-scoped" }
        require(platformItemId != null || !titleContains.isNullOrBlank()) {
            "target key needs a platformItemId or a non-blank title fragment (no faceless target)"
        }
    }
}

/** 一次确认发放（单发）：绑定 taskId + 不可复制的 issuance 序号。 */
data class DeleteConfirmIssuance(
    val approvalId: String,
    val taskId: String,
    val issuanceSerial: Int,
)

/** [DeleteApprovalLedger] 的准入/发放裁决。 */
sealed interface DeleteApprovalDecision {
    /** 准入通过（或查看时有效）：批准可用。 */
    data class Admitted(val approvalId: String) : DeleteApprovalDecision

    /** 明确拒绝（含状态与分类学原因码；无排队、无倒计时）。 */
    data class Rejected(
        val state: DeleteApprovalState,
        val reasonCode: String,
        val reason: String,
        val failureClass: DeleteFailureClass,
    ) : DeleteApprovalDecision

    /** 单发成功：这是该批准唯一一次确认发放。 */
    data class Issued(val issuance: DeleteConfirmIssuance) : DeleteApprovalDecision
}

/** 设备侧批准账本行（纯内存实现，落库接缝留给主会话）。 */
data class DeleteApprovalRecord(
    val approvalId: String,
    val targetKey: DeleteTargetKey,
    /** 冻结动作：本专项只有 delisted 商品的删除。 */
    val action: String = ACTION_DELETE_DELISTED,
    val validFromMs: Long,
    val validUntilMs: Long,
    /** 操作员显式设定的保护窗口（窗口内 admit 明确拒绝）。 */
    val protectionUntilMs: Long? = null,
    val state: DeleteApprovalState = DeleteApprovalState.APPROVED,
    val issuance: DeleteConfirmIssuance? = null,
    /** 已派发但未核销（UNKNOWN）的尝试号；保护期由此推导。 */
    val unresolvedAttempt: Int? = null,
) {
    init {
        require(approvalId.isNotBlank()) { "approvalId is required" }
        require(validUntilMs > validFromMs) { "validity window must be non-empty" }
        require(action == ACTION_DELETE_DELISTED) { "only $ACTION_DELETE_DELISTED is approved here" }
    }

    companion object {
        const val ACTION_DELETE_DELISTED = "delete-delisted"
    }
}

/**
 * 删除批准账本：准入（含保护期明确拒绝）、单发确认、取消闭环、UNKNOWN 锁保护、
 * 操作员核销。全部纯决策，无 IO 无时钟（时间由调用方注入 nowMs）。
 */
class DeleteApprovalLedger(private val clock: () -> Long) {

    private val approvals = linkedMapOf<String, DeleteApprovalRecord>()

    fun register(record: DeleteApprovalRecord): DeleteApprovalRecord {
        require(!approvals.containsKey(record.approvalId)) {
            "approval already enrolled: ${record.approvalId}"
        }
        approvals[record.approvalId] = record
        return record
    }

    fun record(approvalId: String): DeleteApprovalRecord? = approvals[approvalId]

    /**
     * 准入裁决：批准在该时刻是否可用。保护期/过期/已消费/已撤销 各自独立拒绝，
     * 绝不归并；被拒的批准不会进入任何等待队列（本账本根本没有队列）。
     */
    fun admit(approvalId: String, nowMs: Long = clock()): DeleteApprovalDecision {
        val record = approvals[approvalId]
            ?: return DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.EXPIRED,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "approval $approvalId does not exist; a delete needs a fresh per-target approval",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
        // 保护期：同目标旧尝试未核销，或操作员设定的保护窗口未过——明确拒绝。
        if (record.unresolvedAttempt != null || record.targetUnderProtection(nowMs)) {
            val prior = record.unresolvedAttempt != null
            return DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.PROTECTION_PERIOD,
                reasonCode = if (prior) {
                    ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT
                } else {
                    ProtectionPeriodReason.APPROVAL_PROTECTION_WINDOW
                },
                reason = if (prior) {
                    "prior confirm attempt #${record.unresolvedAttempt} is still UNKNOWN; " +
                        "operator must resolve it before any new delete admission"
                } else {
                    "target is inside the operator-set protection window until " +
                        "${record.protectionUntilMs}; explicit rejection, no queued retry"
                },
                failureClass = DeleteFailureClass.PROTECTION_PERIOD,
            )
        }
        return when (record.state) {
            DeleteApprovalState.APPROVED -> {
                if (nowMs < record.validFromMs || nowMs > record.validUntilMs) {
                    DeleteApprovalDecision.Rejected(
                        state = DeleteApprovalState.EXPIRED,
                        reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                        reason = "approval window ${record.validFromMs}..${record.validUntilMs} " +
                            "does not cover now=$nowMs; request a fresh approval",
                        failureClass = DeleteFailureClass.NOT_DISPATCHED,
                    )
                } else {
                    DeleteApprovalDecision.Admitted(record.approvalId)
                }
            }
            DeleteApprovalState.CONSUMED -> DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.CONSUMED,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "the single confirm issuance for this approval was already spent",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
            DeleteApprovalState.ABORTED_BY_OPERATOR -> DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.ABORTED_BY_OPERATOR,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "approval was aborted by the operator (cancel loop); re-approve if a delete is still wanted",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
            DeleteApprovalState.PROTECTION_PERIOD -> DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.PROTECTION_PERIOD,
                reasonCode = ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
                reason = "approval was registered during a protection period and never became valid",
                failureClass = DeleteFailureClass.PROTECTION_PERIOD,
            )
            DeleteApprovalState.EXPIRED, DeleteApprovalState.RESOLVED -> DeleteApprovalDecision.Rejected(
                state = record.state,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "approval is terminal (${record.state.wire}); a new delete needs a new approval",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
        }
    }

    /**
     * 是否允许同目标注册新批准：目标上存在 CONSUMED 且未核销的旧批准 → 保护期
     * 明确拒绝（不排队）。这是「未知任务不自动重新删除」的清单侧镜像。
     */
    fun canRegisterTarget(targetKey: DeleteTargetKey): DeleteApprovalDecision {
        val conflict = approvals.values.firstOrNull {
            it.targetKey.identityKey == targetKey.identityKey &&
                (it.state == DeleteApprovalState.CONSUMED && it.unresolvedAttempt != null ||
                    it.state == DeleteApprovalState.PROTECTION_PERIOD)
        }
        return if (conflict != null) {
            DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.PROTECTION_PERIOD,
                reasonCode = ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
                reason = "target ${targetKey.identityKey} has unresolved attempt " +
                    "#${conflict.unresolvedAttempt ?: 0} on approval ${conflict.approvalId}; " +
                    "explicit rejection, nothing is queued",
                failureClass = DeleteFailureClass.PROTECTION_PERIOD,
            )
        } else {
            DeleteApprovalDecision.Admitted(targetKey.identityKey)
        }
    }

    /**
     * 单发确认：APPROVED 且窗口内 → CONSUMED + 唯一 issuance。任何重复请求
     * ALREADY_ISSUED / 状态不符拒绝——对齐 destructiveGate「一次授权」。
     */
    fun claimConfirmOnce(
        approvalId: String,
        taskId: String,
        nowMs: Long = clock(),
    ): DeleteApprovalDecision {
        val record = approvals[approvalId]
            ?: return DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.EXPIRED,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "approval $approvalId does not exist",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
        if (record.targetUnderProtection(nowMs)) {
            return DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.PROTECTION_PERIOD,
                reasonCode = ProtectionPeriodReason.APPROVAL_PROTECTION_WINDOW,
                reason = "target is inside the operator-set protection window; the confirm " +
                    "cannot be issued (explicit rejection, no queued retry)",
                failureClass = DeleteFailureClass.PROTECTION_PERIOD,
            )
        }
        when (record.state) {
            DeleteApprovalState.APPROVED -> {
                if (nowMs < record.validFromMs || nowMs > record.validUntilMs) {
                    return DeleteApprovalDecision.Rejected(
                        state = DeleteApprovalState.EXPIRED,
                        reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                        reason = "approval window does not cover now=$nowMs",
                        failureClass = DeleteFailureClass.NOT_DISPATCHED,
                    )
                }
                val issuance = DeleteConfirmIssuance(
                    approvalId = approvalId,
                    taskId = taskId,
                    issuanceSerial = 1,
                )
                approvals[approvalId] = record.copy(
                    state = DeleteApprovalState.CONSUMED,
                    issuance = issuance,
                    unresolvedAttempt = 1,
                )
                return DeleteApprovalDecision.Issued(issuance)
            }
            DeleteApprovalState.CONSUMED -> return DeleteApprovalDecision.Rejected(
                state = DeleteApprovalState.CONSUMED,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "confirm already issued once for task ${record.issuance?.taskId}; " +
                    "a second strike is never granted (single-strike semantics)",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
            else -> return DeleteApprovalDecision.Rejected(
                state = record.state,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "approval is ${record.state.wire}; no confirm can be issued",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
        }
    }

    /**
     * 取消闭环完成：到达确认框后选择取消、零副作用退出。APPROVED →
     * ABORTED_BY_OPERATOR（确认已发放后不允许「事后取消」——那要走 UNKNOWN/核销）。
     */
    fun recordAbort(approvalId: String): DeleteApprovalDecision {
        val record = approvals[approvalId] ?: return notFound(approvalId)
        return when (record.state) {
            DeleteApprovalState.APPROVED -> {
                approvals[approvalId] = record.copy(state = DeleteApprovalState.ABORTED_BY_OPERATOR)
                DeleteApprovalDecision.Admitted(approvalId)
            }
            else -> DeleteApprovalDecision.Rejected(
                state = record.state,
                reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
                reason = "only an APPROVED (unissued) approval can be aborted by the operator; " +
                    "a spent confirm must be reconciled, not cancelled",
                failureClass = DeleteFailureClass.NOT_DISPATCHED,
            )
        }
    }

    /**
     * 已派发结果未知：CONSUMED 批准挂起（unresolvedAttempt 保持），目标进入
     * 保护期直到 [recordResolved]。绝不自动重新发放。
     */
    fun recordDispatchedUnknown(approvalId: String, reasonCode: String): DeleteApprovalDecision {
        val record = approvals[approvalId] ?: return notFound(approvalId)
        return when (record.state) {
            DeleteApprovalState.CONSUMED -> {
                // 状态保持 CONSUMED；未核销尝试号确保保护期生效。
                DeleteApprovalDecision.Admitted(approvalId)
            }
            else -> DeleteApprovalDecision.Rejected(
                state = record.state,
                reasonCode = reasonCode,
                reason = "only a CONSUMED approval can hold a dispatched-unknown outcome " +
                    "(current state ${record.state.wire})",
                failureClass = DeleteFailureClass.DISPATCHED_UNKNOWN,
            )
        }
    }

    /** 操作员核销（成功确认 / NOT_SUBMITTED 确认）：解锁目标保护期，批准终态。 */
    fun recordResolved(approvalId: String, evidence: String): DeleteApprovalRecord? {
        require(evidence.isNotBlank()) { "resolution evidence is required" }
        val record = approvals[approvalId] ?: return null
        if (record.state == DeleteApprovalState.RESOLVED) return record
        val resolved = record.copy(
            state = DeleteApprovalState.RESOLVED,
            unresolvedAttempt = null,
        )
        approvals[approvalId] = resolved
        return resolved
    }

    private fun notFound(approvalId: String) = DeleteApprovalDecision.Rejected(
        state = DeleteApprovalState.EXPIRED,
        reasonCode = NotDispatchedReason.APPROVAL_NOT_VALID,
        reason = "approval $approvalId does not exist",
        failureClass = DeleteFailureClass.NOT_DISPATCHED,
    )

    private fun DeleteApprovalRecord.targetUnderProtection(nowMs: Long): Boolean =
        protectionUntilMs != null && nowMs < protectionUntilMs
}
