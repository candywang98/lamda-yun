package com.company.cloudctl.inputharness

import android.widget.EditText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HarnessSurfaceTest {
    @Test
    fun activityShowsOneEmptyMultilineField() {
        val controller = Robolectric.buildActivity(HarnessActivity::class.java).setup()
        val field = controller.get().findViewById<EditText>(R.id.harness_multiline_field)
        assertEquals("", field.text.toString())
        assertTrue(field.isEnabled)
        assertFalse(field.isSingleLine)
    }

    @Test
    fun manifestHasNoNetworkOrBusinessPermissions() {
        val manifest = locate("app/src/main/AndroidManifest.xml").readText()
        assertFalse(manifest.contains("uses-permission"))
        assertFalse(manifest.contains("android.permission.INTERNET"))
        assertFalse(manifest.contains("ACCESS_NETWORK_STATE"))
        assertFalse(manifest.contains("<queries"))
        assertFalse(manifest.contains("idlefish"))
        assertFalse(manifest.contains("clipboard"))
        assertFalse(manifest.contains("Button"))
        // The exported launcher is how the instrumentation test starts the field.
        // Nothing else is exported: no deep link, receiver, service, or provider.
        assertTrue(manifest.contains("android.intent.action.MAIN"))
        assertTrue(manifest.contains("android.intent.category.LAUNCHER"))
        assertFalse(manifest.contains("android.intent.action.VIEW"))
        assertFalse(manifest.contains("<receiver"))
        assertFalse(manifest.contains("<service"))
        assertFalse(manifest.contains("<provider"))
        assertFalse(manifest.contains("intent-filter") && manifest.contains("BROWSABLE"))
        assertEquals(1, Regex("<activity").findAll(manifest).count())
    }

    @Test
    fun layoutHasNoActionControls() {
        val layout = locate("app/src/main/res/layout/activity_harness.xml").readText()
        assertTrue(layout.contains("@+id/harness_multiline_field"))
        assertFalse(layout.contains("Button"))
        assertFalse(layout.contains("发送"))
        assertFalse(layout.contains("发布"))
        assertFalse(layout.contains("评价"))
        assertFalse(layout.contains("确定"))
        assertFalse(layout.contains("clipboard"))
    }

    @Test
    fun releaseTaskIsDisabledInGradle() {
        val gradle = locate("app/build.gradle.kts").readText()
        assertTrue(gradle.contains("withBuildType(\"release\")"))
        assertTrue(gradle.contains("variant.enable = false"))
        assertTrue(gradle.contains("assertReleaseVariantAbsent"))
    }

    private fun locate(relative: String): File {
        val candidates = listOf(
            File(relative),
            File("app").takeIf { false },
            File(System.getProperty("user.dir"), relative),
        )
        // Robolectric's cwd is the module root (mobile/input-harness) or app/.
        val roots = listOf(File("."), File(".."), File("../.."))
        for (root in roots) {
            val file = File(root, relative)
            if (file.isFile) return file
        }
        error("missing $relative from ${File(".").absolutePath}; tried $candidates")
    }
}
