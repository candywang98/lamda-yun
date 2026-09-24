package com.company.cloudctl.companion.automation

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.SystemClock
import android.provider.Settings
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.company.cloudctl.companion.ime.InputProofProjection
import com.company.cloudctl.companion.ime.InputProofProjector
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Device entry for the one fixed diagnostic input.
 *
 * Instrumentation arguments are not read. The fixture, package and field are
 * the constants compiled into [DiagnosticInputStepRunner]. A missing harness,
 * a missing accessibility connection, or any result other than INPUT_VERIFIED
 * fails. There is no soft pass.
 *
 * The test brings the already-installed harness activity to the foreground with
 * no extras. The runner then calls [LocalAutomationExecutor] on the connected
 * accessibility service. It does not call [CloudCtlAccessibilityService.execute],
 * so the service does not launch, go back, or restart the target.
 *
 * Enabling the accessibility service is a user action in system settings. This
 * test does not write that setting. If the user has not enabled
 * com.company.cloudctl.companion.debug's service, the result is
 * ACCESSIBILITY_NOT_ACTIVE and the test fails.
 */
@RunWith(AndroidJUnit4::class)
class DiagnosticInputDeviceTest {
    @Test
    fun debugPackageIsBesideProductionAndHasNoClaimComponents() {
        val target = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("com.company.cloudctl.companion.debug", target.packageName)
        assertNotEquals("com.company.cloudctl.companion", target.packageName)
        val info = target.packageManager.getPackageInfo(
            target.packageName,
            PackageManager.GET_SERVICES or PackageManager.GET_RECEIVERS or
                PackageManager.GET_ACTIVITIES or PackageManager.GET_PERMISSIONS,
        )
        val services = info.services?.map { it.name }.orEmpty()
        val receivers = info.receivers?.map { it.name }.orEmpty()
        val activities = info.activities?.map { it.name }.orEmpty()
        val permissions = info.requestedPermissions?.toList().orEmpty()
        assertEquals(
            listOf("com.company.cloudctl.companion.automation.CloudCtlAccessibilityService"),
            services,
        )
        assertTrue(receivers.none { it.startsWith("com.company.cloudctl.companion") })
        assertTrue(activities.isEmpty())
        assertFalse(permissions.contains(android.Manifest.permission.INTERNET))
        assertFalse(permissions.contains(android.Manifest.permission.ACCESS_NETWORK_STATE))
        assertFalse(permissions.contains(android.Manifest.permission.RECEIVE_BOOT_COMPLETED))
        assertFalse(permissions.contains(android.Manifest.permission.FOREGROUND_SERVICE))
        assertFalse(permissions.contains(android.Manifest.permission.REQUEST_INSTALL_PACKAGES))
        assertNull(bindingOf(target))
    }

    @Test
    fun fixedFixtureIsVerifiedOnceWithoutChangingTheKeyboard() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val target = instrumentation.targetContext
        assertNull(bindingOf(target))
        val resolver = target.contentResolver
        val imeBefore = Settings.Secure.getString(resolver, Settings.Secure.DEFAULT_INPUT_METHOD)

        val launch = target.packageManager.getLaunchIntentForPackage(DebugDiagnosticInputPolicy.PACKAGE)
        assertNotNull("input harness is not installed", launch)
        launch!!.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        target.startActivity(launch)
        instrumentation.waitForIdleSync()

        val projection = awaitWriteOrGiveUp()
        val imeAfter = Settings.Secure.getString(resolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        assertEquals(imeBefore, imeAfter)
        assertNull(bindingOf(target))

        assertEquals("INPUT_VERIFIED", projection.resultCode)
        assertEquals(1, projection.commitCount)
        assertEquals("ACCESSIBILITY", projection.channel)
        assertTrue(projection.selectionKnown)
        assertEquals(DiagnosticInputStepRunner.FIXTURE.length, projection.utf16Length)
        assertTrue(projection.generation >= 0L)
        assertTrue(projection.textSha256.matches(SHA256))
        assertTrue(projection.fieldSha256.matches(SHA256))
        assertNotNull(projection.nodeKeySha256)
        assertTrue(projection.nodeKeySha256!!.matches(SHA256))
        assertEquals(InputProofProjector.sha256(DiagnosticInputStepRunner.FIXTURE), projection.textSha256)
        val rendered = projection.toString()
        assertFalse(rendered.contains("你好"))
        assertFalse(rendered.contains("第二行"))
        // Complete safe projection. No fixture text.
        println(
            "DIAG_INPUT result=${projection.resultCode}" +
                " utf16Length=${projection.utf16Length}" +
                " textSha256=${projection.textSha256}" +
                " generation=${projection.generation}" +
                " fieldSha256=${projection.fieldSha256}" +
                " nodeKeySha256=${projection.nodeKeySha256}" +
                " selectionKnown=${projection.selectionKnown}" +
                " channel=${projection.channel}" +
                " commitCount=${projection.commitCount}",
        )
    }

    /**
     * The accessibility service may bind a moment after the test process starts,
     * and the harness window may not be active on the first look. Those two
     * results happen before [replaceText], so repeating them cannot commit.
     * The first result that is not one of those is returned as-is and then
     * asserted. A rejection is not retried into a second commit.
     */
    private fun awaitWriteOrGiveUp(): InputProofProjection {
        val deadline = SystemClock.elapsedRealtime() + 8_000L
        var latest: InputProofProjection? = null
        while (SystemClock.elapsedRealtime() < deadline) {
            val projection = runBlocking {
                DiagnosticInputStepRunner.runFixedOnActiveService(android.os.Build.VERSION.SDK_INT)
            }
            latest = projection
            if (projection.resultCode !in BEFORE_WRITE) return projection
            SystemClock.sleep(400)
        }
        return checkNotNull(latest)
    }

    private fun bindingOf(target: Context): String? =
        target.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE)
            .getString("binding", null)

    private companion object {
        val SHA256 = Regex("^[0-9a-f]{64}$")
        val BEFORE_WRITE = setOf(
            "ACCESSIBILITY_NOT_ACTIVE",
            "WRONG_ACTIVE_PACKAGE",
            "ACTIVE_WINDOW_MISSING",
        )
    }
}
