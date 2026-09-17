package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.features.xianyu.maintenance.basic.MaintenanceBasicFixtures as F
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/** 批准清单：claim-once、保护期明确拒绝、取消闭环、操作员核销。 */
class MaintenanceApprovalLedgerTest {

    private fun freshLedger() = F.ledger()

    private fun registered(
        approvalId: String = "apr-1",
        protectionUntilMs: Long? = null,
    ): Pair<MaintenanceApprovalLedger, MaintenanceTargetKey> {
        val ledger = freshLedger()
        val key = F.key("二战史-01")
        ledger.register(F.approval(approvalId, key, protectionUntilMs = protectionUntilMs))
        return ledger to key
    }

    @Test
    fun claimActionOnceIssuesExactlyOneIssuance() {
        val (ledger, _) = registered("apr-1")
        val first = ledger.claimActionOnce("apr-1", subtaskId = "run-1-s1")
        val issued = assertIs<BasicApprovalDecision.Issued>(first)
        assertEquals("apr-1", issued.issuance.approvalId)
        assertEquals("run-1-s1", issued.issuance.subtaskId)

        val second = ledger.claimActionOnce("apr-1", subtaskId = "run-1-s1-replay")
        val rejected = assertIs<BasicApprovalDecision.Rejected>(second)
        assertEquals(BasicApprovalReason.ALREADY_ISSUED, rejected.reasonCode)
        assertEquals(BasicApprovalState.CONSUMED, rejected.state)
    }

    @Test
    fun protectionWindowIsAnExplicitRejectionNotAQueue() {
        val (ledger, key) = registered("apr-1", protectionUntilMs = F.NOW + 5_000)
        val decision = ledger.admit("apr-1")
        val rejected = assertIs<BasicApprovalDecision.Rejected>(decision)
        assertEquals(BasicApprovalReason.APPROVAL_PROTECTION_WINDOW, rejected.reasonCode)
        assertTrue(rejected.protectionHalt)
        assertEquals(key.identityKey, ledger.record("apr-1")?.targetKey?.identityKey)
        // 保护窗口内 claim 同样拒绝。
        val claim = assertIs<BasicApprovalDecision.Rejected>(ledger.claimActionOnce("apr-1", "s-1"))
        assertEquals(BasicApprovalReason.APPROVAL_PROTECTION_WINDOW, claim.reasonCode)
    }

    @Test
    fun unresolvedAttemptLocksTheTargetUntilOperatorResolves() {
        val (ledger, _) = registered("apr-1")
        ledger.claimActionOnce("apr-1", subtaskId = "s-1") // CONSUMED + unresolvedAttempt=1
        val blocked = assertIs<BasicApprovalDecision.Rejected>(ledger.admit("apr-1"))
        assertEquals(BasicApprovalReason.UNRESOLVED_PRIOR_ATTEMPT, blocked.reasonCode)
        assertTrue(blocked.protectionHalt)

        ledger.recordDispatchedUnknown("apr-1")
        val still = assertIs<BasicApprovalDecision.Rejected>(ledger.admit("apr-1"))
        assertEquals(BasicApprovalReason.UNRESOLVED_PRIOR_ATTEMPT, still.reasonCode)

        ledger.recordResolved("apr-1", evidence = "operator: platformItemId gone from list")
        val after = assertIs<BasicApprovalDecision.Rejected>(ledger.admit("apr-1"))
        assertEquals(BasicApprovalReason.APPROVAL_NOT_VALID, after.reasonCode) // 终态 RESOLVED
        assertEquals(BasicApprovalState.RESOLVED, after.state)
    }

    @Test
    fun abortOnlyWorksBeforeTheConfirmWasSpent() {
        val (ledger, _) = registered("apr-1")
        assertIs<BasicApprovalDecision.Admitted>(ledger.recordAbort("apr-1"))
        assertEquals(BasicApprovalState.ABORTED_BY_OPERATOR, ledger.record("apr-1")?.state)

        val (other, _) = registered("apr-2")
        other.claimActionOnce("apr-2", subtaskId = "s-1")
        val late = assertIs<BasicApprovalDecision.Rejected>(other.recordAbort("apr-2"))
        assertEquals(BasicApprovalReason.APPROVAL_NOT_VALID, late.reasonCode)
    }

    @Test
    fun expiredApprovalIsRejectedWithoutHaltingTheBatch() {
        val ledger = freshLedger()
        val key = F.key("过期品-01")
        ledger.register(
            F.approval("apr-x", key, validFromMs = 0, validUntilMs = 500), // NOW=1000 已过窗
        )
        val rejected = assertIs<BasicApprovalDecision.Rejected>(ledger.admit("apr-x"))
        assertEquals(BasicApprovalReason.APPROVAL_NOT_VALID, rejected.reasonCode)
        assertEquals(false, rejected.protectionHalt)
    }

    @Test
    fun removalApprovalLookupServesTheRelistGate() {
        val ledger = freshLedger()
        val key = F.key("重发品-01")
        ledger.register(
            F.approval(
                "apr-remove",
                key,
                action = MaintenanceActionKind.DELIST,
                purpose = ApprovalPurpose.OLD_OBJECT_REMOVAL,
            ),
        )
        val found = ledger.removalApprovalFor(key, MaintenanceActionKind.DELIST)
        assertEquals("apr-remove", found?.approvalId)
        assertEquals(null, ledger.removalApprovalFor(F.key("另一件-02"), MaintenanceActionKind.DELIST))
    }
}
