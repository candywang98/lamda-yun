package com.company.cloudctl.companion.im

import java.io.File
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Source-set shape of the C6 install. Runs on every unit-test variant because
 * it only reads the manifests, not the acceptance-only service class.
 */
class ImUploadHoldVariantManifestTest {
    @Test
    fun acceptanceAddsOnlyTheShellControlledHoldReceiver() {
        val sources = moduleSources()
        val acceptance = File(sources, "acceptance/AndroidManifest.xml").readText()
        val debug = File(sources, "debug/AndroidManifest.xml").readText()
        val main = File(sources, "main/AndroidManifest.xml").readText()
        assertTrue(acceptance.contains("ImUploadHoldReceiver"))
        assertTrue(acceptance.contains("android:exported=\"true\""))
        assertTrue(acceptance.contains("android.permission.DUMP"))
        assertFalse(acceptance.contains("tools:node=\"remove\""))
        assertTrue(debug.contains("CompanionSyncService"))
        assertTrue(debug.contains("tools:node=\"remove\""))
        assertFalse(debug.contains("ImUploadHoldReceiver"))
        assertTrue(main.contains("CompanionSyncService"))
        assertTrue(main.contains("android.permission.INTERNET"))
        assertFalse(main.contains("ImUploadHoldReceiver"))
        assertFalse(File(sources, "release/java/com/company/cloudctl/companion/im/ImUploadHoldReceiver.kt").isFile)
        assertTrue(File(sources, "acceptance/java/com/company/cloudctl/companion/im/ImUploadHoldReceiver.kt").isFile)
    }

    @Test
    fun releaseBuildTypeDoesNotAllowTheHoldAndAcceptanceDoes() {
        val gradle = moduleGradle().readText()
        val release = gradle.substringAfter("release {").substringBefore("create(\"acceptance\")")
        val acceptance = gradle.substringAfter("create(\"acceptance\")").substringBefore("sourceSets")
        assertFalse(release.contains("IM_UPLOAD_HOLD_ALLOWED\", \"true\""))
        assertTrue(acceptance.contains("applicationIdSuffix = \".acceptance\""))
        assertTrue(acceptance.contains("matchingFallbacks += listOf(\"release\")"))
        assertTrue(acceptance.contains("IM_UPLOAD_HOLD_ALLOWED\", \"true\""))
        assertTrue(gradle.contains("IM_UPLOAD_HOLD_ALLOWED\", \"false\""))
    }

    private fun moduleSources(): File {
        var dir = File("").absoluteFile
        repeat(6) {
            val candidate = File(dir, "src")
            if (File(candidate, "acceptance/AndroidManifest.xml").isFile) return candidate
            dir = dir.parentFile ?: return@repeat
        }
        error("acceptance manifest not found from ${File("").absolutePath}")
    }

    private fun moduleGradle(): File {
        var dir = File("").absoluteFile
        repeat(6) {
            val candidate = File(dir, "build.gradle.kts")
            if (candidate.isFile && candidate.readText().contains("IM_UPLOAD_HOLD_ALLOWED")) return candidate
            dir = dir.parentFile ?: return@repeat
        }
        error("app gradle not found from ${File("").absolutePath}")
    }
}
