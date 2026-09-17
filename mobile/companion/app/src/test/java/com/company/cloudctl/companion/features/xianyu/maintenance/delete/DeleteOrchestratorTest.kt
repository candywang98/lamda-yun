package com.company.cloudctl.companion.features.xianyu.maintenance.delete

import com.company.cloudctl.companion.locators.CompositeItemAttributes
import com.company.cloudctl.companion.locators.ItemIdentityEvidence
import com.company.cloudctl.companion.locators.ItemIdentityEvidencePolicy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * X10 — 删除编排：误卡/同名/旧窗口/无目标 ID/证据不足全部 fail-closed 不触击；
 * 默认取消闭环；单发确认；未知任务不自动重新删除（重放防护）。
 */
class DeleteOrchestratorTest {

    private val platformIdEvidence = ItemIdentityEvidencePolicy.evaluate(
        CompositeItemAttributes(
            accountScope = "xianyu://account/seller-A",
            titleContains = "测试可删品-01",
        ),
        cardLines = listOf("测试可删品-01", "¥1.00"),
        distinctMatchingCards = 1,
        platformItemId = "7123456789",
    )

    private fun cancelLoopOrchestrator() =
        DeleteOrchestrator(DeleteOrchestrator.CANCEL_LOOP_PLAN, approvalId = "apr-1", taskId = "t-1")

    private fun deleteOrchestrator() =
        DeleteOrchestrator(DeleteOrchestrator.DELETE_PLAN, approvalId = "apr-1", taskId = "t-1")

    // ---- fail-closed：五类身份失败，各有原因码，绝不触击 ----

