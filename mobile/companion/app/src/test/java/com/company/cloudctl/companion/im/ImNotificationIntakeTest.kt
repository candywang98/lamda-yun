package com.company.cloudctl.companion.im

import android.app.Notification
import android.content.Context
import android.view.accessibility.AccessibilityEvent
import androidx.test.core.app.ApplicationProvider
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.data.ImOutboxStore
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONObject
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowLog

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ImNotificationIntakeTest {
    private lateinit var context: Context
    private lateinit var store: ImOutboxStore
    private lateinit var service: CloudCtlAccessibilityService
    private val sourceTime = 1_800_000_000_123L

    @BeforeTest
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
        context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE).edit().clear().commit()
        store = ImOutboxStore(context)
        ImMonitor.resetForTest()
        ImMonitor.outbox = store
        ImMonitor.applyConfig(ImMonitorConfig())
        ImFeedNoiseFilter.resetCalibration()
        service = Robolectric.buildService(CloudCtlAccessibilityService::class.java).create().get()
    }

    @AfterTest
    fun tearDown() {
        service.onDestroy()
        store.close()
        context.deleteDatabase(ImOutboxStore.DATABASE_NAME)
        ImMonitor.resetForTest()
        ImMonitor.applyConfig(ImMonitorConfig())
        ImFeedNoiseFilter.resetCalibration()
    }

    private fun notify(
        title: String,
        body: String = "发来一条新消息",
        channel: String = "guessed-feed",
        pkg: String = ImNotificationMetadata.XIANYU_PACKAGE,
        whenMillis: Long = sourceTime,
    ) {
        val notification = Notification.Builder(context, channel)
            .setContentTitle(title)
            .setContentText(body)
            .setCategory(Notification.CATEGORY_MESSAGE)
            .setWhen(whenMillis)
            .build()
        // Extras other than the allowlisted context must not be serialized.
        notification.extras.putString("private-extra", "never-upload-this")
        val event = AccessibilityEvent(AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED).apply {
            packageName = pkg
            parcelableData = notification
        }
        service.onAccessibilityEvent(event)
    }

    @Test
    fun realNamesAndAllNoiseHintsStillReachUploadThroughCallback() {
        ImFeedNoiseFilter.calibrate(ImFeedNoiseFilter.NoiseProfile(
            feedChannels = setOf("feed"),
            dmChannels = setOf("dm"),
            systemSources = setOf("闲鱼小蜜"),
            marketingPeerKeywords = ImFeedNoiseFilter.FEED_PEER_KEYWORDS + "清仓",
            peerNameMaxLength = 1,
        ))
        val names = listOf(
            "张起灵", "一起看海", "小陈捡漏", "周末清仓", "买家".repeat(20),
            "a".repeat(128), "\uD83D\uDE00".repeat(128), "买家\n小王", "系统通知", "官方公告", "闲鱼小蜜",
        )
        names.forEach { notify(it) }
        assertEquals(names, store.unconfirmed().map { it.peerName })
        assertEquals(ImMonitorConfig.MODE_NOTIFICATION, ImMonitor.config.mode)
        val report = ImOutboxDelivery(store, { payload ->
            val messages = payload.getJSONArray("messages")
            assertEquals(names.size, messages.length())
            repeat(messages.length()) { index ->
                val row = messages.getJSONObject(index)
                assertEquals(names[index], row.getString("peerName"))
                assertEquals("发来一条新消息", row.getString("text"))
                assertEquals(Instant.ofEpochMilli(sourceTime).toString(), row.getString("occurredAt"))
                val metadata = row.getJSONObject("notificationMetadata")
                assertEquals(3, metadata.length())
                assertEquals(ImNotificationMetadata.XIANYU_PACKAGE, metadata.getString("packageName"))
                assertEquals("guessed-feed", metadata.getString("channelId"))
                assertEquals("msg", metadata.getString("category"))
                assertFalse(row.toString().contains("never-upload-this"))
            }
            JSONObject().put("accepted", names.size).put("duplicates", 0)
        }).deliverOnce("device-1")
        assertEquals(names.size, report.confirmed)
    }

    @Test
    fun unknownChannelAndMissingMetadataDoNotRequireDmProof() {
        ImFeedNoiseFilter.calibrate(ImFeedNoiseFilter.NoiseProfile(dmChannels = setOf("dm")))
        notify("张起灵", channel = "unknown")
        val observed = assertNotNull(ImNotificationIntake.observe("xianyu", "李起", "在吗", sourceTime, sourceTime))
        assertNull(observed.notificationMetadata)
        assertEquals(ImEnqueueResult.ENQUEUED, ImNotificationIntake.accept(store, null, observed).result)
        assertEquals(2, store.unconfirmed().size)
    }

    @Test
    fun plaintextTitleBodyAndUntrustedChannelNeverAppearInLogs() {
        notify("private-title", body = "private-body", channel = "private-channel", whenMillis = 0)
        assertEquals(1, store.unconfirmed().size)
        val logs = ShadowLog.getLogs().joinToString("\n") { it.msg }
        for (privateValue in listOf("private-title", "private-body", "private-channel")) {
            assertFalse(logs.contains(privateValue))
        }
        assertTrue(logs.contains("OCCURRED_AT_SYNTHESIZED"))
    }

    @Test
    fun disabledAndOtherPlatformsRemainOutsideIntake() {
        ImMonitor.applyConfig(ImMonitorConfig(enabled = false))
        notify("买家")
        ImMonitor.applyConfig(ImMonitorConfig(platforms = setOf("xianyu", "xhs", "douyin", "wechat")))
        for (pkg in listOf("com.xingin.xhs", "com.ss.android.ugc.aweme", "com.tencent.mm", "unknown")) {
            notify("买家", pkg = pkg)
        }
        assertTrue(store.unconfirmed().isEmpty())
    }

    @Test
    fun invalidEventsStillRespectExistingContractValidation() {
        for ((title, body) in listOf(
            "" to "body", "peer" to "", "a".repeat(129) to "body", "\uD83D\uDE00".repeat(129) to "body",
        )) {
            notify(title, body)
        }
        assertTrue(store.unconfirmed().isEmpty())
        assertNull(ImNotificationIntake.observe("xhs", "peer", "body", sourceTime, sourceTime))
    }

    @Test
    fun timestampFallbackAndMetadataDoNotChangeDedupeIdentity() {
        val metadata = ImNotificationMetadata(ImNotificationMetadata.XIANYU_PACKAGE, "feed", "msg")
        val observed = assertNotNull(ImNotificationIntake.observe(
            "xianyu", "买家", "在吗", 0, sourceTime, metadata,
        ))
        assertTrue(observed.occurredAtSynthesized)
        val first = ImNotificationIntake.accept(store, "device-1", observed)
        val duplicate = ImNotificationIntake.accept(store, "device-1", observed.copy(
            notificationMetadata = metadata.copy(channelId = "dm"),
        ))
        assertEquals(ImEnqueueResult.DUPLICATE, duplicate.result)
        assertEquals(first.dedupeKey, duplicate.dedupeKey)
        assertEquals(Instant.ofEpochMilli(sourceTime), duplicate.event!!.occurredAt)
        assertEquals(metadata, duplicate.event.notificationMetadata)
        assertEquals(ImEvent("xianyu", "买家", "在吗", observed.occurredAt).dedupeKey("device-1"), first.dedupeKey)
    }
}
