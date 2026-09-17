package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import com.company.cloudctl.companion.features.xianyu.maintenance.basic.MaintenanceBasicFixtures as F
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 逐目标台账：幂等（已完成不重做）、UNKNOWN 阻塞、类型对齐门。 */
class MaintenanceTargetLedgerTest {

    @Test
    fun completedTargetsAreNeverReissued() {
        val ledger = MaintenanceTargetLedger()
        ledger.enroll("t-1", F.key("二战史-01"), MaintenanceActionKind.DELIST)
        ledger.markInFlight("t-1", "s-1")
        ledger.complete("t-1", MaintenanceActionResult.Delisted)

        val next = ledger.nextActionable()
        assertNull(next) // 只有一个目标且已完成：无可动目标
        assertTrue(ledger.completedKeys().contains("${F.key("二战史-01").identityKey}|delist"))
    }

    @Test
    fun unknownTargetBlocksFurtherIssuanceUntilResolved() {
        val ledger = MaintenanceTargetLedger()
        ledger.enroll("t-1", F.key("二战史-01"), MaintenanceActionKind.DELIST)
        ledger.enroll("t-2", F.key("二战史-02"), MaintenanceActionKind.DELIST)
        ledger.markInFlight("t-1", "s-1")
        ledger.markUnknown("t-1", "DIALOG_DISMISSAL_UNCAPTURED")

        assertNull(ledger.nextActionable()) // UNKNOWN 阻塞，t-2 不被发放
        ledger.resolveUnknown("t-1", evidence = "operator verified platformItemId 71234")
        assertEquals("t-1", ledger.nextActionable()?.targetId)
    }

    @Test
    fun completionRequiresKindAlignedResult() {
        val ledger = MaintenanceTargetLedger()
        ledger.enroll("t-1", F.key("二战史-01"), MaintenanceActionKind.DELIST)
        ledger.markInFlight("t-1", "s-1")
        assertFailsWith<IllegalArgumentException> {
            ledger.complete("t-1", MaintenanceActionResult.Polished)
        }
        ledger.complete("t-1", MaintenanceActionResult.Delisted)
        assertEquals(MaintenanceTargetState.COMPLETED, ledger.record("t-1")?.state)
        assertEquals(MaintenanceActionResult.Delisted, ledger.record("t-1")?.result)
    }

    @Test
    fun readbackHeldAndFailedAreTerminalStates() {
        val ledger = MaintenanceTargetLedger()
        ledger.enroll("t-1", F.key("二战史-01"), MaintenanceActionKind.PRICE_REDUCE)
        ledger.enroll("t-2", F.key("二战史-02"), MaintenanceActionKind.DELIST)
        ledger.markInFlight("t-1", "s-1")
        ledger.holdReadback("t-1", "PRICE_READBACK_MISMATCH")
        assertTrue(ledger.record("t-1")!!.terminal)

        ledger.markInFlight("t-2", "s-2")
        ledger.markFailed("t-2", "MENU_NOT_VERIFIED")
        assertTrue(ledger.record("t-2")!!.terminal)
        assertNull(ledger.nextActionable()) // 两个终态：无可动目标
    }

    @Test
    fun inFlightTargetIsReturnedForSingleItemSerialProgress() {
        val ledger = MaintenanceTargetLedger()
        ledger.enroll("t-1", F.key("二战史-01"), MaintenanceActionKind.DELIST)
        ledger.enroll("t-2", F.key("二战史-02"), MaintenanceActionKind.DELIST)
        ledger.markInFlight("t-1", "s-1")
        assertEquals("t-1", ledger.nextActionable()?.targetId) // 在飞的先报结果
    }
}
