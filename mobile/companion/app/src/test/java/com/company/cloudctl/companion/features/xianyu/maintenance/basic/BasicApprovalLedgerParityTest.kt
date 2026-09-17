package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.features.xianyu.maintenance.delete.DeleteApprovalDecision
import com.company.cloudctl.companion.features.xianyu.maintenance.delete.DeleteApprovalLedger
import com.company.cloudctl.companion.features.xianyu.maintenance.delete.DeleteApprovalRecord
import com.company.cloudctl.companion.features.xianyu.maintenance.delete.DeleteFailureClass
import com.company.cloudctl.companion.features.xianyu.maintenance.delete.DeleteTargetKey
import com.company.cloudctl.companion.features.xianyu.maintenance.basic.MaintenanceBasicFixtures as F
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * X11 验收用例 5：与 X10 delete 批准清单的模式一致性（claim-once 语义对齐）。
 *
 * delete 包对本任务只读：本测试把两本账并排跑同一场景，钉死行为等价——
 * 1) 单发：第一次 Issued，第二次永远拒绝；
 * 2) 未核销尝试：admit 明确拒绝且是保护类（无队列无倒计时）；
 * 3) 消费后取消：拒绝（要核销，不是取消）；
 * 4) 操作员核销：终态，之后按终态拒绝。
 */
class BasicApprovalLedgerParityTest {

    private fun x10Ledger(): DeleteApprovalLedger {
        val ledger = DeleteApprovalLedger { F.NOW }
        ledger.register(
            DeleteApprovalRecord(
                approvalId = "x10-apr-1",
                targetKey = DeleteTargetKey(
                    accountScope = F.ACCOUNT,
                    platformItemId = "7123456789",
                ),
                validFromMs = 0,
                validUntilMs = 5_000,
            ),
        )
        return ledger
    }

    private fun x11Ledger(): MaintenanceApprovalLedger {
        val ledger = F.ledger()
        ledger.register(
            F.approval("x11-apr-1", F.key("二战史-01", platformItemId = "7123456789")),
        )
        return ledger
    }

    @Test
    fun claimOnceSemanticsMatchOnBothLedgers() {
        val x10 = x10Ledger()
        val x11 = x11Ledger()

        // 第一次：两本账都发放唯一 issuance。
        assertIs<DeleteApprovalDecision.Issued>(x10.claimConfirmOnce("x10-apr-1", "task-1"))
        assertIs<BasicApprovalDecision.Issued>(x11.claimActionOnce("x11-apr-1", "subtask-1"))

        // 第二次：两本账都拒绝，且拒绝态都是 CONSUMED。
        val x10Second = assertIs<DeleteApprovalDecision.Rejected>(x10.claimConfirmOnce("x10-apr-1", "task-1"))
        val x11Second = assertIs<BasicApprovalDecision.Rejected>(x11.claimActionOnce("x11-apr-1", "subtask-1"))
        assertEquals("CONSUMED", x10Second.state.wire)
        assertEquals(BasicApprovalState.CONSUMED, x11Second.state)
    }

    @Test
    fun unresolvedAttemptBlocksAdmissionOnBothLedgers() {
        val x10 = x10Ledger()
        val x11 = x11Ledger()
        x10.claimConfirmOnce("x10-apr-1", "task-1")
        x11.claimActionOnce("x11-apr-1", "subtask-1")

        val x10Blocked = assertIs<DeleteApprovalDecision.Rejected>(x10.admit("x10-apr-1"))
        val x11Blocked = assertIs<BasicApprovalDecision.Rejected>(x11.admit("x11-apr-1"))

        // X10：保护期分类 + UNRESOLVED_PRIOR_ATTEMPT；X11：同语义镜像。
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, x10Blocked.failureClass)
        assertEquals("UNRESOLVED_PRIOR_ATTEMPT", x10Blocked.reasonCode)
        assertEquals(BasicApprovalReason.UNRESOLVED_PRIOR_ATTEMPT, x11Blocked.reasonCode)
        assertTrue(x11Blocked.protectionHalt)
    }

    @Test
    fun abortAfterConsumeIsRejectedOnBothLedgers() {
        val x10 = x10Ledger()
        val x11 = x11Ledger()
        x10.claimConfirmOnce("x10-apr-1", "task-1")
        x11.claimActionOnce("x11-apr-1", "subtask-1")

        assertIs<DeleteApprovalDecision.Rejected>(x10.recordAbort("x10-apr-1"))
        assertIs<BasicApprovalDecision.Rejected>(x11.recordAbort("x11-apr-1"))
    }

    @Test
    fun operatorResolutionIsTerminalOnBothLedgers() {
        val x10 = x10Ledger()
        val x11 = x11Ledger()
        x10.claimConfirmOnce("x10-apr-1", "task-1")
        x11.claimActionOnce("x11-apr-1", "subtask-1")

        x10.recordResolved("x10-apr-1", evidence = "operator confirmed")
        x11.recordResolved("x11-apr-1", evidence = "operator confirmed")

        val x10After = assertIs<DeleteApprovalDecision.Rejected>(x10.admit("x10-apr-1"))
        val x11After = assertIs<BasicApprovalDecision.Rejected>(x11.admit("x11-apr-1"))
        assertEquals("RESOLVED", x10After.state.wire)
        assertEquals(BasicApprovalState.RESOLVED, x11After.state)
    }
}
