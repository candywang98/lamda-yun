package com.company.cloudctl.companion.automation

import java.io.File
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Proves the diagnostic admit is not part of the release source set.
 *
 * This does not assemble a release APK (that needs the update signing key).
 * It checks the source sets the release compile actually uses.
 */
class DiagnosticReleaseAbsenceTest {
    @Test
    fun releaseSourceSetDoesNotNameTheHarnessPackage() {
        val release = sourceRoot().resolve("src/release")
        assertTrue(release.isDirectory, "release source set missing")
        val text = release.walkTopDown().filter { it.isFile }.joinToString("\n") { it.readText() }
        assertFalse(text.contains("com.company.cloudctl.inputharness"))
        assertFalse(text.contains("DebugDiagnosticInputPolicy"))
        assertFalse(text.contains("harness_multiline_field"))
        assertTrue(text.contains("DiagnosticInputPolicy.Closed"))
        assertFalse(text.contains("var installed"))
        assertFalse(text.contains("fun enforceClosed"))
        assertTrue(text.contains("DiagnosticInputPolicyProvider"))
        val binding = release.resolve(
            "java/com/company/cloudctl/companion/data/BindingWritePolicy.kt",
        ).readText()
        assertTrue(binding.contains("fun beforeSave() = Unit"))
        assertFalse(binding.contains("rejectWrite"))
        val debugBinding = sourceRoot().resolve(
            "src/debug/java/com/company/cloudctl/companion/data/BindingWritePolicy.kt",
        ).readText()
        assertTrue(debugBinding.contains("DebugBindingGuard.rejectWrite"))
    }

    @Test
    fun debugAdmitLivesOnlyInTheDebugSourceSet() {
        val debug = sourceRoot().resolve("src/debug/java/com/company/cloudctl/companion/automation/DebugDiagnosticInputPolicy.kt")
        assertTrue(debug.isFile)
        val main = sourceRoot().resolve("src/main").walkTopDown().filter { it.isFile }.joinToString("\n") { it.readText() }
        assertFalse(main.contains("com.company.cloudctl.inputharness"))
        assertFalse(main.contains("DebugDiagnosticInputPolicy"))
        assertTrue(main.contains("object Closed : DiagnosticInputPolicy"))
        assertFalse(main.contains("var installed"))
        assertTrue(main.contains("DiagnosticInputPolicyProvider.policy"))
        assertFalse(main.contains("DebugBindingPolicy"))
        assertTrue(main.contains("BindingWritePolicy.beforeSave"))
    }

    @Test
    fun debugAccessibilityConfigIsRestrictedToTheHarness() {
        val config = sourceRoot().resolve(
            "src/debug/res/xml/accessibility_service_config.xml",
        ).readText()
        assertTrue(config.contains("android:packageNames=\"com.company.cloudctl.inputharness\""))
        assertTrue(config.contains("android:canPerformGestures=\"false\""))
        assertTrue(config.contains("android:canTakeScreenshot=\"false\""))
        assertTrue(config.contains("flagInputMethodEditor"))
    }

    @Test
    fun productionAllowlistsDoNotContainTheHarness() {
        val registry = sourceRoot().resolve(
            "src/main/java/com/company/cloudctl/companion/automation/TargetLocatorRegistry.kt",
        ).readText()
        val parser = sourceRoot().resolve(
            "src/main/java/com/company/cloudctl/companion/automation/AutomationTask.kt",
        ).readText()
        assertFalse(registry.contains("inputharness"))
        assertFalse(parser.contains("inputharness"))
        assertTrue(parser.contains("TargetLocatorRegistry.XIANYU_PACKAGE"))
    }

    private fun sourceRoot(): File {
        val candidates = listOf(
            File("app"),
            File("mobile/companion/app"),
            File("../app"),
        )
        return candidates.firstOrNull { it.resolve("src/main").isDirectory }
            ?: error("companion app source root not found from ${File(".").absolutePath}")
    }
}
