package com.company.cloudctl.companion.im

import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ImMonitorTest {
    private fun event(peer: String = "buyer", text: String = "在吗", at: Instant = Instant.ofEpochSecond(1_800_000_000)) =
        ImEvent(platform = "xianyu", peerName = peer, text = text, occurredAt = at)

    @Test
    fun dedupesIdenticalEventsAndKeepsDistinctOnes() {
        assertTrue(ImMonitor.accept("device-1", event()))
        assertFalse(ImMonitor.accept("device-1", event()))
        assertTrue(ImMonitor.accept("device-1", event(text = "第二条")))
        // I10 retransmission contract: the SAME text re-observed one second
        // later (new second bucket) is a push re-post / duty re-read, not a
        // fresh message — it must not be queued or processed twice.
        assertFalse(ImMonitor.accept("device-1", event(at = Instant.ofEpochSecond(1_800_000_001))))
        assertEquals(2, ImMonitor.pendingCount())
        assertEquals(2, ImMonitor.drain(20).size)
        assertEquals(0, ImMonitor.pendingCount())
    }

    @Test
    fun requeueRestoresFailedBatchesForRetry() {
        ImMonitor.accept("device-1", event(text = "a"))
        val batch = ImMonitor.drain(20)
        ImMonitor.requeue(batch)
        assertEquals(1, ImMonitor.pendingCount())
        val retry = ImMonitor.drain(20)
        assertEquals(listOf("a"), retry.map { it.text })
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
        assertTrue(ImMonitor.isPackageEnabled("com.xingin.xhs"))
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
        assertTrue(ImMonitor.accept("device-1", event(peer = "re-peer", text = "九成新吗", at = base)))
        assertFalse(
            ImMonitor.accept("device-1", event(peer = "re-peer", text = "九成新吗", at = base.plusSeconds(3))),
        )
        assertFalse(
            ImMonitor.accept("device-1", event(peer = "re-peer", text = "九成新吗", at = base.plusSeconds(90))),
        )
        assertEquals(1, ImMonitor.pendingCount())
        ImMonitor.drain(20)
    }

    @Test
    fun retransmissionWindowIsBoundedAndIdentityScoped() {
        val base = Instant.ofEpochSecond(1_800_000_000)
        val beyond = base.plusMillis(ImMonitor.RETRANSMIT_WINDOW_MS + 1_000)
        // Outside the window the same text is a genuinely fresh message.
        assertTrue(ImMonitor.accept("device-1", event(peer = "win-peer", text = "有发票吗", at = base)))
        assertTrue(ImMonitor.accept("device-1", event(peer = "win-peer", text = "有发票吗", at = beyond)))
        // Different peer, same text: distinct source identity, both fresh.
        assertTrue(ImMonitor.accept("device-1", event(peer = "other-peer", text = "有发票吗", at = base.plusSeconds(5))))
        // Out-of-order occurrences never count as retransmissions.
        assertTrue(ImMonitor.accept("device-1", event(peer = "win-peer", text = "有发票吗", at = base.plusSeconds(10))))
        assertEquals(4, ImMonitor.pendingCount())
        ImMonitor.drain(20)
    }
}
