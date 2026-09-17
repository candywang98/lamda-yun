package com.company.cloudctl.companion.control

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class CapabilityProbeTest {
    private fun probe(
        bound: Boolean = false,
        enabled: Boolean = false,
        defaultIme: String? = null,
        wssGranted: Boolean = false,
        adb: Boolean? = null,
    ): Map<String, com.company.cloudctl.companion.data.CapabilityProbeStatus> =
        CapabilityProbe(
            accessibilityBound = { bound },
            accessibilityEnabledInSettings = { enabled },
            defaultImeComponent = { defaultIme },
            ownImeComponent = { "com.company.cloudctl/.ime.CloudCtlInputMethod" },
            writeSecureSettingsGranted = { wssGranted },
            adbMotionInjectionAvailable = { adb },
        ).probe()

    @Test
    fun `all four capabilities are reported`() {
        val report = probe(bound = true, enabled = true)
        assertEquals(
            setOf(
                CapabilityProbe.CAP_ACCESSIBILITY_BOUND,
                CapabilityProbe.CAP_IME_DEFAULT,
                CapabilityProbe.CAP_WRITE_SECURE_SETTINGS,
                CapabilityProbe.CAP_ADB_MOTION_INJECTION,
            ),
            report.keys,
        )
    }

    @Test
    fun `accessibility bound requires both settings enable and live binding`() {
        assertFalse(probe(bound = true, enabled = false).getValue(CapabilityProbe.CAP_ACCESSIBILITY_BOUND).detected!!)
        assertFalse(probe(bound = false, enabled = true).getValue(CapabilityProbe.CAP_ACCESSIBILITY_BOUND).detected!!)
        assertTrue(probe(bound = true, enabled = true).getValue(CapabilityProbe.CAP_ACCESSIBILITY_BOUND).detected!!)
    }

    @Test
    fun `ime default matches own component case-insensitively`() {
        val report = probe(defaultIme = "COM.COMPANY.CLOUDCTL/.ime.CloudCtlInputMethod")
        assertTrue(report.getValue(CapabilityProbe.CAP_IME_DEFAULT).detected!!)
        assertFalse(probe(defaultIme = "com.other/.Ime").getValue(CapabilityProbe.CAP_IME_DEFAULT).detected!!)
        assertFalse(probe(defaultIme = null).getValue(CapabilityProbe.CAP_IME_DEFAULT).detected!!)
    }

    @Test
    fun `write secure settings is detection only and never claimed without grant`() {
        assertTrue(probe(wssGranted = true).getValue(CapabilityProbe.CAP_WRITE_SECURE_SETTINGS).detected!!)
        val denied = probe(wssGranted = false).getValue(CapabilityProbe.CAP_WRITE_SECURE_SETTINGS)
        assertFalse(denied.detected!!)
        assertTrue(denied.detail!!.contains("adb pm grant"))
    }

    @Test
    fun `adb motion injection reports unknown rather than false`() {
        val report = probe().getValue(CapabilityProbe.CAP_ADB_MOTION_INJECTION)
        assertNull(report.detected, "external adb channel cannot be verified in-process; report UNKNOWN")
    }
}
