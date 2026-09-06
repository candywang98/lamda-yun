package com.company.cloudctl.companion.network

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class EnrollmentParserTest {
    @Test
    fun acceptsPinnedHttpsControlApi() {
        val payload = EnrollmentParser.parse(
            "https://control-api.site.example:8443/",
            "ab12cd",
            "aa:".repeat(31) + "aa",
        )
        assertEquals("AB12CD", payload.code)
        assertEquals(64, payload.certificateSha256.length)
    }

    @Test
    fun rejectsDeviceServicePort() {
        assertFailsWith<IllegalArgumentException> {
            EnrollmentParser.parse(
                "https://10.0.0.3:65000",
                "ABCDEF",
                "a".repeat(64),
            )
        }
    }

    @Test
    fun matchesSharedEnrollmentCodeContract() {
        val cases = checkNotNull(javaClass.classLoader?.getResourceAsStream(
            "companion-enrollment-code-cases.tsv",
        )).bufferedReader().useLines { lines ->
            lines.filter { it.isNotBlank() && !it.startsWith("#") }.toList()
        }
        assertTrue(cases.isNotEmpty())
        for (line in cases) {
            val (accepted, input, expected) = line.split('\t')
            if (accepted.toBoolean()) {
                assertEquals(
                    expected,
                    EnrollmentParser.parse(
                        "https://control-api.site.example:8443",
                        input,
                        "a".repeat(64),
                    ).code,
                )
            } else {
                assertFailsWith<IllegalArgumentException>(message = input) {
                    EnrollmentParser.parse(
                        "https://control-api.site.example:8443",
                        input,
                        "a".repeat(64),
                    )
                }
            }
        }
    }
}
