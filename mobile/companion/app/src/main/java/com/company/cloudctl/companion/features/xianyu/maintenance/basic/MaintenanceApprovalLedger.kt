package com.company.cloudctl.companion.features.xianyu.maintenance.basic

/**
 * X11 — 维护批准清单：逐目标一条批准 + claim-once 单发语义。
 *
 * 与 X10 [com.company.cloudctl.companion.features.xianyu.maintenance.delete
 * .DeleteApprovalLedger] 对齐实现（delete 包对本任务只读，不 import 不改写）：
 * 同一状态机骨架（APPROVED → CONSUMED 单发；保护期明确拒绝；取消闭环；
 * UNKNOWN 锁目标；操作员核销解除），但服务于 basic 四类动作，并新增
 * [ApprovalPurpose.OLD_OBJECT_REMOVAL]——编辑重发时旧对象的删除/下架必须
 * 是**显式独立批准**，绝不隐式（任务卡第 3 条铁律，[RelistPlan] 消费）。
 *
 * 三条铁律（与 X10 同一血统）：
 * 1. 一次只发一次确认：[claimActionOnce] 把 APPROVED 推进 CONSUMED 并铸造唯一
 *    issuance；第二次一律 ALREADY_ISSUED 拒绝，本地永不补发。
 * 2. 保护期是明确拒绝：无队列、无倒计时、无到期自动放行；解除唯一路径是
 *    操作员核销（[recordResolved]）。
 * 3. 无时钟：时间由调用方注入（clock/nowMs），纯决策无 IO，落库留给接线层。
 */
enum class BasicApprovalState(val wire: String) {
    APPROVED("APPROVED"),
    CONSUMED("CONSUMED"),
    ABORTED_BY_OPERATOR("ABORTED_BY_OPERATOR"),
    PROTECTION_PERIOD("PROTECTION_PERIOD"),
    EXPIRED("EXPIRED"),
    RESOLVED("RESOLVED"),
}

/** 批准用途：直接动作，或编辑重发场景下旧对象处置的显式独立批准。 */
enum class ApprovalPurpose(val wire: String) {
    DIRECT_ACTION("direct-action"),

    /** 旧对象删除/下架的独立批准——RelistPlan 的硬前提。 */
    OLD_OBJECT_REMOVAL("old-object-removal"),
}

