package com.company.cloudctl.companion.ime

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ImeAvailabilityTest {
    @Test
    fun matchesEnabledAndSelectedComponentIds() {
        val pkg = "com.company.cloudctl.companion"
        assertTrue(
            ImeAvailability.listed(
                "$pkg/.ime.CloudCtlInputMethod:com.google.android.inputmethod.latin/.LatinIME",
                pkg,
            ),
        )
        assertTrue(
            ImeAvailability.listed(
                "$pkg/$pkg.ime.CloudCtlInputMethod",
                pkg,
            ),
        )
        assertFalse(ImeAvailability.listed("com.google.android.inputmethod.latin/.LatinIME", pkg))
        assertFalse(ImeAvailability.listed(null, pkg))
    }

    @Test
    fun pickerRequestIsTheRecoverableEnablingPath() {
        // Public system picker only; a framework failure surfaces false, never a crash.
        var opened = false
        assertTrue(ImeAvailability.pickerRequest { opened = true })
        assertTrue(opened)
        assertFalse(
            ImeAvailability.pickerRequest { throw IllegalStateException("window lost") },
        )
    }
}
