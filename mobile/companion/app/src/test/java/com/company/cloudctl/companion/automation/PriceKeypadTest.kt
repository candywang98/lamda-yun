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
}
