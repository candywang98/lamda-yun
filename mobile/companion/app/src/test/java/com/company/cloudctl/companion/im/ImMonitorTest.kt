package com.company.cloudctl.companion.im

import com.company.cloudctl.companion.BuildConfig
import java.time.Instant
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ImMonitorTest {
    @AfterTest
    fun clearMemoryHint() {
        ImMonitor.resetForTest()
    }
    private fun event(peer: String = "buyer", text: String = "在吗", at: Instant = Instant.ofEpochSecond(1_800_000_000)) =
        ImEvent(platform = "xianyu", peerName = peer, text = text, occurredAt = at)

    @Test
    fun dedupesIdenticalEventsAndKeepsDistinctOnes() {
        assertFalse(ImMonitor.alreadyRecorded("device-1", event()))
        ImMonitor.noteAccepted("device-1", event())
        assertTrue(ImMonitor.alreadyRecorded("device-1", event()))
        assertFalse(ImMonitor.alreadyRecorded("device-1", event(text = "第二条")))
        ImMonitor.noteAccepted("device-1", event(text = "第二条"))
        // I10 retransmission contract: the SAME canonical text re-observed one
        // second later is a push re-post, not a fresh memory hint.
        assertTrue(ImMonitor.alreadyRecorded("device-1", event(at = Instant.ofEpochSecond(1_800_000_001))))
    }

    @Test
    fun dedupeKeyBindsDevicePeerBucketAndText() {
        val a = event().dedupeKey("device-1")
        assertEquals(a, event().dedupeKey("device-1"))
        assertFalse(a == event().dedupeKey("device-2"))
        assertFalse(a == event(text = "x").dedupeKey("device-1"))
    }

    @Test
    fun configGatesPackagesBySelectedPlatforms() {
        ImMonitor.applyConfig(ImMonitorConfig(platforms = setOf("xhs")))
        assertEquals(!BuildConfig.HEARTBEAT_DIAGNOSTIC, ImMonitor.isPackageEnabled("com.xingin.xhs"))
        assertFalse(ImMonitor.isPackageEnabled("com.taobao.idlefish"))
        assertFalse(ImMonitor.isPackageEnabled("com.unknown.app"))
        ImMonitor.applyConfig(ImMonitorConfig(enabled = false, platforms = setOf("xhs")))
        assertFalse(ImMonitor.isPackageEnabled("com.xingin.xhs"))
        ImMonitor.applyConfig(ImMonitorConfig())
    }

    @Test
    fun dutyWindowRespectsModeAndCrossesMidnight() {
        val day = ImMonitorConfig(mode = "DUTY", dutyStart = "09:00", dutyEnd = "23:00")
        assertTrue(day.dutyActive(java.time.LocalTime.of(12, 0)))
        assertFalse(day.dutyActive(java.time.LocalTime.of(23, 30)))
        val night = ImMonitorConfig(mode = "DUTY", dutyStart = "22:00", dutyEnd = "06:00")
        assertTrue(night.dutyActive(java.time.LocalTime.of(2, 0)))
        assertFalse(ImMonitorConfig(mode = "NOTIFICATION").dutyActive(java.time.LocalTime.of(12, 0)))
    }

    @Test
    fun channelFilterBlocksFeedPushesForNonXianyuPlatforms() {
        assertTrue(ImMonitorConfig.isChannelAllowed("xianyu", null))
        assertTrue(ImMonitorConfig.isChannelAllowed("xianyu", "anything"))
        assertTrue(ImMonitorConfig.isChannelAllowed("xhs", "message_push"))
        assertFalse(ImMonitorConfig.isChannelAllowed("xhs", "push_oplus_category_content"))
        assertFalse(ImMonitorConfig.isChannelAllowed("douyin", "pre84"))
        assertFalse(ImMonitorConfig.isChannelAllowed("wechat", null))
    }

    @Test
    fun dedupeKeyBindsPlatform() {
        val a = event().dedupeKey("device-1")
        assertFalse(a == ImEvent("xhs", "buyer", "在吗", Instant.ofEpochSecond(1_800_000_000)).dedupeKey("device-1"))
    }

    // I10 — inbound retransmission window (platform|peer|text identity).

    @Test
    fun retransmittedPushInsideTheWindowIsDropped() {
        val base = Instant.ofEpochSecond(1_800_000_000)
        // Same peer+text re-observed seconds apart (push re-post / duty re-read
        // with a fabricated now()): dropped, never processed twice.
        assertFalse(ImMonitor.alreadyRecorded("device-1", event(peer = "re-peer", text = "九成新吗", at = base)))
        ImMonitor.noteAccepted("device-1", event(peer = "re-peer", text = "九成新吗", at = base))
        assertTrue(
            ImMonitor.alreadyRecorded("device-1", event(peer = "re-peer", text = "九成新吗", at = base.plusSeconds(3))),
        )
        assertTrue(
            ImMonitor.alreadyRecorded("device-1", event(peer = "re-peer", text = "九成新吗", at = base.plusSeconds(90))),
        )
    }

    @Test
    fun retransmissionWindowIsBoundedAndIdentityScoped() {
        val base = Instant.ofEpochSecond(1_800_000_000)
        // The window is strict `< RETRANSMIT_WINDOW_MS`, so the boundary itself is fresh.
        val beyond = base.plusMillis(ImMonitor.RETRANSMIT_WINDOW_MS)
        // Outside the window the same text is a genuinely fresh message.
        assertFalse(ImMonitor.alreadyRecorded("device-1", event(peer = "win-peer", text = "有发票吗", at = base)))
        ImMonitor.noteAccepted("device-1", event(peer = "win-peer", text = "有发票吗", at = base))
        assertFalse(ImMonitor.alreadyRecorded("device-1", event(peer = "win-peer", text = "有发票吗", at = beyond)))
        // Different peer, same text: distinct source identity, both fresh.
        assertFalse(ImMonitor.alreadyRecorded("device-1", event(peer = "other-peer", text = "有发票吗", at = base.plusSeconds(5))))
        // An earlier occurrence is not a retransmission of the later one.
        assertFalse(ImMonitor.alreadyRecorded("device-1", event(peer = "win-peer", text = "有发票吗", at = base.minusSeconds(10))))
    }
}
