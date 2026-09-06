package com.company.cloudctl.dpc

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class AllowlistParserTest {
    @Test
    fun parsesDistinctPackages() {
        assertEquals(
            listOf("com.company.cloudctl.companion", "com.company.target"),
            AllowlistParser.parse(
                "com.company.cloudctl.companion, com.company.target, com.company.target",
            ),
        )
    }

    @Test
    fun rejectsShellLikeInput() {
        assertFailsWith<IllegalArgumentException> {
            AllowlistParser.parse("com.company.target; rm -rf /data")
        }
    }
}