/** 目标键（B13 语义：platformItemId 强身份，或账号域 + 复合可见属性）。 */
data class MaintenanceTargetKey(
    val accountScope: String,
    val platformItemId: String? = null,
    val titleContains: String? = null,
    val price: String? = null,
    val listingState: String? = null,
) {
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

/** 单发发放：绑定 subtaskId + 序号（不可复制）。 */
data class BasicConfirmIssuance(
    val approvalId: String,
    val subtaskId: String,
    val issuanceSerial: Int,
)

/** 批准清单裁决。 */
sealed interface BasicApprovalDecision {
    data class Admitted(val approvalId: String) : BasicApprovalDecision
    data class Rejected(
        val state: BasicApprovalState,
        val reasonCode: String,
        val reason: String,
        val protectionHalt: Boolean = false,
    ) : BasicApprovalDecision
    data class Issued(val issuance: BasicConfirmIssuance) : BasicApprovalDecision
}

/** 批准清单原因码（独立命名，不与 X10 的码混用）。 */
object BasicApprovalReason {
    const val APPROVAL_NOT_VALID = "APPROVAL_NOT_VALID"
    const val ALREADY_ISSUED = "ALREADY_ISSUED"
    const val APPROVAL_PROTECTION_WINDOW = "APPROVAL_PROTECTION_WINDOW"
    const val UNRESOLVED_PRIOR_ATTEMPT = "UNRESOLVED_PRIOR_ATTEMPT"
}

/** 批准行。 */
data class BasicApprovalRecord(
    val approvalId: String,
    val targetKey: MaintenanceTargetKey,
    val action: MaintenanceActionKind,
    val purpose: ApprovalPurpose = ApprovalPurpose.DIRECT_ACTION,
    val validFromMs: Long,
    val validUntilMs: Long,
    val protectionUntilMs: Long? = null,
    val state: BasicApprovalState = BasicApprovalState.APPROVED,
    val issuance: BasicConfirmIssuance? = null,
    val unresolvedAttempt: Int? = null,
) {
    init {
        require(approvalId.isNotBlank()) { "approvalId is required" }
        require(validUntilMs > validFromMs) { "validity window must be non-empty" }
    }
}

/**
 * 维护批准账本（纯内存，对齐 X10 DeleteApprovalLedger 的 claim-once 语义；
 * 一致性由 BasicApprovalLedgerParityTest 与 X10 并行钉死）。
 */
class MaintenanceApprovalLedger(private val clock: () -> Long) {

    private val approvals = linkedMapOf<String, BasicApprovalRecord>()

    fun register(record: BasicApprovalRecord): BasicApprovalRecord {
        require(!approvals.containsKey(record.approvalId)) {
            "approval already enrolled: ${record.approvalId}"
        }
        approvals[record.approvalId] = record
        return record
    }

    fun record(approvalId: String): BasicApprovalRecord? = approvals[approvalId]

    /**
     * 旧对象处置批准查询：同目标 + 指定动作 + OLD_OBJECT_REMOVAL 用途。
     * [RelistPlan] 验证「旧对象删除/下架必须显式独立审批」时消费。
     */
    fun removalApprovalFor(
        targetKey: MaintenanceTargetKey,
        action: MaintenanceActionKind,
    ): BasicApprovalRecord? = approvals.values.firstOrNull {
        it.targetKey.identityKey == targetKey.identityKey &&
            it.action == action &&
            it.purpose == ApprovalPurpose.OLD_OBJECT_REMOVAL
    }

    /** 准入裁决：保护期/过期/已消费/已撤销各自独立拒绝，绝不排队。 */
    fun admit(approvalId: String, nowMs: Long = clock()): BasicApprovalDecision {
        val record = approvals[approvalId] ?: return notFound(approvalId)
        if (record.unresolvedAttempt != null) {
            return rejected(
                record,
                BasicApprovalReason.UNRESOLVED_PRIOR_ATTEMPT,
                "prior confirm attempt #${record.unresolvedAttempt} on approval " +
                    "$approvalId is still UNKNOWN; the operator must resolve it before " +
                    "any new admission (explicit rejection, nothing queued)",
                protectionHalt = true,
            )
        }
        if (record.protectionUntilMs != null && nowMs < record.protectionUntilMs) {
            return rejected(
                record,
                BasicApprovalReason.APPROVAL_PROTECTION_WINDOW,
                "target ${record.targetKey.identityKey} is inside the operator-set " +
                    "protection window until ${record.protectionUntilMs}; explicit rejection",
                protectionHalt = true,
            )
        }
        return when (record.state) {
            BasicApprovalState.APPROVED ->
                if (nowMs < record.validFromMs || nowMs > record.validUntilMs) {
                    rejected(
                        record,
                        BasicApprovalReason.APPROVAL_NOT_VALID,
                        "approval window ${record.validFromMs}..${record.validUntilMs} does " +
                            "not cover now=$nowMs; request a fresh per-target approval",
                    )
                } else {
                    BasicApprovalDecision.Admitted(approvalId)
                }
            BasicApprovalState.CONSUMED -> rejected(
                record,
                BasicApprovalReason.ALREADY_ISSUED,
                "the single confirm issuance for this approval was already spent on " +
                    "subtask ${record.issuance?.subtaskId}; a second strike is never granted",
            )
            BasicApprovalState.ABORTED_BY_OPERATOR -> rejected(
                record,
                BasicApprovalReason.APPROVAL_NOT_VALID,
                "approval was aborted by the operator; re-approve if the action is still wanted",
            )
            BasicApprovalState.PROTECTION_PERIOD -> rejected(
                record,
                BasicApprovalReason.UNRESOLVED_PRIOR_ATTEMPT,
                "approval was registered during a protection period and never became valid",
                protectionHalt = true,
            )
            BasicApprovalState.EXPIRED, BasicApprovalState.RESOLVED -> rejected(
                record,
                BasicApprovalReason.APPROVAL_NOT_VALID,
                "approval is terminal (${record.state.wire}); a new action needs a new approval",
            )
        }
    }

    /**
     * 单发确认：APPROVED 且窗口内 → CONSUMED + 唯一 issuance（绑定 subtaskId）。
     * 任何重复请求拒绝——对齐 X10 claimConfirmOnce / 服务端 destructiveGate 单发。
     */
    fun claimActionOnce(
        approvalId: String,
        subtaskId: String,
        nowMs: Long = clock(),
    ): BasicApprovalDecision {
        val record = approvals[approvalId] ?: return notFound(approvalId)
        if (record.state != BasicApprovalState.APPROVED) {
            return rejected(
                record,
                if (record.state == BasicApprovalState.CONSUMED) {
                    BasicApprovalReason.ALREADY_ISSUED
                } else {
                    BasicApprovalReason.APPROVAL_NOT_VALID
                },
                "approval $approvalId is ${record.state.wire}; no confirm can be issued " +
                    "(single-strike semantics)",
            )
        }
        if (record.unresolvedAttempt != null ||
            (record.protectionUntilMs != null && nowMs < record.protectionUntilMs)
        ) {
            return rejected(
                record,
                BasicApprovalReason.APPROVAL_PROTECTION_WINDOW,
                "target ${record.targetKey.identityKey} is under protection; the confirm " +
                    "cannot be issued (explicit rejection, no queued retry)",
                protectionHalt = true,
            )
        }
        if (nowMs < record.validFromMs || nowMs > record.validUntilMs) {
            return rejected(
                record,
                BasicApprovalReason.APPROVAL_NOT_VALID,
                "approval window does not cover now=$nowMs",
            )
        }
        val issuance = BasicConfirmIssuance(
            approvalId = approvalId,
            subtaskId = subtaskId,
            issuanceSerial = 1,
        )
        approvals[approvalId] = record.copy(
            state = BasicApprovalState.CONSUMED,
            issuance = issuance,
            unresolvedAttempt = 1,
        )
        return BasicApprovalDecision.Issued(issuance)
    }

    /** 取消闭环：只有未发放（APPROVED）的批准可被操作员撤回。 */
    fun recordAbort(approvalId: String): BasicApprovalDecision {
        val record = approvals[approvalId] ?: return notFound(approvalId)
        return if (record.state == BasicApprovalState.APPROVED) {
            approvals[approvalId] = record.copy(state = BasicApprovalState.ABORTED_BY_OPERATOR)
            BasicApprovalDecision.Admitted(approvalId)
        } else {
            rejected(
                record,
                BasicApprovalReason.APPROVAL_NOT_VALID,
                "only an APPROVED (unissued) approval can be aborted; a spent confirm " +
                    "must be reconciled, not cancelled",
            )
        }
    }

    /** 已派发结果未知：保持 CONSUMED + unresolvedAttempt，目标锁保护期，绝不自动重发。 */
    fun recordDispatchedUnknown(approvalId: String): BasicApprovalDecision {
        val record = approvals[approvalId] ?: return notFound(approvalId)
        return if (record.state == BasicApprovalState.CONSUMED) {
            BasicApprovalDecision.Admitted(approvalId)
        } else {
            rejected(
                record,
                BasicApprovalReason.UNRESOLVED_PRIOR_ATTEMPT,
                "only a CONSUMED approval can hold a dispatched-unknown outcome " +
                    "(current state ${record.state.wire})",
                protectionHalt = true,
            )
        }
    }

    /** 操作员核销：解锁目标保护期，批准终态 RESOLVED。 */
    fun recordResolved(approvalId: String, evidence: String): BasicApprovalRecord? {
        require(evidence.isNotBlank()) { "resolution evidence is required" }
        val record = approvals[approvalId] ?: return null
        if (record.state == BasicApprovalState.RESOLVED) return record
        val resolved = record.copy(state = BasicApprovalState.RESOLVED, unresolvedAttempt = null)
        approvals[approvalId] = resolved
        return resolved
    }

    private fun notFound(approvalId: String) = BasicApprovalDecision.Rejected(
        state = BasicApprovalState.EXPIRED,
        reasonCode = BasicApprovalReason.APPROVAL_NOT_VALID,
        reason = "approval $approvalId does not exist; a maintenance action needs a fresh " +
            "per-target approval",
    )

    private fun rejected(
        record: BasicApprovalRecord,
        reasonCode: String,
        reason: String,
        protectionHalt: Boolean = false,
    ) = BasicApprovalDecision.Rejected(
        state = record.state,
        reasonCode = reasonCode,
        reason = reason,
        protectionHalt = protectionHalt,
    )
}
