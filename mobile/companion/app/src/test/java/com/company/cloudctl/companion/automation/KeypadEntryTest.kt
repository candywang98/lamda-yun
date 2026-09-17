package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * B14 acceptance: price goes through the custom keypad as clear -> digit-by-digit
 * -> amount readback. Without a reliable readback the entry resolves WAITING_USER
 * and is never recorded as a full-field success.
 */
class KeypadEntryTest {
    @Test
    fun clearPlanCoversEveryShownCharacterIncludingTheDot() {
        val entry = KeypadEntry("199.00")
        assertEquals("199", entry.digits)
        assertEquals(4, entry.clearsNeeded("10.5"))
        assertEquals(4, entry.clearsNeeded("¥10.5"))
        assertEquals(0, entry.clearsNeeded(null))
        assertEquals(0, entry.clearsNeeded(""))
    }

    @Test
    fun unclearedLeftoverBreaksPrefixConsistencyMidFlight() {
        val entry = KeypadEntry("199")
        // Typed "1" but the field shows "91": a leftover "9" is still there.
        assertFalse(entry.prefixConsistent("91", 1))
        // Correct digit-by-digit progress after a real clear.
        assertTrue(entry.prefixConsistent("1", 1))
        assertTrue(entry.prefixConsistent("19", 2))
        assertTrue(entry.prefixConsistent("199", 3))
        // No digits typed yet, or more than planned: never consistent.
        assertFalse(entry.prefixConsistent("1", 0))
        assertFalse(entry.prefixConsistent("199", 4))
    }

    @Test
    fun decimalPointMidStateIsConsistent() {
        val entry = KeypadEntry("10.5")
        assertTrue(entry.prefixConsistent("1", 1))
        assertTrue(entry.prefixConsistent("10", 2))
        assertTrue(entry.prefixConsistent("10.", 3))
        assertTrue(entry.prefixConsistent("10.5", 4))
    }

    @Test
    fun unreadableFormResolvesWaitingUser() {
        assertEquals(KeypadEntry.Outcome.WAITING_USER, KeypadEntry("199").outcome(null))
        assertEquals(KeypadEntry.Outcome.WAITING_USER, KeypadEntry("199").outcome("定价"))
        assertEquals("WAITING_USER", KeypadEntry("199").outcomeWire("随便什么"))
    }

    @Test
    fun accumulatedAmountResolvesWaitingUserNotSuccess() {
        // Typing "199" over an uncleared "10" accumulated to "10199".
        assertEquals(KeypadEntry.Outcome.WAITING_USER, KeypadEntry("199").outcome("¥10199.00"))
    }

    @Test
    fun clearAndRetypeKeepsTheAmountConsistent() {
        val entry = KeypadEntry("199")
        // 1) forgot to clear -> accumulated readback fails
        assertEquals(KeypadEntry.Outcome.WAITING_USER, entry.outcome("¥10199.00"))
        // 2) clear plan for the accumulated amount, retype, readback succeeds
        assertEquals(5, entry.clearsNeeded("10199"))
        assertEquals(KeypadEntry.Outcome.VERIFIED, entry.outcome("价格\n¥199.00"))
        assertEquals("PRICE_VERIFIED", entry.outcomeWire("¥199"))
    }

    @Test
    fun verifiedOnlyOnNumericEqualReadback() {
        assertEquals(KeypadEntry.Outcome.VERIFIED, KeypadEntry("199").outcome("¥199"))
        assertEquals(KeypadEntry.Outcome.VERIFIED, KeypadEntry("10.50").outcome("¥10.5"))
        // Stale previous price still on the form is not the new price.
        assertEquals(KeypadEntry.Outcome.WAITING_USER, KeypadEntry("199").outcome("¥99"))
        assertEquals(KeypadEntry.Outcome.WAITING_USER, KeypadEntry("10.5").outcome("¥1.05"))
    }

    @Test
    fun rejectsValuesTheKeypadCannotType() {
        assertFailsWith<IllegalArgumentException> { KeypadEntry("199元") }
        assertFailsWith<IllegalArgumentException> { KeypadEntry("10..5") }
        assertFailsWith<IllegalArgumentException> { KeypadEntry("") }
    }
}
