package com.company.cloudctl.companion.data

import com.company.cloudctl.companion.BuildConfig
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Debug and release compile different BindingWritePolicy types under the same
 * name. Acceptance and heartbeatDiagnostic reuse the release source set, so
 * assert the policy actually packaged by each variant rather than assuming
 * every unit-test task is the debug variant.
 */
class BindingWritePolicyTest {
    @Test
    fun bindingPolicyMatchesThePackagedSourceSet() {
        if (BuildConfig.APPLICATION_ID.endsWith(".debug")) {
            val error = kotlin.test.assertFailsWith<IllegalStateException> {
                BindingWritePolicy.beforeSave()
            }
            assertEquals("DEBUG_BINDING_FORBIDDEN", error.message)
        } else {
            BindingWritePolicy.beforeSave()
        }
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
