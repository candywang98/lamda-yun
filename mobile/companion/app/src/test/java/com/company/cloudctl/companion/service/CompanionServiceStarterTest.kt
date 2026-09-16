package com.company.cloudctl.companion.service

import android.app.Application
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.test.core.app.ApplicationProvider
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/** B11 任务 2：启动异常被分类而非崩溃；specialUse 声明保持原样。 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CompanionServiceStarterTest {
    private lateinit var context: Context
    private lateinit var application: Application

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        application = context as Application
        clearBinding()
    }

    @AfterTest
    fun tearDown() {
        clearBinding()
    }

    @Test
    fun `without binding no start is attempted and NotBound is reported`() {
        var launches = 0
        val attempt = CompanionServiceStarter.tryStartIfBound(context) { _, _ -> launches++ }

        assertIs<ServiceStartAttempt.NotBound>(attempt)
        assertEquals(0, launches)
        assertEquals(false, CompanionServiceStarter.startIfBound(context))
        assertNull(shadowOf(application).nextStartedService)
    }

    @Test
    fun `with binding the sync service is started in the foreground`() {
        writeBinding()
        var launches = 0
        var launchedIntent: Intent? = null
        val attempt = CompanionServiceStarter.tryStartIfBound(context) { _, intent ->
            launches++
            launchedIntent = intent
        }

        assertIs<ServiceStartAttempt.Started>(attempt)
        assertEquals(1, launches)
        assertEquals(CompanionSyncService::class.java.name, launchedIntent!!.component?.className)
        assertEquals(true, CompanionServiceStarter.startIfBound(context))
    }

    @Test
    fun `platform refusals are classified instead of crashing the caller`() {
        writeBinding()
        val notAllowed = CompanionServiceStarter.tryStartIfBound(context) { _, _ ->
            throw android.app.ForegroundServiceStartNotAllowedException("bg restriction")
        }
        assertEquals("START_NOT_ALLOWED", (notAllowed as ServiceStartAttempt.Refused).reasonCode)

        val illegal = CompanionServiceStarter.tryStartIfBound(context) { _, _ -> throw IllegalStateException("not a service") }
        assertEquals("FOREGROUND_START_ILLEGAL_STATE", (illegal as ServiceStartAttempt.Refused).reasonCode)

        val security = CompanionServiceStarter.tryStartIfBound(context) { _, _ -> throw SecurityException("missing permission") }
        assertEquals("FOREGROUND_START_SECURITY", (security as ServiceStartAttempt.Refused).reasonCode)

        assertTrue(
            CompanionServiceStarter.tryStartIfBound(context) { _, _ -> throw IllegalStateException("no") }
                is ServiceStartAttempt.Refused,
        )
    }

    @Test
    fun `manifest keeps the sync service declared as specialUse`() {
        val info = context.packageManager.getServiceInfo(
            ComponentName(context, CompanionSyncService::class.java),
            PackageManager.GET_META_DATA,
        )
        assertTrue(
            info.foregroundServiceType and ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE != 0,
            "manifest must keep specialUse (current type=${info.foregroundServiceType})",
        )
        if (Build.VERSION.SDK_INT >= 34) {
            assertTrue(info.foregroundServiceType and ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC == 0)
        }
    }

    private fun writeBinding() {
        context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE)
            .edit()
            .putString("binding", """{"cloudUrl":"https://cloud.example"}""")
            .commit()
    }

    private fun clearBinding() {
        context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE)
            .edit()
            .remove("binding")
            .commit()
    }
}
