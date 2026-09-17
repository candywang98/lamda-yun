package com.company.cloudctl.companion.features.xianyu.maintenance.delete

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * X10 — 结果回读：列表消失 + badge 变化双证才 VerifiedDeleted；badge 门禁缺失
 * 一律「待核对」，绝不伪造成功；目标仍可见不是成功。
 */
class DeleteResultReadbackTest {

    @Test
    fun vanishedTargetPlusBadgeDeltaIsVerifiedDeleted() {
        val verdict = DeleteReadbackJudge.judge(
            DeleteResultReadback.Observation(
                targetStillVisible = false,
                delistedBadgeCount = 1,
                delistedBadgeBaseline = 2,
                confirmDialogDismissed = true,
            ),
        )
        val verified = assertIs<DeleteReadbackVerdict.VerifiedDeleted>(verdict)
        assertEquals(2, verified.badgeBefore)
        assertEquals(1, verified.badgeAfter)
    }

    @Test
    fun badgeGateMissingHoldsPendingVerificationNeverSuccess() {
        // P09 删除终版真机形态：已下架 tab 无数字角标（锚点契约实测），v2 详情路径
        // tabs 不在树内——badge 门禁缺失 → 待核对。
        val verdict = DeleteReadbackJudge.judge(
            DeleteResultReadback.Observation(
                targetStillVisible = false,
                delistedBadgeCount = null,
                delistedBadgeBaseline = null,
                confirmDialogDismissed = true,
            ),
        )
        val pending = assertIs<DeleteReadbackVerdict.PendingVerification>(verdict)
        assertEquals(DispatchedUnknownReason.BADGE_UNREADABLE, pending.reasonCode)
    }

    @Test
    fun halfReadableBadgeStillHoldsPendingVerification() {
        // 基线在、读数缺（或反之）：证据不齐，不折算成功。
        val verdict = DeleteReadbackJudge.judge(
            DeleteResultReadback.Observation(
                targetStillVisible = false,
                delistedBadgeCount = null,
                delistedBadgeBaseline = 2,
                confirmDialogDismissed = true,
            ),
        )
        assertIs<DeleteReadbackVerdict.PendingVerification>(verdict)
    }

    @Test
    fun stillVisibleTargetIsNeverASuccess() {
        val verdict = DeleteReadbackJudge.judge(
            DeleteResultReadback.Observation(
                targetStillVisible = true,
                delistedBadgeCount = 1,
                delistedBadgeBaseline = 2,
                confirmDialogDismissed = true,
            ),
        )
        assertIs<DeleteReadbackVerdict.StillPresent>(verdict)
    }

    @Test
    fun badgeMovingTheWrongWayIsInconclusiveNotSuccess() {
        val verdict = DeleteReadbackJudge.judge(
            DeleteResultReadback.Observation(
                targetStillVisible = false,
                delistedBadgeCount = 2,
                delistedBadgeBaseline = 2,
                confirmDialogDismissed = true,
            ),
        )
        val inconclusive = assertIs<DeleteReadbackVerdict.Inconclusive>(verdict)
        assertEquals(DispatchedUnknownReason.READBACK_INCONCLUSIVE, inconclusive.reasonCode)
    }

    @Test
    fun openDialogDuringReadbackIsContradictoryAndInconclusive() {
        val verdict = DeleteReadbackJudge.judge(
            DeleteResultReadback.Observation(
                targetStillVisible = false,
                delistedBadgeCount = 1,
                delistedBadgeBaseline = 2,
                confirmDialogDismissed = false,
            ),
        )
        assertIs<DeleteReadbackVerdict.Inconclusive>(verdict)
    }

    @Test
    fun onlyVerifiedDeletedCountsAsMachineSuccess() {
        val verdicts = listOf(
            DeleteReadbackJudge.judge(
                DeleteResultReadback.Observation(false, 1, 2, true),
            ),
            DeleteReadbackJudge.judge(
                DeleteResultReadback.Observation(false, null, null, true),
            ),
            DeleteReadbackJudge.judge(
                DeleteResultReadback.Observation(true, 1, 2, true),
            ),
            DeleteReadbackJudge.judge(
                DeleteResultReadback.Observation(false, 2, 2, true),
            ),
        )
        assertEquals(1, verdicts.count { it is DeleteReadbackVerdict.VerifiedDeleted })
    }
}
