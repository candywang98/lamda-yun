package com.company.cloudctl.companion.device

import android.app.KeyguardManager
import android.content.Context
import android.provider.Settings
import androidx.test.core.app.ApplicationProvider
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/** B11：readiness 各维度经真实系统服务分别采集、分别上报。 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class LocalHealthCollectorReadinessTest {
    private lateinit var context: Context
    private lateinit var collector: LocalHealthCollector

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        collector = LocalHealthCollector(context)
        Settings.Secure.putString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES, null)
    }

    @Test
    fun `default device reports every dimension separately`() {
        val snapshot = collector.collectReadiness(
            transportOnline = true,
            activeAccessibilityService = { null },
        )
        assertTrue(snapshot.transportOnline)
        assertFalse(snapshot.accessibilityEnabled)
        assertFalse(snapshot.accessibilityActive)
        assertFalse(snapshot.imeReady)
        assertTrue(snapshot.screenUnlocked)
        assertEquals(ClaimEligibilityPolicy.ENGINE_FLOOR, snapshot.engineVersion)
    }

    @Test
    fun `accessibility enabled is read from the secure setting`() {
        Settings.Secure.putString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            "${context.packageName}/${context.packageName}.automation.CloudCtlAccessibilityService",
        )
        val enabled = collector.collectReadiness(transportOnline = true, activeAccessibilityService = { null })
        assertTrue(enabled.accessibilityEnabled)

        Settings.Secure.putString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            "com.other.app/.OtherService",
        )
        val disabled = collector.collectReadiness(transportOnline = true, activeAccessibilityService = { null })
        assertFalse(disabled.accessibilityEnabled)
    }

    @Test
    fun `accessibility active reflects the bound instance independent of the setting`() {
        // 设置关闭但实例仍在（关闭瞬态）：两个维度必须能各自表达。
        val instance = Any()
        val snapshot = collector.collectReadiness(
            transportOnline = true,
            activeAccessibilityService = { instance },
        )
        assertFalse(snapshot.accessibilityEnabled)
        assertTrue(snapshot.accessibilityActive)
    }

    @Test
    fun `locked keyguard reports screen locked`() {
        val keyguard = context.getSystemService(KeyguardManager::class.java)
        shadowOf(keyguard).setKeyguardLocked(true)
        val snapshot = collector.collectReadiness(transportOnline = true, activeAccessibilityService = { null })
        assertFalse(snapshot.screenUnlocked)
    }

    @Test
    fun `api33 active accessibility is input ready without the cloudctl keyboard`() {
        // This test class runs on SDK 35. Input capability must not require the
        // user to enable or select CloudCtl Input.
        val snapshot = collector.collectReadiness(
            transportOnline = true,
            activeAccessibilityService = { Any() },
        )
        assertTrue(snapshot.accessibilityActive)
        assertTrue(snapshot.imeReady)
        assertFalse(snapshot.accessibilityEnabled)
    }

    @Test
    fun `transport online is carried through, not guessed`() {
        val offline = collector.collectReadiness(transportOnline = false, activeAccessibilityService = { null })
        assertFalse(offline.transportOnline)
    }
}
