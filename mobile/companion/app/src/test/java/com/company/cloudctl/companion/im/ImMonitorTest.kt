package com.company.cloudctl.companion.im

import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ImMonitorTest {
    private fun event(peer: String = "buyer", text: String = "在吗", at: Instant = Instant.ofEpochSecond(1_800_000_000)) =
        ImEvent(peerName = peer, text = text, occurredAt = at)

    @Test
    fun dedupesIdenticalEventsAndKeepsDistinctOnes() {
        assertTrue(ImMonitor.accept("device-1", event()))
        assertFalse(ImMonitor.accept("device-1", event()))
        assertTrue(ImMonitor.accept("device-1", event(text = "第二条")))
        assertTrue(ImMonitor.accept("device-1", event(at = Instant.ofEpochSecond(1_800_000_001))))
        assertEquals(3, ImMonitor.pendingCount())
        assertEquals(3, ImMonitor.drain(20).size)
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
}
