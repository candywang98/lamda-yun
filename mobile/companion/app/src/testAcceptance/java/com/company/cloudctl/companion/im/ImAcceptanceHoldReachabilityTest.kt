package com.company.cloudctl.companion.im

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.data.ImOutboxStore
import java.io.File
import java.time.Instant
import org.json.JSONObject
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ImAcceptanceHoldReachabilityTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    @AfterTest
    fun tearDown() {
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
    }

    @Test
    fun acceptanceKeepsSyncAndAddsOnlyDumpProtectedReceiver() {
        val sources = moduleSources()
        val acceptance = File(sources, "acceptance/AndroidManifest.xml").readText()
        val main = File(sources, "main/AndroidManifest.xml").readText()
        val debug = File(sources, "debug/AndroidManifest.xml").readText()
        assertTrue(acceptance.contains("ImUploadHoldReceiver"))
        assertTrue(acceptance.contains("android:exported=\"true\""))
        assertTrue(acceptance.contains("android.permission.DUMP"))
        assertTrue(main.contains(".service.CompanionSyncService"))
        assertTrue(main.contains("android.permission.INTERNET"))
        assertFalse(main.contains("ImUploadHoldReceiver"))
        assertFalse(debug.contains("ImUploadHoldReceiver"))
        assertTrue(BuildConfig.IM_UPLOAD_HOLD_ALLOWED)
        assertEquals("com.company.cloudctl.companion.acceptance", BuildConfig.APPLICATION_ID)

        val receiver = context.packageManager.getReceiverInfo(
            ComponentName(context, ImUploadHoldReceiver::class.java),
            0,
        )
        assertTrue(receiver.exported)
        assertEquals("android.permission.DUMP", receiver.permission)
        val sync = context.packageManager.getServiceInfo(
            ComponentName(context, "com.company.cloudctl.companion.service.CompanionSyncService"),
            0,
        )
        assertEquals("com.company.cloudctl.companion.service.CompanionSyncService", sync.name)
    }

    @Test
    fun controlledBroadcastPersistsHoldWithoutInsertingAMessage() {
        val intent = Intent(ImUploadHold.ACTION)
            .setComponent(ComponentName(context, ImUploadHoldReceiver::class.java))
            .putExtra(ImUploadHold.EXTRA_HELD, true)
        val resolved = context.packageManager.queryBroadcastReceivers(intent, PackageManager.MATCH_DEFAULT_ONLY)
        assertTrue(resolved.any { it.activityInfo.name == ImUploadHoldReceiver::class.java.name })

        ImUploadHoldReceiver().onReceive(context, intent)
        val store = ImOutboxStore(context)
        try {
            assertTrue(store.uploadHeld())
            assertEquals(0, store.unconfirmed().size)
            assertEquals(0, store.counts().confirmed)
        } finally {
            store.close()
        }
    }

    @Test
    fun receiverPauseSurvivesReopenAndReleaseResumesDeliveryOnce() {
        val now = Instant.parse("2026-09-23T00:00:00Z")
        val event = ImEvent("xianyu", "buyer", "恢复测试", now)
        val receiver = ImUploadHoldReceiver()
        receiver.onReceive(context, Intent(ImUploadHold.ACTION).putExtra(ImUploadHold.EXTRA_HELD, true))
        var calls = 0
        val sender: (JSONObject) -> JSONObject = {
            calls++
            JSONObject().put("accepted", 1).put("duplicates", 0)
        }
        ImOutboxStore(context).use { store ->
            assertTrue(store.uploadHeld())
            store.enqueue("device-1", event, now)
            assertTrue(ImOutboxDelivery(store, sender) { now }.deliverOnce("device-1").held)
            assertEquals(0, calls)
        }
        ImOutboxStore(context).use { reopened ->
            assertTrue(reopened.uploadHeld())
            assertEquals(1, reopened.unconfirmed().size)
        }
        receiver.onReceive(context, Intent(ImUploadHold.ACTION).putExtra(ImUploadHold.EXTRA_HELD, false))
        ImOutboxStore(context).use { reopened ->
            assertFalse(reopened.uploadHeld())
            val delivery = ImOutboxDelivery(reopened, sender) { now }
            assertEquals(1, delivery.deliverOnce("device-1").confirmed)
            assertEquals(0, delivery.deliverOnce("device-1").sent)
            assertEquals(1, calls)
            assertEquals(0, reopened.unconfirmed().size)
        }
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
}
