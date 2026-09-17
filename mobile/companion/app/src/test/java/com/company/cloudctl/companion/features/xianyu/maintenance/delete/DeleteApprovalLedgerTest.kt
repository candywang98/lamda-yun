package com.company.cloudctl.companion.features.xianyu.maintenance.delete

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * X10 — 批准清单：逐目标四要素（账号/证据/动作/有效期）、单发确认、
 * 保护期明确拒绝（不排队）、取消闭环 ABORTED_BY_OPERATOR、UNKNOWN 锁保护。
 */
class DeleteApprovalLedgerTest {

    private var now = 1_000L
    private val ledger = DeleteApprovalLedger(clock = { now })

    private val targetKey = DeleteTargetKey(
        accountScope = "xianyu://account/seller-A",
        platformItemId = "7123456789",
    )

    private fun approvedRecord(
        key: DeleteTargetKey = targetKey,
        protectionUntilMs: Long? = null,
    ) = DeleteApprovalRecord(
        approvalId = "apr-${key.identityKey.hashCode().toUInt()}",
        targetKey = key,
        validFromMs = 900,
        validUntilMs = 2_000,
        protectionUntilMs = protectionUntilMs,
    )

    @Test
    fun approvalCarriesAccountEvidenceActionAndValidity() {
        val record = ledger.register(approvedRecord())
        assertEquals(targetKey.accountScope, record.targetKey.accountScope)
        assertEquals("7123456789", record.targetKey.platformItemId)
        assertEquals(DeleteApprovalRecord.ACTION_DELETE_DELISTED, record.action)
        assertTrue(record.validUntilMs > record.validFromMs)
        assertIs<DeleteApprovalDecision.Admitted>(ledger.admit(record.approvalId))
    }

    @Test
    fun compositeTargetKeyFallsBackToAccountScopedIdentity() {
        val composite = DeleteTargetKey(
            accountScope = "xianyu://account/seller-A",
            titleContains = "黄同学漫画二战史2",
            price = "¥45.00",
            listingState = "已下架",
        )
        assertTrue(composite.identityKey.startsWith("composite:xianyu://account/seller-A|"))
        assertEquals(
            composite.identityKey,
            composite.copy().identityKey,
            "the same composite target must key identically",
        )
    }

    @Test
    fun confirmIsIssuedExactlyOnce() {
        val record = ledger.register(approvedRecord())
        val first = assertIs<DeleteApprovalDecision.Issued>(
            ledger.claimConfirmOnce(record.approvalId, taskId = "task-1"),
        )
        assertEquals(1, first.issuance.issuanceSerial)
        assertEquals("task-1", first.issuance.taskId)
        assertEquals(DeleteApprovalState.CONSUMED, ledger.record(record.approvalId)!!.state)
        // 第二次请求：绝不补发（destructiveGate 单发语义镜像）。
        val second = assertIs<DeleteApprovalDecision.Rejected>(
            ledger.claimConfirmOnce(record.approvalId, taskId = "task-1-retry"),
        )
        assertEquals(DeleteApprovalState.CONSUMED, second.state)
        assertEquals(NotDispatchedReason.APPROVAL_NOT_VALID, second.reasonCode)
    }

    @Test
    fun expiryIsAnExplicitRejectionOutsideTheValidityWindow() {
        val record = ledger.register(approvedRecord())
        now = 5_000 // 窗口 900..2000 之外
        val decision = assertIs<DeleteApprovalDecision.Rejected>(ledger.admit(record.approvalId))
        assertEquals(DeleteApprovalState.EXPIRED, decision.state)
        val claim = assertIs<DeleteApprovalDecision.Rejected>(
            ledger.claimConfirmOnce(record.approvalId, taskId = "task-1"),
        )
        assertEquals(DeleteApprovalState.EXPIRED, claim.state)
    }

    @Test
    fun operatorProtectionWindowIsAnExplicitRejectionNotAQueue() {
        val record = ledger.register(approvedRecord(protectionUntilMs = 1_500))
        val decision = assertIs<DeleteApprovalDecision.Rejected>(ledger.admit(record.approvalId))
        assertEquals(DeleteApprovalState.PROTECTION_PERIOD, decision.state)
        assertEquals(ProtectionPeriodReason.APPROVAL_PROTECTION_WINDOW, decision.reasonCode)
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, decision.failureClass)
        // 保护期不是倒计时：到期后也没有任何自动放行的回调——账本没有队列可查。
        now = 1_600
        assertIs<DeleteApprovalDecision.Admitted>(ledger.admit(record.approvalId))
    }

    @Test
    fun unresolvedUnknownLocksTheTargetIntoProtectionUntilOperatorResolves() {
        val record = ledger.register(approvedRecord())
        assertIs<DeleteApprovalDecision.Issued>(ledger.claimConfirmOnce(record.approvalId, "task-1"))
        assertIs<DeleteApprovalDecision.Admitted>(
            ledger.recordDispatchedUnknown(record.approvalId, DispatchedUnknownReason.BADGE_UNREADABLE),
        )
        // 同目标注册新批准 → 保护期明确拒绝（未知任务不自动重新删除的清单侧镜像）。
        val reRegister = assertIs<DeleteApprovalDecision.Rejected>(
            ledger.canRegisterTarget(targetKey),
        )
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, reRegister.failureClass)
        assertEquals(ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT, reRegister.reasonCode)
        // 旧批准自身也不再放行任何确认。
        val admit = assertIs<DeleteApprovalDecision.Rejected>(ledger.admit(record.approvalId))
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, admit.failureClass)
        // 操作员核销后解锁。
        ledger.recordResolved(record.approvalId, evidence = "operator: platformItemId + 截图")
        assertIs<DeleteApprovalDecision.Admitted>(ledger.canRegisterTarget(targetKey))
    }

    @Test
    fun cancelLoopRecordsAbortedByOperatorWithZeroSideEffects() {
        val record = ledger.register(approvedRecord())
        assertIs<DeleteApprovalDecision.Admitted>(ledger.recordAbort(record.approvalId))
        assertEquals(
            DeleteApprovalState.ABORTED_BY_OPERATOR,
            ledger.record(record.approvalId)!!.state,
        )
        // 撤出后不再发放确认；再删除需要新批准。
        val claim = assertIs<DeleteApprovalDecision.Rejected>(
            ledger.claimConfirmOnce(record.approvalId, taskId = "task-1"),
        )
        assertEquals(DeleteApprovalState.ABORTED_BY_OPERATOR, claim.state)
    }

    @Test
    fun aSpentConfirmCannotBeCancelledAfterwards() {
        val record = ledger.register(approvedRecord())
        assertIs<DeleteApprovalDecision.Issued>(ledger.claimConfirmOnce(record.approvalId, "task-1"))
        val abort = assertIs<DeleteApprovalDecision.Rejected>(ledger.recordAbort(record.approvalId))
        assertEquals(DeleteFailureClass.NOT_DISPATCHED, abort.failureClass)
        assertEquals(
            DeleteApprovalState.CONSUMED,
            ledger.record(record.approvalId)!!.state,
            "a spent confirm must be reconciled, never retro-cancelled",
        )
    }

    @Test
    fun targetKeyRequiresEitherPlatformIdOrTitleFragment() {
        val bad = runCatching {
            DeleteTargetKey(accountScope = "xianyu://account/seller-A")
        }
        assertTrue(bad.isFailure, "a faceless target (no id, no title) must be rejected at construction")
    }
}
