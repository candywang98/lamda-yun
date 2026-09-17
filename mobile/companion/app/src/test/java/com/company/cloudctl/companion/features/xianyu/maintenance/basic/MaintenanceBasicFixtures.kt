package com.company.cloudctl.companion.features.xianyu.maintenance.basic

/** X11 basic/ 测试共用夹具（纯内存，无 IO 无时钟；NOW 由调用方注入）。 */
internal object MaintenanceBasicFixtures {

    const val NOW: Long = 1_000L
    const val ACCOUNT = "xianyu://account/seller-A"

    fun key(title: String, platformItemId: String? = null): MaintenanceTargetKey =
        MaintenanceTargetKey(
            accountScope = ACCOUNT,
            platformItemId = platformItemId,
            titleContains = if (platformItemId == null) title else null,
        )

    fun ledger(): MaintenanceApprovalLedger = MaintenanceApprovalLedger { NOW }

    fun approval(
        approvalId: String,
        targetKey: MaintenanceTargetKey,
        action: MaintenanceActionKind = MaintenanceActionKind.DELIST,
        purpose: ApprovalPurpose = ApprovalPurpose.DIRECT_ACTION,
        state: BasicApprovalState = BasicApprovalState.APPROVED,
        validFromMs: Long = 0L,
        validUntilMs: Long = 5_000L,
        protectionUntilMs: Long? = null,
        unresolvedAttempt: Int? = null,
    ): BasicApprovalRecord = BasicApprovalRecord(
        approvalId = approvalId,
        targetKey = targetKey,
        action = action,
        purpose = purpose,
        validFromMs = validFromMs,
        validUntilMs = validUntilMs,
        protectionUntilMs = protectionUntilMs,
        state = state,
        unresolvedAttempt = unresolvedAttempt,
    )

    fun delistTarget(
        targetId: String,
        title: String,
        approvalId: String = "apr-$targetId",
    ): MaintenanceBatchTarget = MaintenanceBatchTarget(
        targetId = targetId,
        key = key(title),
        action = MaintenanceActionKind.DELIST,
        approvalId = approvalId,
    )
}
