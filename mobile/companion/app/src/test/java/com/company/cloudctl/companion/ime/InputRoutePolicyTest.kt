package com.company.cloudctl.companion.ime

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class InputRoutePolicyTest {
    @Test fun api33AccessibilityIsReadyWithoutSelectingCloudCtl() {
        assertEquals(InputChannel.ACCESSIBILITY, InputRoutePolicy.channel(33))
        assertEquals(InputChannel.ACCESSIBILITY, InputRoutePolicy.channel(35))
        assertTrue(InputRoutePolicy.ready(33, accessibilityActive = true, imeEnabled = false, imeSelected = false))
        assertFalse(InputRoutePolicy.requiresSetup(33, imeEnabled = false, imeSelected = false))
        assertFalse(InputRoutePolicy.requiresSetup(34, imeEnabled = true, imeSelected = false))
    }

    @Test fun api33WithoutAccessibilityIsNotReady() {
        assertFalse(InputRoutePolicy.ready(33, accessibilityActive = false, imeEnabled = true, imeSelected = true))
    }

    @Test fun api30RequiresEnabledCloudCtlButNotCurrentSelection() {
        assertEquals(InputChannel.TEMPORARY_IME, InputRoutePolicy.channel(30))
        assertEquals(InputChannel.TEMPORARY_IME, InputRoutePolicy.channel(32))
        assertTrue(InputRoutePolicy.ready(31, accessibilityActive = true, imeEnabled = true, imeSelected = false))
        assertFalse(InputRoutePolicy.ready(31, accessibilityActive = true, imeEnabled = false, imeSelected = false))
        assertTrue(InputRoutePolicy.requiresSetup(30, imeEnabled = false, imeSelected = false))
        assertFalse(InputRoutePolicy.requiresSetup(32, imeEnabled = true, imeSelected = false))
    }

    @Test fun api29RequiresEnabledAndCurrentCloudCtl() {
        assertEquals(InputChannel.MANUAL_IME, InputRoutePolicy.channel(29))
        assertFalse(InputRoutePolicy.ready(29, accessibilityActive = true, imeEnabled = true, imeSelected = false))
        assertTrue(InputRoutePolicy.ready(29, accessibilityActive = true, imeEnabled = true, imeSelected = true))
        assertTrue(InputRoutePolicy.requiresSetup(29, imeEnabled = true, imeSelected = false))
        assertFalse(InputRoutePolicy.requiresSetup(29, imeEnabled = true, imeSelected = true))
    }

    @Test fun api33UnboundDoesNotAuthorizeAKeyboardSwitch() {
        assertFalse(InputRoutePolicy.accessibilityFallbackAllowed(accessibilityBound = false))
        assertTrue(InputRoutePolicy.accessibilityFallbackAllowed(accessibilityBound = true))
    }

    @Test fun onlyThePriceLocatorIsPrice() {
        assertTrue(InputRoutePolicy.isPrice("xianyu_price"))
        assertFalse(InputRoutePolicy.isPrice("xianyu_description"))
        assertFalse(InputRoutePolicy.isPrice("xianyu_chat_input"))
    }
}
