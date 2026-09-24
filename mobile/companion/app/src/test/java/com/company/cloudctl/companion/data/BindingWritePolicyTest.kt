package com.company.cloudctl.companion.data

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Debug and release compile different BindingWritePolicy types under the same
 * name. This test runs in the debug unit-test variant, so the type it calls is
 * the debug one. The release type is checked by reading the release source,
 * which compileReleaseKotlin also has to compile.
 */
class BindingWritePolicyTest {
    @Test
    fun debugPolicyRefusesToSaveABinding() {
        val error = kotlin.test.assertFailsWith<IllegalStateException> {
            BindingWritePolicy.beforeSave()
        }
        assertEquals("DEBUG_BINDING_FORBIDDEN", error.message)
    }

    @Test
    fun releasePolicyIsANoOpAndDoesNotNameTheDebugGuard() {
        val release = sourceRoot().resolve(
            "src/release/java/com/company/cloudctl/companion/data/BindingWritePolicy.kt",
        )
        val text = release.readText()
        assertTrue(text.contains("fun beforeSave() = Unit"))
        assertFalse(text.contains("rejectWrite"))
        assertFalse(text.contains("DebugBindingGuard"))
        assertFalse(text.contains("DEBUG_BINDING_FORBIDDEN"))
    }

    private fun sourceRoot(): File {
        val candidates = listOf(File("app"), File("mobile/companion/app"), File("../app"))
        return candidates.firstOrNull { it.resolve("src/main").isDirectory }
            ?: error("companion app source root not found from ${File(".").absolutePath}")
    }
}
