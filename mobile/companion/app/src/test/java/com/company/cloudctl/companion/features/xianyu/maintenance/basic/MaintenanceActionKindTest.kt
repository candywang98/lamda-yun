package com.company.cloudctl.companion.features.xianyu.maintenance.basic

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * X11 任务卡第 5 条：每个操作的结果类型独立，禁止统一映射成 success/delete。
 */
class MaintenanceActionKindTest {

    @Test
    fun resultWiresAreAllDistinctPerAction() {
        assertEquals(
            setOf("POLISHED", "DELISTED", "PRICE_REDUCED", "RELISTED"),
            MaintenanceActionResult.allWires,
        )
        assertEquals(4, MaintenanceActionKind.entries.size)
        // 动作 wire 也各自独立（与服务端 commandType 分形同构）。
        assertEquals(
            MaintenanceActionKind.entries.size,
            MaintenanceActionKind.entries.map { it.wire }.toSet().size,
        )
    }

    @Test
    fun crossActionAccountingIsRejectedByTheTypeGate() {
        // DELIST 目标拿 POLISHED 结果记账 = 统一映射回归，必须抛错。
        assertFailsWith<IllegalArgumentException> {
            MaintenanceActionResult.requireMatches(
                MaintenanceActionKind.DELIST,
                MaintenanceActionResult.Polished,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            MaintenanceActionResult.requireMatches(
                MaintenanceActionKind.POLISH,
                MaintenanceActionResult.Delisted,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            MaintenanceActionResult.requireMatches(
                MaintenanceActionKind.RELIST,
                MaintenanceActionResult.PriceReduced(oldPriceCents = 200L, newPriceCents = 100L),
            )
        }
        // 对齐的记账通过。
        MaintenanceActionResult.requireMatches(
            MaintenanceActionKind.DELIST,
            MaintenanceActionResult.Delisted,
        )
    }

    @Test
    fun priceReducedMustActuallyReduceAndStayPositive() {
        assertFailsWith<IllegalArgumentException> {
            MaintenanceActionResult.PriceReduced(oldPriceCents = 100L, newPriceCents = 100L)
        }
        assertFailsWith<IllegalArgumentException> {
            MaintenanceActionResult.PriceReduced(oldPriceCents = 100L, newPriceCents = 0L)
        }
        MaintenanceActionResult.PriceReduced(oldPriceCents = 100L, newPriceCents = 1L)
    }

    @Test
    fun outcomeFamiliesNeverCollapseIntoOneSuccess() {
        val outcomes = listOf(
            MaintenanceOutcome.Completed(MaintenanceActionResult.Polished),
            MaintenanceOutcome.ReadbackHeld("PRICE_READBACK_MISMATCH", "mismatch"),
            MaintenanceOutcome.Unknown("DIALOG_DISMISSAL_UNCAPTURED", "unknown"),
            MaintenanceOutcome.Failed("INTENT_REJECTED", "rejected"),
        )
        // 四类终局各自独立的类形态（sealed 分支互不相同）。
        assertEquals(4, outcomes.map { it::class }.toSet().size)
        assertTrue(
            MaintenanceOutcome.Completed(MaintenanceActionResult.Delisted).result
                is MaintenanceActionResult.Delisted,
        )
    }
}
