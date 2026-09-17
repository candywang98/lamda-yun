package com.company.cloudctl.companion.automation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PriceKeypadTest {
    @Test
    fun keepsWholeNumbersIncludingTrailingZeros() {
        assertEquals("199", PriceKeypad.keys("199"))
        assertEquals("10", PriceKeypad.keys("10"))
        assertEquals("199", PriceKeypad.keys("199.00"))
        assertEquals("10.5", PriceKeypad.keys("10.50"))
    }

    @Test
    fun acceptsFormattedIdlefishPrice() {
        assertTrue(PriceKeypad.acceptedOnForm("价格\n¥199.00", "199"))
        assertTrue(PriceKeypad.acceptedOnForm("¥199", "199.00"))
        assertFalse(PriceKeypad.acceptedOnForm("价格", "199"))
    }

    // ---- B14: accumulated amounts must never pass for the intended price ----

    @Test
    fun accumulatedAmountNeverPassesDespiteSubstringMatch() {
        // Uncleared leftover "10" + typing "199" shows "10199": "199" IS a substring
        // of it, yet the price is wrong. Token equality rejects it.
        assertFalse(PriceKeypad.acceptedOnForm("¥10199.00", "199"))
        assertFalse(PriceKeypad.acceptedOnForm("¥19910", "199"))
        assertTrue(PriceKeypad.acceptedOnForm("¥199", "199"))
    }

    @Test
    fun decimalPointRoundTripsNumerically() {
        assertTrue(PriceKeypad.acceptedOnForm("¥10.5", "10.5"))
        assertTrue(PriceKeypad.acceptedOnForm("¥10.50", "10.5"))
        assertTrue(PriceKeypad.acceptedOnForm("¥10.5", "10.50"))
        assertFalse(PriceKeypad.acceptedOnForm("¥1.05", "10.5"))
        assertFalse(PriceKeypad.acceptedOnForm("¥105", "10.5"))
        assertFalse(PriceKeypad.acceptedOnForm("¥10..5", "10.5"))
    }

    @Test
    fun commaGroupedAmountsCompareNumerically() {
        assertTrue(PriceKeypad.acceptedOnForm("¥1,299.00", "1299"))
        assertTrue(PriceKeypad.acceptedOnForm("到手价 1,299", "1299.00"))
        assertFalse(PriceKeypad.acceptedOnForm("¥1,299.00", "299"))
    }

    @Test
    fun displayedAmountsExtractTokensNotSubstrings() {
        assertEquals(listOf("10199.00"), PriceKeypad.displayedAmounts("¥10199.00"))
        assertEquals(listOf("199"), PriceKeypad.displayedAmounts("¥199"))
        assertEquals(listOf("1,299.00"), PriceKeypad.displayedAmounts("¥1,299.00"))
        assertEquals(emptyList(), PriceKeypad.displayedAmounts("定价"))
    }

    @Test
    fun keypadableAllowsOneDecimalPointAtMost() {
        assertTrue(PriceKeypad.keypadable("199"))
        assertTrue(PriceKeypad.keypadable("10.5"))
        assertTrue(PriceKeypad.keypadable("10.50"))
        assertFalse(PriceKeypad.keypadable("10..5"))
        assertFalse(PriceKeypad.keypadable("199元"))
        assertFalse(PriceKeypad.keypadable(""))
    }
}
