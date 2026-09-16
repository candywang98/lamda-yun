package com.company.cloudctl.companion.device

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** B11 验收：上报合并 + 断网缓存上限（丢最旧），告警不会以风暴形式重放。 */
class HealthReportBufferTest {
    @Test
    fun `same alert inside the merge window coalesces into one slot`() {
        val buffer = HealthReportBuffer(capacity = 16, mergeWindowMillis = 60_000L)
        repeat(50) { index ->
            buffer.add(alert("dev-1:battery_low", digest = "v1"), nowMillis = index * 1_000L)
        }

        assertEquals(1, buffer.size())
        val slot = buffer.snapshot().single()
        assertEquals(50, slot.mergedCount)
        assertEquals(0L, slot.firstSeenAtMillis)
        assertEquals(49_000L, slot.lastSeenAtMillis)
    }

    @Test
    fun `merged alerts drain as one upload entry instead of N`() {
        val buffer = HealthReportBuffer()
        repeat(100) { buffer.add(alert("dev-7:offline"), nowMillis = it * 100L) }
        val drained = buffer.drain()
        assertEquals(1, drained.size)
        assertEquals(100, drained.single().mergedCount)
        assertEquals(0, buffer.size())
        assertTrue(buffer.snapshot().isEmpty())
    }

    @Test
    fun `different digests for the same key stay separate`() {
        val buffer = HealthReportBuffer()
        buffer.add(alert("dev-1:battery_low", digest = "v1"), nowMillis = 0L)
        buffer.add(alert("dev-1:battery_low", digest = "v2"), nowMillis = 1_000L)
        assertEquals(2, buffer.size())
    }

    @Test
    fun `same digest outside the merge window starts a new slot`() {
        val buffer = HealthReportBuffer(mergeWindowMillis = 60_000L)
        buffer.add(alert("dev-1:offline"), nowMillis = 0L)
        buffer.add(alert("dev-1:offline"), nowMillis = 61_000L)
        assertEquals(2, buffer.size())
    }

    @Test
    fun `offline cache is capped by dropping the oldest entries`() {
        val buffer = HealthReportBuffer(capacity = 4, mergeWindowMillis = 0L)
        for (index in 0 until 6) {
            buffer.add(alert("dev-$index:alert"), nowMillis = index * 1_000L)
        }

        assertEquals(4, buffer.size())
        // 丢最旧，保留最新四条。
        assertEquals(
            listOf("dev-2:alert", "dev-3:alert", "dev-4:alert", "dev-5:alert"),
            buffer.snapshot().map { it.alert.key },
        )
        assertEquals(5_000L, buffer.snapshot().last().lastSeenAtMillis)
    }

    @Test
    fun `capacity evicts the oldest slot even a merged hot alert`() {
        val buffer = HealthReportBuffer(capacity = 2, mergeWindowMillis = 60_000L)
        repeat(30) { buffer.add(alert("hot:flap"), nowMillis = it * 10L) }
        buffer.add(alert("other:1"), nowMillis = 1L)
        buffer.add(alert("other:2"), nowMillis = 2L)

        // hot:flap 先入队，容量满了按最旧淘汰；最新两条保留。
        assertEquals(2, buffer.size())
        assertEquals(listOf("other:1", "other:2"), buffer.snapshot().map { it.alert.key })
    }

    private fun alert(key: String, digest: String = "d") = HealthAlert(
        key = key,
        digest = digest,
        severity = "WARN",
        occurredAtMillis = 0L,
    )
}
