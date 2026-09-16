package com.company.cloudctl.companion.service

import kotlinx.coroutines.runBlocking
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * B11 验收：短暂 rebind 在有界观察窗内恢复（且把新实例交给调用方，不重放
 * 提交）；永久关闭立即退出等待并留下 UI 可解释、可查询的状态。
 */
class RebindAwareReadinessWaiterTest {
    @BeforeTest
    fun setUp() {
        AccessibilityRuntimeStatusRegistry.clear()
    }

    @AfterTest
    fun tearDown() {
        AccessibilityRuntimeStatusRegistry.clear()
    }

    @Test
    fun `ready at first capture returns without sleeping`() = runBlocking {
        val service = Any()
        val sleeps = mutableListOf<Long>()
        val observation = waiter(active = { service }, sleep = { sleeps += it }).observe()

        assertEquals(RebindOutcome.READY, observation.outcome)
        assertEquals(0, observation.rebindCount)
        assertEquals(0L, observation.waitedMillis)
        assertFalse(observation.instanceChanged)
        assertSame(service, (observation.readiness as AccessibilityRuntimeReadiness.Ready<Any>).service)
        assertEquals(emptyList(), sleeps)
        val status = AccessibilityRuntimeStatusRegistry.snapshot()
        assertEquals(AccessibilityRuntimePhase.READY, status?.phase)
        assertEquals(true, status?.accessibilityEnabled)
        assertEquals(true, status?.accessibilityActive)
        assertEquals(true, status?.readiness)
        assertTrue(status!!.explanation.isNotBlank())
    }

    @Test
    fun `transient rebind recovers inside the bounded window and hands over the new instance`() = runBlocking {
        val oldInstance = Any()
        val newInstance = Any()
        val sleeps = mutableListOf<Long>()
        // Observation starts mid-rebind: the first capture is unstable (the
        // two reads disagree — old instance dying, rebound one arriving),
        // then the rebound instance stabilises on the next poll.
        var reads = 0
        val active: () -> Any? = {
            reads++
            if (reads == 1) oldInstance else newInstance
        }
        val observation = waiter(
            timeoutMillis = 3_000,
            pollIntervalMillis = 100,
            active = active,
            sleep = { sleeps += it },
        ).observe()

        assertEquals(RebindOutcome.REBIND_RECOVERED, observation.outcome)
        assertEquals(1, observation.rebindCount)
        assertTrue(observation.instanceChanged)
        assertTrue(observation.waitedMillis in 1..3_000)
        assertTrue(sleeps.isNotEmpty())
        // 不重放提交：Ready 携带的是重绑后的新实例，旧实例绝不返回。
        val ready = assertIs<AccessibilityRuntimeReadiness.Ready<Any>>(observation.readiness)
        assertSame(newInstance, ready.service)
        assertNotSame(oldInstance, ready.service)
        val status = AccessibilityRuntimeStatusRegistry.snapshot()
        assertEquals(AccessibilityRuntimePhase.READY, status?.phase)
        assertEquals(1, status?.rebindCount)
        assertEquals(true, status?.readiness)
    }

    @Test
    fun `disconnect then late activation is READY with bounded wait`() = runBlocking {
        val instance = Any()
        var reads = 0
        val observation = waiter(
            active = { instance.takeIf { reads > 1 } },
            beforeRead = { reads++ },
        ).observe()

        assertEquals(RebindOutcome.READY, observation.outcome)
        assertEquals(0, observation.rebindCount)
        assertTrue(observation.waitedMillis > 0)
    }

    @Test
    fun `permanently disabled setting exits the wait immediately without reading the runtime`() = runBlocking {
        var activeReads = 0
        val sleeps = mutableListOf<Long>()
        val observation = waiter(
            enabled = { false },
            active = { activeReads++; Any() },
            sleep = { sleeps += it },
        ).observe()

        assertEquals(RebindOutcome.DISABLED, observation.outcome)
        assertEquals(0L, observation.waitedMillis)
        assertEquals(0, activeReads)
        assertEquals(emptyList(), sleeps)
        val status = AccessibilityRuntimeStatusRegistry.snapshot()
        assertEquals(AccessibilityRuntimePhase.DISABLED, status?.phase)
        assertEquals(false, status?.accessibilityEnabled)
        assertEquals(false, status?.accessibilityActive)
        assertEquals(false, status?.readiness)
        assertTrue(status!!.explanation.contains("无障碍"))
    }

    @Test
    fun `disabled mid-wait exits at the next poll instead of burning the budget`() = runBlocking {
        var enabled = true
        val sleeps = mutableListOf<Long>()
        val observation = waiter(
            timeoutMillis = 3_000,
            pollIntervalMillis = 100,
            enabled = { enabled },
            active = { null },
            sleep = { sleeps += it; enabled = false },
        ).observe()

        assertEquals(RebindOutcome.DISABLED, observation.outcome)
        assertEquals(100L, observation.waitedMillis)
        assertEquals(listOf(100L), sleeps)
        assertEquals(AccessibilityRuntimePhase.DISABLED, AccessibilityRuntimeStatusRegistry.snapshot()?.phase)
    }

    @Test
    fun `still inactive after the full bounded budget reports INACTIVE`() = runBlocking {
        val sleeps = mutableListOf<Long>()
        var rebindWaitSeen = false
        val observation = waiter(
            timeoutMillis = 1_000,
            pollIntervalMillis = 400,
            active = { null },
            sleep = {
                sleeps += it
                AccessibilityRuntimeStatusRegistry.snapshot()?.let { status ->
                    if (status.phase == AccessibilityRuntimePhase.REBIND_WAIT) rebindWaitSeen = true
                }
            },
        ).observe()

        assertEquals(RebindOutcome.STILL_INACTIVE, observation.outcome)
        assertEquals(1_000L, sleeps.sum())
        assertEquals(1_000L, observation.waitedMillis)
        assertTrue(rebindWaitSeen)
        val status = AccessibilityRuntimeStatusRegistry.snapshot()
        assertEquals(AccessibilityRuntimePhase.INACTIVE, status?.phase)
        // enabled 与 active 分开上报：这里 enabled 仍为 true，只是未激活。
        assertEquals(true, status?.accessibilityEnabled)
        assertEquals(false, status?.accessibilityActive)
        assertEquals(false, status?.readiness)
    }

    @Test
    fun `same stable instance never counts as a rebind`() = runBlocking {
        val instance = Any()
        val observation = waiter(active = { instance }).observe()
        assertEquals(0, observation.rebindCount)
        assertEquals(RebindOutcome.READY, observation.outcome)
    }

    private fun waiter(
        timeoutMillis: Long = 1_000,
        pollIntervalMillis: Long = 100,
        enabled: () -> Boolean = { true },
        active: () -> Any? = { null },
        sleep: suspend (Long) -> Unit = {},
        beforeRead: () -> Unit = {},
    ) = RebindAwareReadinessWaiter<Any>(
        timeoutMillis = timeoutMillis,
        pollIntervalMillis = pollIntervalMillis,
        isEnabled = enabled,
        activeService = { beforeRead(); active() },
        sleep = sleep,
        now = { java.time.Instant.ofEpochMilli(0L) },
    )
}
