package com.company.cloudctl.companion.features.xianyu.maintenance.delete

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * X10 — 失败分类学：四类独立状态与处置，绝不归并为一个「点击失败」；
 * P09 三次真实历史各归一类。
 */
class DeleteFailureTaxonomyTest {

    @Test
    fun fourClassesExistWithDistinctWireNames() {
        val wires = DeleteFailureClass.entries.map { it.wire }.toSet()
        assertEquals(
            setOf("WRONG_TARGET", "NOT_DISPATCHED", "DISPATCHED_UNKNOWN", "PROTECTION_PERIOD"),
            wires,
        )
        assertEquals(4, DeleteFailureClass.entries.size)
    }

    @Test
    fun everyClassMapsToItsOwnLedgerState() {
        val states = DeleteFailureClass.entries.map { it.ledgerStateWire() }.toSet()
        assertEquals(DeleteFailureClass.entries.size, states.size)
        assertEquals(
            setOf(
                "BLOCKED_IDENTITY",
                "NOT_DISPATCHED",
                "UNKNOWN",
                "PROTECTION_PERIOD",
            ),
            states,
        )
    }

    @Test
    fun everyClassMapsToItsOwnDispositionAndNoneIsAnAutoRetry() {
        val dispositions = DeleteFailureClass.entries.map { it.dispositionWire() }.toSet()
        assertEquals(DeleteFailureClass.entries.size, dispositions.size)
        // 处置语汇里不允许出现任何自动重试语义。
        assertTrue(
            dispositions.none { it.contains("RETRY") || it.contains("AUTO") },
            "no disposition may encode an automatic retry: $dispositions",
        )
        assertTrue(
            DeleteFailureDisposition.EXPLICIT_REJECT_NO_QUEUE in
                DeleteFailureDisposition.entries.toSet(),
        )
    }

    @Test
    fun p09AttemptOneIntent409IsNotDispatchedNotAClickFailure() {
        val record = P09DeleteHistoryReplay.attempts[0].record
        assertEquals("4d226249", P09DeleteHistoryReplay.attempts[0].taskId)
        assertEquals(DeleteFailureClass.NOT_DISPATCHED, record.failureClass)
        assertEquals(NotDispatchedReason.INTENT_REJECTED, record.reasonCode)
        assertEquals(DeleteFailureLedgerState.NOT_DISPATCHED, record.ledgerState)
        assertEquals(
            DeleteFailureDisposition.SAFE_EXIT_NEW_AUTHORIZATION_REQUIRED,
            record.disposition,
        )
    }

    @Test
    fun p09AttemptTwoLayoutDriftIsWrongTargetClassNotNotDispatched() {
        val record = P09DeleteHistoryReplay.attempts[1].record
        assertEquals("6d22dd62", P09DeleteHistoryReplay.attempts[1].taskId)
        assertEquals(DeleteFailureClass.WRONG_TARGET, record.failureClass)
        assertEquals(WrongTargetReason.LAYOUT_DRIFT_BLOCKED, record.reasonCode)
        assertEquals(DeleteFailureLedgerState.BLOCKED_IDENTITY, record.ledgerState)
        assertEquals(
            DeleteFailureDisposition.STOP_NO_STRIKE_OPERATOR_DISAMBIGUATE,
            record.disposition,
        )
    }

    @Test
    fun p09AttemptThreeUncapturedDismissalIsDispatchedUnknown() {
        val record = P09DeleteHistoryReplay.attempts[2].record
        assertEquals("37a665b0", P09DeleteHistoryReplay.attempts[2].taskId)
        assertEquals(DeleteFailureClass.DISPATCHED_UNKNOWN, record.failureClass)
        assertEquals(DispatchedUnknownReason.DIALOG_DISMISSAL_UNCAPTURED, record.reasonCode)
        assertEquals(DeleteFailureLedgerState.UNKNOWN, record.ledgerState)
        assertEquals(
            DeleteFailureDisposition.NEVER_RESTRIKE_PENDING_VERIFICATION,
            record.disposition,
        )
    }

    @Test
    fun threeHistoricalAttemptsNeverShareAClassStateOrDisposition() {
        assertEquals(3, P09DeleteHistoryReplay.attempts.size)
        assertTrue(P09DeleteHistoryReplay.classesStayDistinct())
        val classes = P09DeleteHistoryReplay.attempts.map { it.record.failureClass }.toSet()
        assertEquals(3, classes.size, "merging any two P09 failures into one class is a regression")
    }

    @Test
    fun protectionPeriodIsTheFourthClassWithRejectNoQueueDisposition() {
        val record = DeleteFailureRecord(
            failureClass = DeleteFailureClass.PROTECTION_PERIOD,
            reasonCode = ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
            reason = "prior attempt UNKNOWN",
        )
        assertEquals(DeleteFailureLedgerState.PROTECTION_PERIOD, record.ledgerState)
        assertEquals(DeleteFailureDisposition.EXPLICIT_REJECT_NO_QUEUE, record.disposition)
    }

    @Test
    fun reasonCodesAreNeverBlankAndNeverCollapseToClickFailed() {
        val all = listOf(
            WrongTargetReason.DETAIL_TITLE_MISMATCH,
            WrongTargetReason.SAME_TITLE_AMBIGUITY,
            WrongTargetReason.STALE_WINDOW,
            WrongTargetReason.NO_TARGET_ID,
            WrongTargetReason.INSUFFICIENT_EVIDENCE,
            WrongTargetReason.LAYOUT_DRIFT_BLOCKED,
            NotDispatchedReason.INTENT_REJECTED,
            NotDispatchedReason.NAVIGATION_FAILED,
            NotDispatchedReason.MENU_NOT_VERIFIED,
            NotDispatchedReason.CONFIRM_DIALOG_NOT_UNIQUE,
            NotDispatchedReason.APPROVAL_NOT_VALID,
            NotDispatchedReason.CANCEL_LOOP_NOT_CLEAN,
            NotDispatchedReason.UNEXPECTED_EVENT,
            DispatchedUnknownReason.DIALOG_DISMISSAL_UNCAPTURED,
            DispatchedUnknownReason.BADGE_UNREADABLE,
            DispatchedUnknownReason.READBACK_INCONCLUSIVE,
            ProtectionPeriodReason.UNRESOLVED_PRIOR_ATTEMPT,
            ProtectionPeriodReason.APPROVAL_PROTECTION_WINDOW,
        )
        assertEquals(all.size, all.toSet().size)
        assertTrue(all.all { it.isNotBlank() && it != "CLICK_FAILED" })
    }

    private fun DeleteFailureClass.ledgerStateWire() =
        DeleteFailureRecord(this, "PROBE", "probe").ledgerState.wire

    private fun DeleteFailureClass.dispositionWire() =
        DeleteFailureRecord(this, "PROBE", "probe").disposition.wire
}
