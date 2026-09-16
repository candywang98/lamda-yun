package com.company.cloudctl.companion.device

import kotlin.math.floor
import kotlin.math.min
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * B11 验收：网络退避 + jitter；不同设备的健康重连不构成重试风暴
 * （退避上界与抖散均可断言）。
 */
class ReconnectBackoffTest {
    @Test
    fun `exponential backoff with no jitter grows to the cap and resets`() {
        val backoff = ReconnectBackoff(
            initialDelayMillis = 1_000,
            maximumDelayMillis = 8_000,
            jitter = { 1.0 },
        )
        assertEquals(listOf(1_000L, 2_000L, 4_000L, 8_000L, 8_000L), List(5) { backoff.nextDelayMillis() })
        backoff.reset()
        assertEquals(1_000L, backoff.nextDelayMillis())
    }

    @Test
    fun `jitter keeps every delay inside the multiplied band`() {
        val backoff = ReconnectBackoff(initialDelayMillis = 1_000, maximumDelayMillis = 60_000, jitter = { 1.05 })
        for (attempt in 0 until 8) {
            val base = min(1_000L shl min(attempt, 16), 60_000L)
            val delay = backoff.nextDelayMillis()
            assertTrue(delay >= floor(base * ReconnectBackoff.JITTER_FLOOR) - 1, "attempt=$attempt delay=$delay base=$base")
            assertTrue(delay <= base * ReconnectBackoff.JITTER_CEIL + 1, "attempt=$attempt delay=$delay base=$base")
        }
    }

    @Test
    fun `attempt bound per window is small and deterministic`() {
        val backoff = ReconnectBackoff(initialDelayMillis = 1_000, maximumDelayMillis = 60_000)
        // 最快（jitter 下界 0.8）序列：0.8,1.6,3.2,6.4,12.8,25.6s → 累计 50.4s，
        // 第 7 次（48s）会越过 60s 窗口。
        assertEquals(6, backoff.attemptsWithin(60_000L))
        assertEquals(1, backoff.attemptsWithin(1_000L))
        assertTrue(backoff.attemptsWithin(Long.MAX_VALUE) > 6)
    }

    @Test
    fun `a synchronized fleet failure does not form a retry storm`() {
        val devices = 100
        val windowMillis = 60_000L
        val backoffs = (0 until devices).map { device ->
            var call = 0
            ReconnectBackoff(
                initialDelayMillis = 1_000,
                maximumDelayMillis = 60_000,
                jitter = { 0.8 + ((device * 7 + call++ * 13) % 41) / 100.0 },
            )
        }

        // 每台设备连续失败 10 轮，记录全部重连延迟与时刻。
        val delaysPerDevice = backoffs.map { backoff -> List(10) { backoff.nextDelayMillis() } }
        val attemptTimes = delaysPerDevice.map { delays -> delays.runningFold(0L) { acc, delay -> acc + delay } }

        // 1) 每台设备任意 60s 窗口内的尝试数不超过退避上界（+首拍）。
        val bound = backoffs.first().attemptsWithin(windowMillis) + 1
        for (times in attemptTimes) {
            for (windowStart in 0 until times.last() step windowMillis) {
                val inWindow = times.count { it >= windowStart && it < windowStart + windowMillis }
                assertTrue(inWindow <= bound, "window at $windowStart saw $inWindow attempts (bound $bound)")
            }
        }

        // 2) 同一轮重连被 jitter 抖散：100 台设备的第一拍延迟至少 30 个不同值。
        val firstRoundDelays = attemptTimes.map { it[1] }.toSet()
        assertTrue(firstRoundDelays.size >= 30, "first round spread over ${firstRoundDelays.size} distinct delays")

        // 3) 每次重连延迟（非累计时刻）都落在合法区间内。
        for (delays in delaysPerDevice) {
            delays.forEach { assertTrue(it in 1..windowMillis) }
        }
    }

    @Test
    fun `constructor rejects degenerate configurations`() {
        assertFailsWith<IllegalArgumentException> { ReconnectBackoff(initialDelayMillis = 0) }
        assertFailsWith<IllegalArgumentException> { ReconnectBackoff(initialDelayMillis = 5_000, maximumDelayMillis = 1_000) }
    }
}
