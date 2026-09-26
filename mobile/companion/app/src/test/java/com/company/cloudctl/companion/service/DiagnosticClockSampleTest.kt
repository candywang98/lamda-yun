package com.company.cloudctl.companion.service

import kotlin.test.Test
import kotlin.test.assertEquals

class DiagnosticClockSampleTest {
    @Test fun `awake interval has no sleep time`() {
        assertEquals(0L, DiagnosticClockSample(21_000, 20_000).sleepMillisSince(DiagnosticClockSample(1_000, 0)))
    }
    @Test fun `elapsed minus uptime isolates suspended time`() {
        assertEquals(120_000L, DiagnosticClockSample(141_000, 20_000).sleepMillisSince(DiagnosticClockSample(1_000, 0)))
    }
    @Test fun `clock sampling skew cannot report negative sleep`() {
        assertEquals(0L, DiagnosticClockSample(1_100, 101).sleepMillisSince(DiagnosticClockSample(1_000, 0)))
    }
}
