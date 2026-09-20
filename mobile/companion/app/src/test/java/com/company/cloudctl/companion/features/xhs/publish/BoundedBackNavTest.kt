package com.company.cloudctl.companion.features.xhs.publish

import com.company.cloudctl.companion.features.xhs.publish.BoundedBackNav.Decision
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * F14 验收：无界 back 不出现——预算耗尽即有界退出。
 */
class BoundedBackNavTest {

    @Test
    fun allowsBacksWithinBudgetAndCountsOnlyEvidencedBacks() {
        var nav = BoundedBackNav(maxBacks = 2)
        val first = nav.requestBack()
        assertIs<Decision.AllowBack>(first)
        assertEquals(1, first.remainingAfter)

        // 无证据的返回不消耗预算（页面没确认回来不算一次成功 back）。
        nav = nav.onBackEvidence(expectedLocatorHit = false)
        assertEquals(0, nav.backsUsed())

        nav = nav.onBackEvidence(expectedLocatorHit = true)
        assertEquals(1, nav.backsUsed())
        val second = nav.requestBack()
        assertIs<Decision.AllowBack>(second)
        assertEquals(0, second.remainingAfter)
    }

    @Test
    fun exhaustedBudgetExitsBoundedWithExplainableReason() {
        var nav = BoundedBackNav(maxBacks = 1)
        nav = nav.onBackEvidence(expectedLocatorHit = true)
        val decision = nav.requestBack()
        val exit = assertIs<Decision.BoundedExit>(decision)
        assertTrue(exit.reason.contains("NAV_BOUNDED_EXIT"))
        assertTrue(exit.reason.contains("1"))
    }

    @Test
    fun invalidBudgetIsRejectedAtConstruction() {
        val hit = try {
            BoundedBackNav(maxBacks = 0)
            false
        } catch (_: IllegalArgumentException) {
            true
        }
        assertTrue(hit)
    }
}
