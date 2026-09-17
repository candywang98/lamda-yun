package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.features.xianyu.publish.PublishCompletionBoundary
import com.company.cloudctl.companion.features.xianyu.maintenance.basic.MaintenanceBasicFixtures as F
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * X11 任务卡第 3 条：编辑重发复用发布语义（P10 边界），旧对象删除/下架
 * 绝不是隐式步骤——需要显式独立审批。
 */
class RelistPlanTest {

    private fun ledgerWithRemovalApproval(
        approvalId: String = "apr-remove",
        key: MaintenanceTargetKey = F.key("重发品-01"),
        action: MaintenanceActionKind = MaintenanceActionKind.DELIST,
        purpose: ApprovalPurpose = ApprovalPurpose.OLD_OBJECT_REMOVAL,
        state: BasicApprovalState = BasicApprovalState.APPROVED,
    ): MaintenanceApprovalLedger {
        val ledger = F.ledger()
        ledger.register(F.approval(approvalId, key, action = action, purpose = purpose, state = state))
        return ledger
    }

    @Test
    fun implicitOldObjectRemovalIsForbidden() {
        val key = F.key("重发品-01")
        val invalid = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.AUTO_FILL_HUMAN_COMMIT,
            disposition = OldObjectDisposition.DELIST_OLD,
            removalApprovalId = null, // 隐式下架旧对象：铁律拒绝
            approvals = ledgerWithRemovalApproval(key = key),
        )
        val rejection = assertIs<RelistPlanValidation.Invalid>(invalid)
        assertEquals(RelistPlanError.IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN, rejection.error)

        val invalidDelete = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.FULL_AUTO,
            disposition = OldObjectDisposition.DELETE_OLD,
            removalApprovalId = null,
            approvals = ledgerWithRemovalApproval(key = key),
        )
        assertEquals(
            RelistPlanError.IMPLICIT_OLD_OBJECT_REMOVAL_FORBIDDEN,
            assertIs<RelistPlanValidation.Invalid>(invalidDelete).error,
        )
    }

    @Test
    fun explicitIndependentRemovalApprovalUnlocksThePlan() {
        val key = F.key("重发品-01")
        val valid = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.AUTO_FILL_HUMAN_PRICE,
            disposition = OldObjectDisposition.DELIST_OLD,
            removalApprovalId = "apr-remove",
            approvals = ledgerWithRemovalApproval(key = key),
        )
        assertIs<RelistPlanValidation.Valid>(valid)
    }

    @Test
    fun removalApprovalMustMatchPurposeTargetAndAction() {
        val key = F.key("重发品-01")
        // 用途不对（直接动作批准冒充 removal 批准）。
        val wrongPurpose = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.FULL_AUTO,
            disposition = OldObjectDisposition.DELIST_OLD,
            removalApprovalId = "apr-remove",
            approvals = ledgerWithRemovalApproval(key = key, purpose = ApprovalPurpose.DIRECT_ACTION),
        )
        assertEquals(
            RelistPlanError.REMOVAL_APPROVAL_NOT_MATCHED,
            assertIs<RelistPlanValidation.Invalid>(wrongPurpose).error,
        )
        // 目标不符（批准盖的是另一件）。
        val wrongTarget = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.FULL_AUTO,
            disposition = OldObjectDisposition.DELIST_OLD,
            removalApprovalId = "apr-remove",
            approvals = ledgerWithRemovalApproval(key = F.key("另一件-02")),
        )
        assertEquals(
            RelistPlanError.REMOVAL_APPROVAL_NOT_MATCHED,
            assertIs<RelistPlanValidation.Invalid>(wrongTarget).error,
        )
        // 状态不符（已消费的批准不能当 removal 证据）。
        val spent = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.FULL_AUTO,
            disposition = OldObjectDisposition.DELIST_OLD,
            removalApprovalId = "apr-remove",
            approvals = ledgerWithRemovalApproval(key = key, state = BasicApprovalState.CONSUMED),
        )
        assertEquals(
            RelistPlanError.INVALID_REMOVAL_APPROVAL_STATE,
            assertIs<RelistPlanValidation.Invalid>(spent).error,
        )
    }

    @Test
    fun keepListedNeedsNoRemovalAndRejectsContradictoryApprovals() {
        val key = F.key("下架重发品-01")
        val valid = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
            disposition = OldObjectDisposition.KEEP_LISTED,
            removalApprovalId = null,
            approvals = ledgerWithRemovalApproval(key = key),
        )
        assertIs<RelistPlanValidation.Valid>(valid)

        val contradictory = RelistPlanValidator.validate(
            oldTarget = key,
            boundary = PublishCompletionBoundary.FULL_AUTO,
            disposition = OldObjectDisposition.KEEP_LISTED,
            removalApprovalId = "apr-remove", // 不动旧对象却带了 removal 批准：矛盾计划拒绝
            approvals = ledgerWithRemovalApproval(key = key),
        )
        assertEquals(
            RelistPlanError.UNNECESSARY_REMOVAL_APPROVAL,
            assertIs<RelistPlanValidation.Invalid>(contradictory).error,
        )
    }

    @Test
    fun boundaryReusesTheP10CompletionModel() {
        // P10 四边界原样可用（只读复用；降级格语义由 publish 包持有）。
        val key = F.key("重发品-01")
        PublishCompletionBoundary.entries.forEach { boundary ->
            val valid = RelistPlanValidator.validate(
                oldTarget = key,
                boundary = boundary,
                disposition = OldObjectDisposition.KEEP_LISTED,
                removalApprovalId = null,
                approvals = ledgerWithRemovalApproval(key = key),
            )
            assertIs<RelistPlanValidation.Valid>(valid)
        }
        assertEquals(
            PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
            PublishCompletionBoundary.envelope(
                PublishCompletionBoundary.FULL_AUTO,
                PublishCompletionBoundary.HUMAN_PRICE_HUMAN_COMMIT,
            ),
        )
    }
}