    @Test
    fun nullIdentityNoTargetIdBlocksWrongTargetBeforeAnyStrike() {
        val orchestrator = deleteOrchestrator()
        val decision = orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(null))
        val blocked = assertIs<DeleteDecision.Blocked>(decision)
        assertEquals(DeleteFailureClass.WRONG_TARGET, blocked.record.failureClass)
        assertEquals(WrongTargetReason.NO_TARGET_ID, blocked.record.reasonCode)
    }

    @Test
    fun sameTitleAmbiguityBlocksWrongTargetWithItsOwnReasonCode() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            CompositeItemAttributes(
                accountScope = "xianyu://account/seller-A",
                titleContains = "同名测试品",
                price = "¥1.00",
            ),
            cardLines = emptyList(),
            distinctMatchingCards = 2,
        )
        assertTrue(evidence is ItemIdentityEvidence.Insufficient)
        val orchestrator = deleteOrchestrator()
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(evidence)),
        )
        assertEquals(DeleteFailureClass.WRONG_TARGET, blocked.record.failureClass)
        assertEquals(WrongTargetReason.SAME_TITLE_AMBIGUITY, blocked.record.reasonCode)
    }

    @Test
    fun insufficientCompositeBlocksWrongTargetWithItsOwnReasonCode() {
        val evidence = ItemIdentityEvidence.Insufficient(
            reason = "composite identity needs ≥2 visible attributes, got 1 (title alone is not an identity)",
        )
        val orchestrator = deleteOrchestrator()
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(evidence)),
        )
        assertEquals(DeleteFailureClass.WRONG_TARGET, blocked.record.failureClass)
        assertEquals(WrongTargetReason.INSUFFICIENT_EVIDENCE, blocked.record.reasonCode)
    }

    @Test
    fun staleWindowOnDetailRecheckBlocksWrongTargetWithItsOwnReasonCode() {
        val orchestrator = deleteOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(
                DeleteEvent.DetailIdentityChecked(
                    titleMatched = true,
                    windowChanged = true,
                ),
            ),
        )
        assertEquals(DeleteFailureClass.WRONG_TARGET, blocked.record.failureClass)
        assertEquals(WrongTargetReason.STALE_WINDOW, blocked.record.reasonCode)
    }

    @Test
    fun sessionEpochChangeOnDetailRecheckAlsoBlocksWrongTarget() {
        val orchestrator = deleteOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(
                DeleteEvent.DetailIdentityChecked(
                    titleMatched = true,
                    sessionEpochChanged = true,
                ),
            ),
        )
        assertEquals(DeleteFailureClass.WRONG_TARGET, blocked.record.failureClass)
        assertEquals(WrongTargetReason.STALE_WINDOW, blocked.record.reasonCode)
    }

    @Test
    fun detailTitleMismatchBlocksWrongTargetWithItsOwnReasonCode() {
        val orchestrator = deleteOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = false)),
        )
        assertEquals(DeleteFailureClass.WRONG_TARGET, blocked.record.failureClass)
        assertEquals(WrongTargetReason.DETAIL_TITLE_MISMATCH, blocked.record.reasonCode)
    }

    // ---- 菜单与确认框异常：零副作用安全退出（未派发） ----

    @Test
    fun menuAnomalyExitsSafelyWithoutAnyStrike() {
        val orchestrator = deleteOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = true))
        val abort = assertIs<DeleteDecision.AbortSafely>(
            orchestrator.submit(
                DeleteEvent.ManageMenuObserved(
                    deleteAnchorPresent = false,
                    cancelAnchorPresent = true,
                    anomaly = true,
                ),
            ),
        )
        assertEquals(DeleteFailureClass.NOT_DISPATCHED, abort.record.failureClass)
        assertEquals(NotDispatchedReason.MENU_NOT_VERIFIED, abort.record.reasonCode)
    }

    @Test
    fun nonUniqueConfirmDialogExitsSafelyWithoutAnyStrike() {
        val orchestrator = deleteOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = true))
        orchestrator.submit(
            DeleteEvent.ManageMenuObserved(deleteAnchorPresent = true, cancelAnchorPresent = true),
        )
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
        val abort = assertIs<DeleteDecision.AbortSafely>(
            orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = false, textMatches = true)),
        )
        assertEquals(DeleteFailureClass.NOT_DISPATCHED, abort.record.failureClass)
        assertEquals(NotDispatchedReason.CONFIRM_DIALOG_NOT_UNIQUE, abort.record.reasonCode)
    }

    // ---- 取消闭环（默认计划）：到达确认框并能撤出，零副作用 ----

    @Test
    fun cancelLoopClosesCleanlyWithZeroSideEffects() {
        val orchestrator = cancelLoopOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = true))
        orchestrator.submit(
            DeleteEvent.ManageMenuObserved(deleteAnchorPresent = true, cancelAnchorPresent = true),
        )
        // 两次确认框观察：一次=弹窗打开，一次=唯一性+文本验证（走完才到取消步）。
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
        val closed = assertIs<DeleteDecision.CancelLoopClosed>(
            orchestrator.submit(
                DeleteEvent.CancelLoopExited(sideEffects = 0, backOnDetailOrList = true),
            ),
        )
        assertEquals("apr-1", closed.approvalId)
        assertEquals(0, closed.sideEffects)
    }

    @Test
    fun dirtyCancelLoopIsBlockedNotClosed() {
        val orchestrator = cancelLoopOrchestrator()
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = true))
        orchestrator.submit(
            DeleteEvent.ManageMenuObserved(deleteAnchorPresent = true, cancelAnchorPresent = true),
        )
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(
                DeleteEvent.CancelLoopExited(sideEffects = 1, backOnDetailOrList = false),
            ),
        )
        assertEquals(NotDispatchedReason.CANCEL_LOOP_NOT_CLEAN, blocked.record.reasonCode)
    }

    // ---- 复合证据的人工确认门（B13 humanConfirmationRequired） ----

    @Test
    fun compositeEvidenceRequiresHumanIdentityConfirmBeforeAnyStrike() {
        val evidence = ItemIdentityEvidencePolicy.evaluate(
            CompositeItemAttributes(
                accountScope = "xianyu://account/seller-A",
                titleContains = "测试可删品-01",
                price = "¥1.00",
                listingState = "已下架",
            ),
            cardLines = listOf("测试可删品-01", "¥1.00"),
            distinctMatchingCards = 1,
        )
        assertTrue(evidence is ItemIdentityEvidence.CompositeConfirmed)
        val orchestrator = deleteOrchestrator()
        assertEquals(
            DeleteDecision.WaitHumanIdentityConfirm,
            orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(evidence)),
        )
        // 人工未确认前，后续事件一律停在人工门。
        assertEquals(
            DeleteDecision.WaitHumanIdentityConfirm,
            orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = true)),
        )
        // 人工确认后放行。
        assertIs<DeleteDecision.Advance>(
            orchestrator.submit(DeleteEvent.HumanIdentityConfirmed),
        )
    }

    // ---- 单发确认 + 授权拒绝 ----

    @Test
    fun issuedAuthorizationAuthorizesExactlyOneStrike() {
        val orchestrator = deleteOrchestrator()
        walkToAuthorization(orchestrator)
        val authorize = assertIs<DeleteDecision.AuthorizeStrike>(
            orchestrator.submit(
                DeleteEvent.AuthorizationDecided(
                    DeleteApprovalDecision.Issued(
                        DeleteConfirmIssuance("apr-1", "t-1", 1),
                    ),
                ),
            ),
        )
        assertEquals("t-1", authorize.issuance.taskId)
        // 单发闩：第二次派发事件被保护期分类拒绝。
        orchestrator.submit(DeleteEvent.StrikeDispatched("action-key-1"))
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(DeleteEvent.StrikeDispatched("action-key-1-again")),
        )
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, blocked.record.failureClass)
    }

    @Test
    fun rejectedAuthorizationBlocksWithoutAnyStrike() {
        val orchestrator = deleteOrchestrator()
        walkToAuthorization(orchestrator)
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(
                DeleteEvent.AuthorizationDecided(
                    DeleteApprovalDecision.Rejected(
                        state = DeleteApprovalState.PROTECTION_PERIOD,
                        reasonCode = ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
                        reason = "prior attempt unresolved",
                        failureClass = DeleteFailureClass.PROTECTION_PERIOD,
                    ),
                ),
            ),
        )
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, blocked.record.failureClass)
    }

    // ---- 未知任务不自动重新删除（重放防护） ----

    @Test
    fun unknownOutcomeNeverRestrikesAndBlocksFurtherSteps() {
        val orchestrator = deleteOrchestrator()
        walkToAuthorization(orchestrator)
        orchestrator.submit(
            DeleteEvent.AuthorizationDecided(
                DeleteApprovalDecision.Issued(DeleteConfirmIssuance("apr-1", "t-1", 1)),
            ),
        )
        orchestrator.submit(DeleteEvent.StrikeDispatched("action-key-1"))
        val unknown = assertIs<DeleteDecision.ReportedUnknown>(
            orchestrator.submit(
                DeleteEvent.StrikeOutcomeReported(
                    status = "UNKNOWN",
                    reasonCode = DispatchedUnknownReason.DIALOG_DISMISSAL_UNCAPTURED,
                ),
            ),
        )
        assertEquals(DeleteFailureClass.DISPATCHED_UNKNOWN, unknown.record.failureClass)
        assertEquals(
            DeleteFailureDisposition.NEVER_RESTRIKE_PENDING_VERIFICATION,
            unknown.record.disposition,
        )
        // 之后任何事件（包括再来一次派发）都被保护期硬闩挡住。
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(DeleteEvent.StrikeDispatched("action-key-1-replay")),
        )
        assertEquals(DeleteFailureClass.PROTECTION_PERIOD, blocked.record.failureClass)
        assertEquals(ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT, blocked.record.reasonCode)
    }

    @Test
    fun outcomeWithoutDispatchIsBlockedAsNotDispatched() {
        val orchestrator = deleteOrchestrator()
        walkToAuthorization(orchestrator)
        orchestrator.submit(
            DeleteEvent.AuthorizationDecided(
                DeleteApprovalDecision.Issued(DeleteConfirmIssuance("apr-1", "t-1", 1)),
            ),
        )
        val blocked = assertIs<DeleteDecision.Blocked>(
            orchestrator.submit(DeleteEvent.StrikeOutcomeReported(status = "APPLIED")),
        )
        assertEquals(DeleteFailureClass.NOT_DISPATCHED, blocked.record.failureClass)
        assertEquals(NotDispatchedReason.INTENT_REJECTED, blocked.record.reasonCode)
    }

    @Test
    fun appliedOutcomeAdvancesToReadbackAndCompletes() {
        val orchestrator = deleteOrchestrator()
        walkToAuthorization(orchestrator)
        orchestrator.submit(
            DeleteEvent.AuthorizationDecided(
                DeleteApprovalDecision.Issued(DeleteConfirmIssuance("apr-1", "t-1", 1)),
            ),
        )
        orchestrator.submit(DeleteEvent.StrikeDispatched("action-key-1"))
        assertIs<DeleteDecision.Advance>(
            orchestrator.submit(DeleteEvent.StrikeOutcomeReported(status = "APPLIED")),
        )
        val completed = assertIs<DeleteDecision.Completed>(
            orchestrator.submit(
                DeleteEvent.ReadbackObserved(
                    DeleteResultReadback.Observation(
                        targetStillVisible = false,
                        delistedBadgeCount = 1,
                        delistedBadgeBaseline = 2,
                        confirmDialogDismissed = true,
                    ),
                ),
            ),
        )
        assertIs<DeleteReadbackVerdict.VerifiedDeleted>(completed.verdict)
    }

    private fun walkToAuthorization(orchestrator: DeleteOrchestrator) {
        orchestrator.submit(DeleteEvent.TargetIdentityEvaluated(platformIdEvidence))
        orchestrator.submit(DeleteEvent.DetailIdentityChecked(titleMatched = true))
        orchestrator.submit(
            DeleteEvent.ManageMenuObserved(deleteAnchorPresent = true, cancelAnchorPresent = true),
        )
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
        orchestrator.submit(DeleteEvent.ConfirmDialogObserved(unique = true, textMatches = true))
    }
}
